#!/usr/bin/env python3
"""Every command a document shows must actually run.

    python3 scripts/gates/check_docs_runnable.py [--root .]

    0 = every documented invocation resolves
    1 = a document names a script or a flag that does not exist
    2 = cannot judge (not a git repository)

A document that shows a command is making a checkable claim about code, and it
is the claim that rots first: the script grows a flag, loses one, renames a
subcommand, and the document keeps saying what used to be true. Nobody notices,
because nobody types a command out of a document they wrote.

This gate found four such lines in this repository's own skills on the day it
was written -- two files documenting `dream.py prepare --src ... --snap ...`
against a script whose flags had been `--notes`/`--out` since it was committed.
Every one of them failed with `unrecognized arguments`. They had been shipped.

## What it checks, and what it deliberately does not

Flags and subcommands are read out of the target script's `argparse` calls
*statically*, with `ast`. Running `--help` would be more accurate and is not an
option: this gate ships into repositories it did not write, and a check that
executes the code it is checking is the same mistake the PreToolUse hook exists
to avoid.

Static reading has a known blind spot -- a flag added through a loop or a helper
function is invisible, so a *documented* flag can be reported missing when it
exists. That direction is safe (a false red is read and dismissed); the reverse
would not be. `# docs-runnable: ignore` on the command's own line, or
`<!-- docs-runnable-ok: reason -->` near the top of a file, exempts it.

Values are not checked. `--root <repo>` is a fine thing for a document to say;
whether `<repo>` exists is not knowable and not the point. Only the names of
flags and subcommands are claims about the code.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys

# A command must begin its line (after indentation, and an optional `$` prompt).
# That rule is what keeps `"command": "python3 scripts/guards/dispatch.py"` --
# a JSON fragment showing a hook wiring, not a shell command -- out of scope.
INVOCATION = re.compile(r"^\s*(?:\$\s+)?python3?\s+(\S+\.py)\s*(.*)$")
EXEMPT_FILE = re.compile(r"<!--\s*docs-runnable-ok:")
EXEMPT_LINE = "# docs-runnable: ignore"
PLACEHOLDER = re.compile(r"^<.*>$")
HEADER_LINES = 40

# A fence that declares its language as markdown holds *sample markup* -- what a
# good how-to step looks like, what a decision record's header is -- and the
# commands inside it illustrate a shape rather than name anything in this tree.
# Reading them as live invocations reports the sample's own placeholder paths as
# broken, which is a finding about a document that is doing its job.
#
# Only `markdown` and `md`. Every other language is a real command in a real
# shell as far as this gate is concerned, and a `bash` fence full of examples is
# exactly the case this gate was written to catch.
FENCE = re.compile(r"^\s*(?:```|~~~)\s*(\w*)")
SAMPLE_LANGS = {"markdown", "md"}


def tracked_markdown(root):
    out = subprocess.run(["git", "ls-files", "-z", "*.md"],
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split("\0") if p]


def resolve_script(root, raw):
    """A documented path to a file in this repository, or None.

    Documents here speak two dialects: the plugin's own layout
    (`shared/scripts/gates/x.py`) and the layout it scaffolds into a target
    repository (`scripts/gates/x.py`). Both name the same file, and a gate that
    understood only one of them would be red on half of its own documentation.

    A leading `${CLAUDE_PLUGIN_ROOT}/` is stripped too. That is the variable
    Claude Code sets to a plugin's install location, so a skill telling an agent
    to run something inside the plugin must use it -- and until it was stripped
    here, every command that did went *silently unchecked*, which is the failure
    mode this gate exists to prevent, one level up."""
    rel = re.sub(r"^\$\{CLAUDE_PLUGIN_ROOT\}/|^<[^<>/]+>/", "", raw.strip())
    for cand in (rel, os.path.join("shared", rel)):
        if os.path.isfile(os.path.join(root, cand)):
            return cand
    return None


def declared(root, rel):
    """(flags, subcommands) declared by a script's argparse calls.

    Returns (None, None) when the file cannot be parsed -- a syntax error is
    somebody else's failure and not something to report as a documentation
    defect."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None, None

    flags, subs = set(), set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        names = [a.value for a in node.args
                 if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        for n in names:
            if n.startswith("-"):
                flags.add(n)
        positional = [n for n in names if not n.startswith("-")]
        for kw in node.keywords:
            # `choices=[...]` on a positional is how these scripts spell a
            # subcommand. Collected only for positionals, so that a documented
            # *value* of an option is never mistaken for a subcommand.
            if kw.arg == "choices" and positional and isinstance(
                    kw.value, (ast.List, ast.Tuple, ast.Set)):
                subs.update(e.value for e in kw.value.elts
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str))
    return flags, subs


def tokens(rest):
    """Split a command tail, stopping at a trailing comment or `--`."""
    rest = re.split(r"\s{2,}#", rest)[0]
    out = []
    for tok in rest.split():
        if tok == "--":
            break
        out.append(tok)
    return out


def check_command(root, script, rest, flags, subs):
    """Findings for one documented invocation."""
    found = []
    toks = tokens(rest)
    for tok in toks:
        if not tok.startswith("-") or tok == "-":
            continue
        name = tok.split("=", 1)[0]
        if name not in flags:
            found.append(f"{script} has no option {name}")
    if subs:
        bare = [t for t in toks if not t.startswith("-")]
        # Only the first bare token can be the subcommand; anything after it is
        # a value belonging to the option before it.
        if bare and bare[0] not in subs and not PLACEHOLDER.match(bare[0]):
            found.append(f"{script} has no subcommand {bare[0]!r} "
                         f"(expected one of {', '.join(sorted(subs))})")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    docs = tracked_markdown(root)
    if docs is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    findings, checked = [], 0
    for rel in docs:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        if any(EXEMPT_FILE.search(l) for l in lines[:HEADER_LINES]):
            continue

        in_sample = False
        for i, line in enumerate(lines, 1):
            fence = FENCE.match(line)
            if fence:
                # A closing fence carries no language, so it can only ever end a
                # sample -- never open one.
                in_sample = (not in_sample) and fence.group(1) in SAMPLE_LANGS
                continue
            if in_sample or EXEMPT_LINE in line:
                continue
            m = INVOCATION.match(line)
            if not m:
                continue
            script = resolve_script(root, m.group(1))
            if script is None:
                # Not every documented `python3 x.py` is about this repository
                # -- `python3 -m swebench...`, a snippet from another project.
                # Only a path that looks like it belongs here is a finding.
                raw = m.group(1)
                if re.sub(r"^\$\{CLAUDE_PLUGIN_ROOT\}/|^<[^<>/]+>/", "",
                          raw).startswith(("scripts/", "shared/", "hooks/")):
                    findings.append(f"{rel}:{i}  names a script that does not "
                                    f"exist: {raw}")
                continue
            flags, subs = declared(root, script)
            if flags is None:
                continue
            checked += 1
            for problem in check_command(root, script, m.group(2), flags, subs):
                findings.append(f"{rel}:{i}  {problem}")

    if findings:
        print(f"{len(findings)} documented command(s) would not run:\n",
              file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print("\nFix the document, or the script -- but a command that has "
              "never been\nrun is not documentation, it is a guess that "
              "outranks the code.", file=sys.stderr)
        return 1

    print(f"{checked} documented command(s) resolve against the scripts they name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
