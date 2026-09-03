#!/usr/bin/env python3
"""A substantive change to the plugin must raise its version.

    python3 .github/scripts/check_version_bumped.py --base-ref <sha>
    python3 .github/scripts/check_version_bumped.py --self-test [--verbose]

    0 = bumped, or nothing shipped changed    1 = changed without a bump
    2 = cannot judge (not a git repository, unreadable plugin.json, bad base)

Claude Code decides whether an installed plugin needs updating by comparing the
`version` in `.claude-plugin/plugin.json`. A release that changes what the
plugin does without changing that number is a release nobody receives: the
marketplace serves it, every existing install keeps the old copy, and the only
symptom is that a fix "did not work" for everyone except the author.

Nothing about that is visible in a diff. It is the exact shape this repository
keeps describing -- irreversible enough to matter, silent enough to survive
review -- so it gets a check rather than a line in CONTRIBUTING.md.

This one has already fired on its own repository. `plugin.json` sat at `0.1.0`
across the first nine merged pull requests — one of which renamed the plugin —
and nothing anywhere noticed.

## Why `.github/scripts/` and not `shared/scripts/gates/`

Everything under `shared/scripts/gates/` is copied into the repositories this
plugin scaffolds. This check is about *this* repository's release hygiene and
would be meaningless there -- a scaffolded repo has no plugin.json. Judgement
still lives in a script rather than in the workflow; it is just a script that
belongs to the repository rather than to the payload.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

# The surface Claude Code actually loads, plus the manifest that describes it.
# `.github/`, `docs/`, and the top-level prose are deliberately absent: a typo
# fix in a decision record reaches no installed client, and requiring a version
# bump for it would train everyone to bump reflexively, which is the failure
# this check exists to prevent rather than a milder version of it.
SHIPPED = (".claude-plugin/", "skills/", "agents/", "commands/", "hooks/",
           "shared/")
MANIFEST = ".claude-plugin/plugin.json"


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def parse_version(text):
    """A tuple for comparison, or None if it is not a version at all.

    Lenient about the shape (`1.2`, `1.2.3`, `1.2.3-rc1` all parse) and strict
    about the ordering, because the only question asked of it is "is this one
    larger than that one".
    """
    if not isinstance(text, str) or not text.strip():
        return None
    core = text.strip().split("+")[0].split("-")[0]
    parts = core.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def version_at(ref, root, path=MANIFEST):
    out = sh(["git", "show", f"{ref}:{path}"], cwd=root)
    if out.returncode != 0:
        return None, f"no {path} at {ref}"
    try:
        return json.loads(out.stdout).get("version"), None
    except ValueError as exc:
        return None, f"{path} at {ref} is not valid JSON: {exc}"


def changed_files(base, root):
    out = sh(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=root)
    if out.returncode != 0:
        # `...` needs a merge base. A shallow clone has none, and silently
        # falling back to a two-dot diff would compare against whatever the
        # fetch happened to include.
        return None
    return [p for p in out.stdout.split("\n") if p]


def check(base, root):
    """Returns (exit_code, message)."""
    # `git rev-parse`, not `os.path.isdir(".git")`. In a linked worktree .git
    # is a *file* pointing at the real directory, and in a submodule likewise,
    # so the isdir test reports "not a git repository" for a tree git is
    # perfectly happy with. It answered that way the first time this ran inside
    # a worktree -- exit 2, in a check whose whole contract is that 2 means
    # nobody could tell.
    if sh(["git", "rev-parse", "--git-dir"], cwd=root).returncode != 0:
        return 2, "cannot judge: not a git repository"

    files = changed_files(base, root)
    if files is None:
        return 2, (f"cannot judge: no merge base with {base}. A shallow "
                   f"checkout cannot answer this — use fetch-depth: 0.")

    touched = sorted(f for f in files if f.startswith(SHIPPED))
    if not touched:
        return 0, "nothing under the shipped surface changed"

    with open(os.path.join(root, MANIFEST), encoding="utf-8") as fh:
        head_raw = json.load(fh).get("version")
    base_raw, err = version_at(base, root)
    if err:
        # A plugin.json that did not exist at the base is a new plugin, not a
        # missed bump.
        return 0, f"{err}; treating as newly added"

    head, prev = parse_version(head_raw), parse_version(base_raw)
    if head is None:
        return 2, f"cannot judge: version {head_raw!r} is not a version"
    if prev is None:
        return 2, f"cannot judge: version {base_raw!r} at {base} is not a version"

    if head > prev:
        return 0, f"version {base_raw} -> {head_raw}"

    listing = "\n".join(f"    {f}" for f in touched[:12])
    more = f"\n    … and {len(touched) - 12} more" if len(touched) > 12 else ""
    return 1, (
        f"{len(touched)} file(s) under the shipped surface changed, but "
        f"{MANIFEST} is still {head_raw}:\n{listing}{more}\n\n"
        f"Claude Code compares that number to decide whether an installed copy "
        f"is stale. Left as it is, this change reaches nobody who already has "
        f"the plugin — and it fails silently, for them, not for you.\n\n"
        f"Raise it in {MANIFEST}, or, if this really ships nothing, say so on "
        f"the pull request with the `no-version-bump` label.")


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _repo(version="0.1.0"):
    tmp = tempfile.mkdtemp(prefix="version-check-")
    os.makedirs(os.path.join(tmp, ".claude-plugin"))
    _write(tmp, MANIFEST, json.dumps({"name": "demo", "version": version}) + "\n")
    _write(tmp, "README.md", "# demo\n")
    sh(["git", "init", "-q", "."], cwd=tmp)
    _commit(tmp, "init")
    return tmp


def _write(root, rel, body):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def _commit(root, message):
    sh(["git", "add", "-A"], cwd=root)
    sh(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
        "commit", "-qm", message], cwd=root)
    return sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()


def _case_shipped_change_without_bump():
    root = _repo()
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "skills/demo/SKILL.md", "---\nname: demo\n---\n\nNew.\n")
        _commit(root, "change a skill")
        code, msg = check(base, root)
        if code != 1:
            return f"expected 1, got {code}: {msg}"
        if "skills/demo/SKILL.md" not in msg:
            return f"red, but does not name the file that changed: {msg}"
        return None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _case_shipped_change_with_bump():
    root = _repo()
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "skills/demo/SKILL.md", "---\nname: demo\n---\n\nNew.\n")
        _write(root, MANIFEST,
               json.dumps({"name": "demo", "version": "0.2.0"}) + "\n")
        _commit(root, "change a skill and bump")
        code, msg = check(base, root)
        return None if code == 0 else f"expected 0, got {code}: {msg}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _case_docs_only_needs_no_bump():
    """The negative control. Without it, `exit 1` would pass this suite."""
    root = _repo()
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "docs/decisions/0001-x.md", "# 0001\n\nA decision.\n")
        _write(root, "README.md", "# demo\n\nMore prose.\n")
        _commit(root, "docs only")
        code, msg = check(base, root)
        return None if code == 0 else f"expected 0, got {code}: {msg}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _case_lower_version_is_not_a_bump():
    root = _repo(version="0.9.0")
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "skills/demo/SKILL.md", "---\nname: demo\n---\n\nNew.\n")
        _write(root, MANIFEST,
               json.dumps({"name": "demo", "version": "0.10"}) + "\n")
        _commit(root, "change and mis-version")
        code, _ = check(base, root)
        # 0.10 > 0.9 numerically per component, which is correct semver and the
        # reason this compares tuples of ints rather than strings.
        return None if code == 0 else "0.10 must count as newer than 0.9.0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _case_string_comparison_would_be_wrong():
    root = _repo(version="0.9.0")
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "hooks/hooks.json", "{}\n")
        _write(root, MANIFEST,
               json.dumps({"name": "demo", "version": "0.8.0"}) + "\n")
        _commit(root, "go backwards")
        code, _ = check(base, root)
        return None if code == 1 else f"a decrease must be caught, got {code}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _case_a_linked_worktree_is_judgeable():
    """A worktree is a git repository, and `.git` in one is a file.

    Found by running this check inside a worktree while resolving a rebase, and
    getting "not a git repository" from a tree git had just created.
    """
    root = _repo()
    linked = tempfile.mkdtemp(prefix="version-check-wt-")
    path = os.path.join(linked, "wt")
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "skills/demo/SKILL.md", "---\nname: demo\n---\n\nNew.\n")
        _commit(root, "change a skill")
        out = sh(["git", "worktree", "add", "-q", "--detach", path, "HEAD"],
                 cwd=root)
        if out.returncode != 0:
            return f"could not build the fixture: {out.stderr.strip()[:200]}"
        if os.path.isdir(os.path.join(path, ".git")):
            return "fixture is wrong: .git is a directory, so this proves nothing"
        code, msg = check(base, path)
        if code == 2:
            return f"a worktree must be judgeable, got: {msg}"
        if code != 1:
            return f"expected 1 in the worktree, got {code}: {msg}"
        return None
    finally:
        sh(["git", "worktree", "remove", "--force", path], cwd=root)
        shutil.rmtree(linked, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)


def _case_a_command_is_shipped_too():
    """A slash command reaches an installed client like everything else here.

    `commands/` was missing from the list until a step added to `/learn`
    reached every installation without a release. Nothing was wrong with the
    change; the check simply had a hole in its idea of the plugin's surface.
    """
    root = _repo()
    try:
        base = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
        _write(root, "commands/demo.md", "---\ndescription: d\n---\n\nRun.\n")
        _commit(root, "change a command")
        code, msg = check(base, root)
        if code != 1:
            return f"expected 1, got {code}: {msg}"
        if "commands/demo.md" not in msg:
            return f"red, but does not name the file that changed: {msg}"
        return None
    finally:
        shutil.rmtree(root, ignore_errors=True)


SELF_TEST = [
    ("a shipped file changed with no bump is caught",
     _case_shipped_change_without_bump),
    ("a shipped file changed with a bump passes",
     _case_shipped_change_with_bump),
    ("a docs-only change needs no bump", _case_docs_only_needs_no_bump),
    ("0.10 is newer than 0.9.0", _case_lower_version_is_not_a_bump),
    ("a version that went backwards is caught",
     _case_string_comparison_would_be_wrong),
    ("a linked worktree is judgeable", _case_a_linked_worktree_is_judgeable),
    ("a command is shipped too", _case_a_command_is_shipped_too),
]


def self_test(verbose):
    failures = []
    for label, fn in SELF_TEST:
        try:
            problem = fn()
        except Exception as exc:
            problem = f"raised {type(exc).__name__}: {exc}"
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif verbose:
            print(f"  ok  {label}")
    if failures:
        print(f"{len(failures)} of {len(SELF_TEST)} self-test case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if verbose:
        print(f"{len(SELF_TEST)} cases: a missed bump is caught, and a change "
              f"that ships nothing is not")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-ref", help="the ref this change is measured against")
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot judge: git not on PATH", file=sys.stderr)
        return 2
    if a.self_test:
        return self_test(a.verbose)
    if not a.base_ref:
        print("cannot judge: --base-ref is required (or use --self-test)",
              file=sys.stderr)
        return 2

    code, message = check(a.base_ref, os.path.abspath(a.root))
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
