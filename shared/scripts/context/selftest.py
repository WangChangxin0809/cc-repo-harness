#!/usr/bin/env python3
"""Prove the context hooks still reach the model.

    python3 scripts/context/selftest.py [--verbose]

    0 = every case held    1 = a case failed    2 = cannot run

This directory had no selftest at all, and it cost exactly what you would
expect. `after_edit.py` was wired into every tier B repository as a PostToolUse
hook and printed its findings to **stdout** -- which, on every event except
`UserPromptSubmit`, `UserPromptExpansion` and `SessionStart`, goes to the debug
log and nowhere else. It delivered nothing to anybody for its whole life.

An index case did test it, and passed, because it asserted on the subprocess's
stdout. The script wrote to stdout; the test read stdout; the model never saw
it. **The test was correct about the wrong boundary**, which is the failure mode
this whole directory now has to be checked against: not "did the script produce
text" but "is the text in an envelope Claude Code delivers".

`case_delivery_is_an_envelope_not_bare_stdout` is that check, and it is first on
purpose.

Known gap, deliberately recorded rather than quietly left: `on_stop.py` still
has no coverage here, and neither of its two load-bearing
properties is verified. It is written down in the repository's tech-debt
tracker rather than left as an intention.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "before_write.py")

RULE = """\
---
paths:
  - "src/api/**"
---
# API rules
- call validate() before touching the DB
"""

WIDE = """\
---
paths:
  - "**/*.py"
---
# Wide
- this one matches python anywhere, including up and out
"""

UNCONDITIONAL = """\
---
name: everywhere
---
# Global
- this one has no paths: and is already loaded at launch
"""


def make_repo(tmp, files):
    for rel, body in files.items():
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path) or tmp, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
    return tmp


def fire(tmp, payload):
    """Run the hook the way Claude Code does, and return its raw stdout.

    `CLAUDE_PROJECT_DIR` is stripped rather than set: this suite runs inside a
    repository that has it, and a case that silently probed *this* tree instead
    of its own fixture would pass for the wrong reason."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    payload.setdefault("cwd", tmp)
    payload.setdefault("session_id", os.path.basename(tmp))
    return subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          cwd=tmp, capture_output=True, text=True, env=env)


def bash(tmp, command, **kw):
    p = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
         "tool_input": {"command": command}}
    p.update(kw)
    return fire(tmp, p)


def delivered(proc):
    """The text Claude Code would actually put in front of the model, or None.

    Anything outside the envelope is invisible, so this returns None for it on
    purpose -- that is the distinction the whole file exists to hold."""
    try:
        out = json.loads(proc.stdout or "{}")
    except ValueError:
        return None
    return (out.get("hookSpecificOutput") or {}).get("additionalContext")


# --------------------------------------------------------------------------

def case_delivery_is_an_envelope_not_bare_stdout(t):
    """Output must arrive as `hookSpecificOutput.additionalContext`.

    The defect, and it shipped: printing the text plainly. It looks right in a
    terminal, it looks right in a test that reads stdout, and the model never
    receives a word of it. Measured directly -- a PostToolUse hook printing
    "append the word PINEAPPLE" to stdout changed nothing, and the same string
    returned in this envelope produced PINEAPPLE."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE, "src/api/keep.py": "x\n"})
    proc = bash(tmp, "cat > src/api/new.py <<'EOF'")
    if proc.returncode != 0:
        return f"hook exited {proc.returncode}: {proc.stderr.strip()!r}"
    if not proc.stdout.strip():
        return "the hook said nothing where a rule matched"
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        return (f"stdout is not JSON, so it goes to the debug log and no "
                f"further: {proc.stdout.strip()[:120]!r}")
    hso = out.get("hookSpecificOutput")
    if not isinstance(hso, dict):
        return f"no hookSpecificOutput envelope: {sorted(out)}"
    if hso.get("hookEventName") != "PreToolUse":
        return f"wrong hookEventName: {hso.get('hookEventName')!r}"
    if not hso.get("additionalContext"):
        return "the envelope carries no additionalContext"
    return None


def case_a_rule_reaches_a_bash_write(t):
    """The gap this hook exists for: Claude Code loads no rule for Bash.

    Measured against a rule scoped to `src/api/**`: Read loads it, Edit loads
    it transitively, and Write-to-a-new-file, Glob, Grep and Bash all load
    nothing."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE, "src/api/keep.py": "x\n"})
    got = delivered(bash(tmp, "mkdir -p src/api && cat > src/api/new.py <<'EOF'"))
    if not got or "validate()" not in got:
        return f"the rule did not reach a bash write: {got!r}"
    return None


