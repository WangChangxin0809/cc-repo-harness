#!/usr/bin/env python3
"""The plugin surface is prose, and prose has no compiler. Give it one.

    python3 shared/scripts/check_plugin_structure.py [--root .]
    python3 shared/scripts/check_plugin_structure.py --selftest [--verbose]

    0 = the manifest and components hold      1 = something is wrong
    2 = cannot judge (no .claude-plugin/ — not a plugin repository)

    --always-on-cap N   tokens of name+description, summed (default 400)

This repository shipped forty selftest cases covering the *payload* it copies
into other people's repositories, and zero covering the thing that is actually
the plugin: `.claude-plugin/`, `skills/`, `agents/`, `hooks/`. The reason is not
carelessness. Payload is code and code has selftests; the plugin surface is
markdown, and nobody writes a test for a paragraph.

So the defects there were real and invisible. Ten commands across four skills
told an agent to run `python3 <plugin>/shared/scripts/scaffold.py`, where
`<plugin>` was a placeholder invented by this repository and understood by
nothing. The variable Claude Code actually sets is `${CLAUDE_PLUGIN_ROOT}`, and
it exists precisely because a plugin's install location differs by install
method and platform.

`claude plugin validate --strict` is the first-party checker and is better than
this at manifest schema. It is not a substitute: it needs the CLI installed,
and it does not know that a *skill's prose* must not tell an agent to guess a
path. Run both.

This lived in `gates/` and shipped, commented out of every generated `ci.sh`,
because a target repository has no `.claude-plugin/` to judge. A check that
arrives switched off is not payload; it is our instrument in a stranger's
tree. So it sits beside `probe_repo.py` and `drift.py`, run from here and
copied nowhere, and carries its own selftest for the same reason they do:
the gates' harness only knows the gates directory -> docs/decisions/0058
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

MANIFEST = os.path.join(".claude-plugin", "plugin.json")
COMPONENT_DIRS = ("commands", "agents", "skills", "hooks")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"

# A path into the plugin that is not written with the variable. Each of these
# resolves on exactly one machine, or on none.
BAD_PATH = (
    (re.compile(r"<plugin[^>]*>/"), "a hand-invented placeholder"),
    (re.compile(r"~/\.claude/plugins/"), "a home-directory path"),
    (re.compile(r"(?<![\w${])/(?:Users|home)/[\w.-]+/"), "an absolute path"),
)


def load(root):
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        return None, str(exc)


def check_manifest(m, out, root=None):
    name = m.get("name")
    if not name:
        out.append(f"{MANIFEST}: no `name` — it is the only required field")
    elif not KEBAB.match(name):
        out.append(f"{MANIFEST}: name {name!r} is not kebab-case; it has to be "
                   f"unique across every installed plugin and typed by users")

    version = m.get("version")
    if version is None:
        out.append(f"{MANIFEST}: no `version`. Without one there is no way to "
                   f"say which release someone installed, and `claude plugin "
                   f"tag` has nothing to validate against")
    elif not SEMVER.match(str(version)):
        out.append(f"{MANIFEST}: version {version!r} is not semver MAJOR.MINOR.PATCH")

    if not m.get("description"):
        out.append(f"{MANIFEST}: no `description` — it is what a user reads "
                   f"before installing")

    # A custom `commands` or `agents` list REPLACES the default directory;
    # only `skills` adds to it. `agents` entries are files, and the first-
    # party validator insists on `.md`. So a manifest that lists
    # `./agents/assess/reader.md` and forgets `./agents/repo-explorer.md` has
    # silently dropped the explorer, and one that lists a file that is not
    # there has dropped that one. Neither gets a message from the loader.
    for key in ("commands", "agents", "skills", "hooks", "mcpServers"):
        value = m.get(key)
        if value is None:
            continue
        paths = value if isinstance(value, list) else [value]
        for path in paths:
            if not isinstance(path, str) or not path.startswith("./"):
                out.append(f"{MANIFEST}: {key} path {path!r} must be relative "
                           f"and start with './'")
            elif root is not None and not os.path.exists(os.path.join(root, path)):
                out.append(f"{MANIFEST}: {key} path {path!r} does not exist, "
                           f"and a listed path replaces the default — what "
                           f"it was meant to load, loads nowhere")
        if key == "agents" and root is not None:
            default = os.path.join(root, "agents")
            listed = {os.path.normpath(os.path.join(root, p))
                      for p in paths if isinstance(p, str)}
            if os.path.isdir(default):
                dropped = [f for f in sorted(os.listdir(default))
                           if f.endswith(".md") and os.path.normpath(
                               os.path.join(default, f)) not in listed]
                if dropped:
                    out.append(f"{MANIFEST}: `agents` lists files and "
                               f"leaves out agents/{dropped[0]} — a list "
                               f"replaces the default directory, so it no "
                               f"longer loads")


def check_layout(root, out):
    inside = os.path.join(root, ".claude-plugin")
    for d in COMPONENT_DIRS:
        if os.path.isdir(os.path.join(inside, d)):
            out.append(f".claude-plugin/{d}/ — component directories live at "
                       f"the plugin root, not inside .claude-plugin/. Nested "
                       f"there they are never discovered, and nothing says so")


def check_skills(root, out):
    skills = os.path.join(root, "skills")
    if not os.path.isdir(skills):
        return
    for entry in sorted(os.listdir(skills)):
        d = os.path.join(skills, entry)
        if not os.path.isdir(d):
            continue
        if not KEBAB.match(entry):
            out.append(f"skills/{entry}/ is not kebab-case")
        skill = os.path.join(d, "SKILL.md")
        if not os.path.isfile(skill):
            out.append(f"skills/{entry}/ has no SKILL.md — the file name is "
                       f"exact; README.md is not discovered")
            continue
        fm = FRONTMATTER.match(read(skill))
        if not fm:
            out.append(f"skills/{entry}/SKILL.md has no YAML frontmatter")
            continue
        for field in ("name", "description"):
            if not re.search(rf"^{field}:\s*\S", fm.group(1), re.M):
                out.append(f"skills/{entry}/SKILL.md frontmatter has no "
                           f"`{field}`. The description is the *only* thing "
                           f"deciding whether this skill is ever activated")


def check_agents(root, out):
    """Every agent file, at any depth under agents/.

    Agents can live in a subdirectory the manifest lists, and one there with
    no description is as invisible as one at the top: the description is the
    only thing the router reads."""
    agents = os.path.join(root, "agents")
    if not os.path.isdir(agents):
        return
    for cur, _dirs, files in os.walk(agents):
        for entry in sorted(files):
            if not entry.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(cur, entry), root)
            fm = FRONTMATTER.match(read(os.path.join(cur, entry)))
            if not fm:
                out.append(f"{rel} has no YAML frontmatter")
            elif not re.search(r"^description:\s*\S", fm.group(1), re.M):
                out.append(f"{rel} frontmatter has no `description`")


def _field(block, key):
    m = re.search(rf"^{key}:\s*(.*)$", block, re.M)
    return m.group(1).strip() if m else ""


def always_on_cost(root):
    """(rel, name, tokens) for every component the router keeps in context.

    Claude Code lists every installed skill, agent and command by `name` and
    `description` on every turn, in every repository on the machine, whether or
    not that repository has anything for the plugin to do. Bodies are not
    charged -- they load when the thing is invoked -- so this is a cost that
    only the frontmatter can lower.

    Nothing measured it. This repository's own plugin drifted to 350 tokens a
    turn, most of it one skill description that had grown a list of every
    symptom anyone might type. Each addition was one plausible clause.
    """
    found = []
    for base in ("skills", "agents", "commands"):
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for cur, _dirs, files in os.walk(d):
            for entry in sorted(files):
                if not entry.endswith(".md"):
                    continue
                if base == "skills" and entry != "SKILL.md":
                    continue
                path = os.path.join(cur, entry)
                fm = FRONTMATTER.match(read(path))
                if not fm:
                    continue
                block = fm.group(1)
                name = _field(block, "name") or os.path.basename(path)
                cost = len(f"{name}: {_field(block, 'description')}") // 4
                found.append((os.path.relpath(path, root), name, cost))
    return sorted(found, key=lambda t: -t[2])


def check_portable_paths(root, out):
    """Every reference into the plugin must go through the variable.

    This is the check that would have caught the defect that motivated the
    file. A hook command with a wrong path fails loudly the first time it
    fires; a *skill* telling an agent to run `<plugin>/scripts/x.py` fails
    quietly, because the agent guesses, and a plausible guess looks like it
    worked."""
    targets = []
    for sub in ("skills", "agents", "commands"):
        d = os.path.join(root, sub)
        for cur, _dirs, files in os.walk(d):
            targets += [os.path.join(cur, f) for f in files if f.endswith(".md")]
    hooks = os.path.join(root, "hooks", "hooks.json")
    if os.path.isfile(hooks):
        targets.append(hooks)

    for path in sorted(targets):
        rel = os.path.relpath(path, root)
        for i, line in enumerate(read(path).splitlines(), 1):
            for pattern, why in BAD_PATH:
                if pattern.search(line):
                    out.append(f"{rel}:{i}  {why} where {PLUGIN_ROOT} belongs")
                    break


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--always-on-cap", type=int, default=400,
                    help="max tokens of component name+description, summed")
    ap.add_argument("--selftest", action="store_true",
                    help="plant each defect in a throwaway plugin, watch it go red")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.verbose)
    root = os.path.abspath(a.root)

    manifest, err = load(root)
    if err == "missing":
        print(f"cannot judge: no {MANIFEST} — this is not a plugin repository",
              file=sys.stderr)
        return 2
    if manifest is None:
        print(f"cannot judge: {MANIFEST} did not parse: {err}", file=sys.stderr)
        return 2

    out = []
    check_manifest(manifest, out, root)
    check_layout(root, out)
    check_skills(root, out)
    check_agents(root, out)
    check_portable_paths(root, out)

    charged = always_on_cost(root)
    total = sum(c for _, _, c in charged)
    if total > a.always_on_cap:
        listing = "\n".join(f"      {name:<28} ~{c:>4} tok   {rel}"
                             for rel, name, c in charged)
        out.append(
            f"the plugin costs ~{total} tokens on every turn, cap is "
            f"{a.always_on_cap}:\n{listing}\n"
            f"    Paid in EVERY repository on the machine, including the ones\n"
            f"    that never invoke this plugin. Shorten a description, or move\n"
            f"    the component into the payload so the repository that wants\n"
            f"    it is the one that pays.")

    if out:
        print(f"{len(out)} problem(s) in the plugin surface:\n", file=sys.stderr)
        for line in out:
            print(f"  {line}", file=sys.stderr)
        print("\nAlso run `claude plugin validate . --strict`, which knows the "
              "manifest\nschema better than this does.", file=sys.stderr)
        return 1

    n = len([d for d in COMPONENT_DIRS if os.path.isdir(os.path.join(root, d))])
    print(f"plugin surface intact: manifest, {n} component director(ies), "
          f"portable paths, ~{total} tok/turn always-on")
    return 0


# --- selftest ----------------------------------------------------------------
# Every case starts from a plugin that passes, plants one defect, and expects
# the named complaint. The two with needle=None plant the thing most easily
# mistaken for a defect and expect silence; the last expects exit 2, because a
# checker that answers 0 when there is nothing to look at is the worse bug.

DEMO_SKILL = ("---\nname: demo\ndescription: Demonstrate something, when asked "
              "to.\n---\n\n# Demo\n\nGuidance lives here.\n")


def _manifest(**extra):
    m = {"name": "demo-plugin", "version": "0.1.0",
         "description": "A demonstration plugin."}
    m.update(extra)
    return json.dumps(m, indent=2) + "\n"


def _write(root, rel, body):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def _fixture(root):
    _write(root, MANIFEST, _manifest())
    _write(root, "skills/demo/SKILL.md", DEMO_SKILL)
    _write(root, "agents/helper.md",
           "---\nname: helper\ndescription: Helps with demonstrations.\n---\n\n"
           "You help.\n")


# (why, extra args, expected exit, needle in stderr or None, plant)
CASES = [
    ("a skill telling an agent to guess the plugin's location", [], 1,
     "hand-invented placeholder",
     lambda t: _write(t, "skills/demo/SKILL.md",
                      "---\nname: demo\ndescription: Demonstrate something, "
                      "when asked to.\n---\n\n"
                      "Read `<plugin>/references/moments.md` first.\n")),
    # Bodies are free -- they load when the thing is invoked. The frontmatter
    # is not: every skill, agent and command is listed by name and description
    # on every turn, in every repository on the machine.
    ("a description that has grown a clause for every symptom",
     ["--always-on-cap", "60"], 1, "on every turn, cap is 60",
     lambda t: _write(t, "skills/demo/SKILL.md",
                      "---\nname: demo\ndescription: Demonstrate something, "
                      "when asked to. "
                      + "Use it when somebody mentions a thing. " * 12
                      + "\n---\n\n# Demo\n\nGuidance lives here.\n")),
    ("a long body behind a short description, which must NOT be reported",
     ["--always-on-cap", "60"], 0, None,
     lambda t: _write(t, "skills/demo/SKILL.md",
                      DEMO_SKILL + "A paragraph of guidance.\n" * 400)),
    ("component directories nested inside .claude-plugin/", [], 1,
     "not inside .claude-plugin/",
     lambda t: _write(t, ".claude-plugin/skills/x/SKILL.md",
                      "---\nname: x\ndescription: Does x.\n---\n\nx\n")),
    ("a skill whose frontmatter has no description", [], 1,
     "deciding whether this skill is ever activated",
     lambda t: _write(t, "skills/demo/SKILL.md",
                      "---\nname: demo\n---\n\nGuidance lives here.\n")),
    ("a manifest version that is not semver", [], 1, "is not semver",
     lambda t: _write(t, MANIFEST, _manifest(version="v0.1"))),
    # A listed path replaces the default directory. The manifest names the
    # new agent and forgets the old one, and the loader says nothing.
    ("an agents list that drops the agent at the top level", [], 1,
     "leaves out agents/helper.md",
     lambda t: (_write(t, "agents/assess/reader.md",
                       "---\nname: reader\ndescription: Reads one thing.\n"
                       "---\n\nYou read.\n"),
                _write(t, MANIFEST,
                       _manifest(agents=["./agents/assess/reader.md"])))),
    ("an agents list naming a file that is not there", [], 1, "does not exist",
     lambda t: _write(t, MANIFEST, _manifest(agents=["./agents/helper.md",
                                                     "./agents/gone.md"]))),
    ("an agent in a subdirectory with no description", [], 1,
     "agents/assess/reader.md frontmatter has no `description`",
     lambda t: _write(t, "agents/assess/reader.md",
                      "---\nname: reader\n---\n\nYou read.\n")),
    ("the variable itself, which must NOT be reported", [], 0, None,
     lambda t: _write(t, "skills/demo/SKILL.md",
                      "---\nname: demo\ndescription: Demonstrate something, "
                      "when asked to.\n---\n\n"
                      "Read `${CLAUDE_PLUGIN_ROOT}/references/moments.md` "
                      "first.\n")),
    ("no manifest at all, which is COULD NOT JUDGE and never a pass", [], 2,
     "not a plugin repository",
     lambda t: os.remove(os.path.join(t, MANIFEST))),
]


def selftest(verbose=False):
    import shutil
    import subprocess
    import tempfile

    def run(root, args):
        return subprocess.run([sys.executable, __file__, "--root", root, *args],
                              capture_output=True, text=True)

    bad = 0
    for why, args, want, needle, plant in CASES:
        tmp = tempfile.mkdtemp(prefix="plugin-surface-")
        try:
            _fixture(tmp)
            base = run(tmp, args)
            if base.returncode != 0:
                bad += 1
                print(f"FAIL {why}\n     baseline not green: exit "
                      f"{base.returncode}\n{base.stderr}")
                continue
            plant(tmp)
            got = run(tmp, args)
            ok = got.returncode == want and (needle is None
                                             or needle in got.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        bad += not ok
        if verbose or not ok:
            print(f"{'ok  ' if ok else 'FAIL'} {why}")
        if not ok:
            print(f"     wanted exit {want}"
                  + (f" saying {needle!r}" if needle else "")
                  + f", got exit {got.returncode}\n{got.stderr}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} cases pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