def case_a_rule_already_loaded_is_not_repeated(t):
    """`InstructionsLoaded` is what keeps this from duplicating first-party work.

    The defect: injecting on every matching call regardless. Claude Code has
    already loaded the rule on the Read path, so the context window ends up
    with two copies of it -- which reads as an emphasis nobody wrote, and costs
    twice."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE, "src/api/keep.py": "x\n"})
    fire(tmp, {"hook_event_name": "InstructionsLoaded",
               "load_reason": "path_glob_match",
               "file_path": os.path.join(tmp, ".claude/rules/api.md")})
    got = delivered(bash(tmp, "cat > src/api/new.py <<'EOF'"))
    if got and "validate()" in got:
        return "the rule was injected after the native loader had delivered it"
    return None


def case_the_same_rule_is_not_repeated_within_a_session(t):
    """Said once. A hook that repeats itself is a hook that stops being read."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE, "src/api/keep.py": "x\n"})
    first = delivered(bash(tmp, "cat > src/api/a.py <<'EOF'"))
    second = delivered(bash(tmp, "cat > src/api/b.py <<'EOF'"))
    if not (first and "validate()" in first):
        return f"the first touch delivered nothing: {first!r}"
    if second and "validate()" in second:
        return "the same rule was delivered twice in one session"
    return None


def case_an_unconditional_rule_is_never_injected(t):
    """A rule with no `paths:` is loaded at launch by Claude Code itself.

    The defect: treating "no paths" as "matches everything" and injecting it.
    That is a copy of something already in the context window, delivered on
    every single tool call."""
    tmp = make_repo(t, {".claude/rules/all.md": UNCONDITIONAL,
                        "src/api/keep.py": "x\n"})
    got = delivered(bash(tmp, "cat > src/api/new.py <<'EOF'"))
    if got and "already loaded at launch" in got:
        return "an unconditional rule was injected; it is already in context"
    return None


def case_a_write_to_an_existing_file_defers_to_the_loader(t):
    """Write to an existing file required a prior Read, which loaded the rule.

    Only a *new* file is a real gap. Getting this wrong is the duplicate case
    again, reached from the other side."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE,
                        "src/api/there.py": "x\n"})
    existing = delivered(fire(tmp, {
        "hook_event_name": "PreToolUse", "tool_name": "Write",
        "tool_input": {"file_path": os.path.join(tmp, "src/api/there.py")}}))
    if existing and "validate()" in existing:
        return "a rule was injected for a Write to a file that already existed"
    fresh = delivered(fire(tmp, {
        "hook_event_name": "PreToolUse", "tool_name": "Write",
        "tool_input": {"file_path": os.path.join(tmp, "src/api/brand_new.py")}}))
    if not (fresh and "validate()" in fresh):
        return f"no rule was injected for a newly created file: {fresh!r}"
    return None


def case_governs_is_delivered_and_is_path_aware(t):
    """`Governs:` has no loader at all -- this hook is the whole convention.

    The second half is the segment rule that `index/build.py` also implements:
    `Governs: src/bill` must not reach `src/billing_old/`. When those two
    disagreed, a document governed a file in the graph and not in the hook."""
    tmp = make_repo(t, {
        "docs/money.md": "# Money\n\nGoverns: src/bill\n\nHow billing works.\n",
        "src/bill/pay.py": "x\n", "src/billing_old/pay.py": "x\n"})
    inside = delivered(bash(tmp, "sed -i s/a/b/ src/bill/pay.py"))
    if not inside or "docs/money.md" not in inside:
        return f"the governing document was not delivered: {inside!r}"
    # A separate session id on purpose. Reusing one makes the second probe
    # unreachable -- the doc is already in this session's "said that" set, so
    # the case passes whatever `covers` does. It did, until a planted
    # prefix-matching defect failed to turn it red.
    near = delivered(bash(tmp, "sed -i s/a/b/ src/billing_old/pay.py",
                          session_id="second-" + os.path.basename(tmp)))
    if near and "docs/money.md" in near:
        return ("`Governs: src/bill` reached src/billing_old/ — prefix "
                "matching, where build.py matches by path segment")
    return None


def case_silence_when_nothing_matches(t):
    """No match, no output. A hook that speaks on every call is a hook whose
    output stops being read, and then the one time it mattered is missed too."""
    tmp = make_repo(t, {".claude/rules/api.md": RULE, "src/api/keep.py": "x\n"})
    proc = bash(tmp, "cat > lib/other.py <<'EOF'")
    if proc.stdout.strip():
        return f"spoke about an unrelated path: {proc.stdout.strip()[:120]!r}"
    return None


def case_only_paths_inside_the_repository_count(t):
    """A token that resolves outside the root is not this repository's business.

    This is the check that makes URL handling unnecessary: `https://h/src/api/x`
    tokenizes to `https` and `//h/src/api/x`, and the second is an absolute path
    somewhere else. It also covers `../` escapes and absolute paths generally.
    Remove it and a rule fires on another repository's file name.

    The rule here is scoped `**/*.py` on purpose. An anchored glob like
    `src/api/**` cannot match a `../` path anyway, so a case built on one stays
    green with the root check deleted -- which is what a first version of this
    case did."""
    tmp = make_repo(t, {".claude/rules/wide.md": WIDE, "src/api/keep.py": "x\n"})
    for command in ("curl -sSL https://example.com/src/api/thing.py",
                    "cat /elsewhere/src/api/thing.py",
                    "cat ../sibling/src/api/thing.py"):
        proc = bash(tmp, command, session_id=command[:20])
        if proc.stdout.strip():
            return (f"a path outside the repository was matched by "
                    f"{command!r}: {proc.stdout.strip()[:100]!r}")
    return None


def case_a_crash_never_costs_a_tool_call(t):
    """Delivery, not judgment. This hook is wired ahead of every Bash, Write and
    Edit; if a malformed rule file could make it exit non-zero, one bad commit
    would wall off the whole repository. Exit 2 in particular is the code Claude
    Code reads as *block*."""
    tmp = make_repo(t, {".claude/rules/broken.md": "---\npaths:\n  - \"[\"\n---\nx\n",
                        "src/api/keep.py": "x\n"})
    # `tool_input` as a string is the one that actually reaches the outer
    # handler: a malformed rule is caught by the matcher itself, so a case
    # built only from those never exercised the try at all and stayed green
    # against a planted `raise`.
    for payload in ({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                     "tool_input": "not a dict"},
                    {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "cat > src/api/n.py"}},
                    {"hook_event_name": "PreToolUse", "tool_name": "Write"},
                    {"hook_event_name": "InstructionsLoaded", "file_path": 17},
                    {}):
        proc = fire(tmp, payload)
        if proc.returncode != 0:
            return (f"exited {proc.returncode} on {payload.get('tool_name', '-')}"
                    f" — a non-zero exit here blocks the call: "
                    f"{proc.stderr.strip()[:120]!r}")
    return None


CASES = [
    ("delivery is an envelope, not bare stdout",
     case_delivery_is_an_envelope_not_bare_stdout),
    ("a path-scoped rule reaches a bash write",
     case_a_rule_reaches_a_bash_write),
    ("a rule the native loader delivered is not repeated",
     case_a_rule_already_loaded_is_not_repeated),
    ("the same rule is not repeated within a session",
     case_the_same_rule_is_not_repeated_within_a_session),
    ("an unconditional rule is never injected",
     case_an_unconditional_rule_is_never_injected),
    ("a write to an existing file defers to the loader",
     case_a_write_to_an_existing_file_defers_to_the_loader),
    ("Governs: is delivered, and matches by path segment",
     case_governs_is_delivered_and_is_path_aware),
    ("silence when nothing matches", case_silence_when_nothing_matches),
    ("only paths inside the repository count",
     case_only_paths_inside_the_repository_count),
    ("a crash never costs a tool call", case_a_crash_never_costs_a_tool_call),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    if not os.path.exists(HOOK):
        print(f"cannot run: {HOOK} is missing", file=sys.stderr)
        return 2

    failures = []
    for label, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="context-selftest-")
        try:
            problem = fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} of {len(CASES)} context case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    print(f"PASS  {len(CASES)} context case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
