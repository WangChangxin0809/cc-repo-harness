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

`on_stop.py` is covered here too, and its two load-bearing properties are the
ones nothing else could have caught: it **fails open**, which is the inverse of
every other check in the tree, and it short-circuits on `stop_hook_active`. Both
break silently -- a broken fail-open traps the session, a broken short-circuit
makes it unstoppable -- and neither shows up in normal use until it does.
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
ON_STOP = os.path.join(HERE, "on_stop.py")

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
# on_stop.py

STUB = """\
import sys
sys.stderr.write({msg!r})
sys.exit({code})
"""


def stop_repo(tmp, checks):
    """A scaffolded layout with stub gates, because on_stop.py finds them by
    walking up from its own file. Copied rather than run in place: the real
    gates would judge this fixture, and the cases are about how their exit
    codes are read, not about what they say."""
    ctx = os.path.join(tmp, "scripts", "context")
    gates = os.path.join(tmp, "scripts", "gates")
    os.makedirs(ctx); os.makedirs(gates)
    shutil.copy(ON_STOP, os.path.join(ctx, "on_stop.py"))
    for name, (code, msg) in checks.items():
        with open(os.path.join(gates, name), "w", encoding="utf-8") as fh:
            fh.write(STUB.format(code=code, msg=msg))
    subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
    return os.path.join(ctx, "on_stop.py")


def stop(script, tmp, **payload):
    return subprocess.run([sys.executable, script], input=json.dumps(payload),
                          cwd=tmp, capture_output=True, text=True)


def case_a_judged_failure_blocks_the_stop(t):
    """Exit 1 from a check is a judged failure and must hold the turn open,
    with the check's own output handed back -- the remedy is in there, and a
    block with no reason is a block the agent cannot act on."""
    script = stop_repo(t, {"check_docs_index.py": (1, "ROUTING IS BROKEN")})
    proc = stop(script, t)
    if proc.returncode != 2:
        return f"a red tree did not block the stop: exit {proc.returncode}"
    if "ROUTING IS BROKEN" not in proc.stderr:
        return f"the check's own output was swallowed: {proc.stderr.strip()!r}"
    return None


def case_cannot_judge_never_blocks_a_stop(t):
    """**The inversion.** Everywhere else in this tree exit 2 means "could not
    judge" and is never a pass. Here it must pass, because a Stop hook that
    blocks on something it cannot see makes the session impossible to end. The
    two costs are not comparable: a false block is an agent that cannot stop, a
    false pass is a red tree CI catches minutes later."""
    script = stop_repo(t, {"check_docs_index.py": (2, "cannot see the docs")})
    proc = stop(script, t)
    if proc.returncode != 0:
        return (f"exit 2 from a check blocked the stop (exit "
                f"{proc.returncode}) — that traps the session on a condition "
                f"nobody can see")
    return None


def case_stop_hook_active_short_circuits(t):
    """Without it, an unfixable defect is an unbreakable loop: the agent is
    asked to fix it, stops, is blocked again, forever."""
    script = stop_repo(t, {"check_docs_index.py": (1, "STILL BROKEN")})
    proc = stop(script, t, stop_hook_active=True)
    if proc.returncode != 0:
        return (f"blocked a stop that was already this hook's own retry: exit "
                f"{proc.returncode} — this is the unbreakable-loop case")
    return None


def case_a_missing_check_is_not_a_failure(t):
    """Tiers. A repository can carry this hook and not every gate it names, and
    an absent file must not read as a red one."""
    script = stop_repo(t, {})
    proc = stop(script, t)
    if proc.returncode != 0:
        return f"an absent gate was treated as a failure: exit {proc.returncode}"
    return None


def case_a_green_tree_ends_the_turn(t):
    """The other direction. A hook that blocks on everything is switched off in
    a week and takes the working half with it."""
    script = stop_repo(t, {"check_docs_index.py": (0, ""),
                           "check_docs_layout.py": (0, "")})
    proc = stop(script, t)
    if proc.returncode != 0:
        return f"a green tree still blocked the stop: exit {proc.returncode}"
    if proc.stderr.strip():
        return f"spoke on a green tree: {proc.stderr.strip()[:100]!r}"
    return None


# --------------------------------------------------------------------------
# before_write.py

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



# --------------------------------------------------------------------------
# same_turn.py

SAME_TURN = os.path.join(os.path.dirname(HOOK), "same_turn.py")


def beside(tmp, code, says="what the check said"):
    """A directory holding a file and a `selftest.py` that exits `code`."""
    d = os.path.join(tmp, "work", "guards")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "thing.py"), "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    with open(os.path.join(d, "selftest.py"), "w", encoding="utf-8") as fh:
        fh.write("import sys\nprint(%r)\nsys.exit(%d)\n" % (says, code))
    return os.path.join(d, "thing.py")


def edit(tmp, path):
    return subprocess.run(
        [sys.executable, SAME_TURN],
        input=json.dumps({"hook_event_name": "PostToolUse",
                          "tool_name": "Edit",
                          "tool_input": {"file_path": path}}),
        cwd=tmp, capture_output=True, text=True)


def case_a_red_check_beside_the_edit_blocks(t):
    """The rung itself. A check that judged and went red must reach the model
    while the reasoning that produced the edit is still there -- which means
    exit 2 and stderr, because that is the channel that arrives."""
    proc = edit(t, beside(t, 1, "GUARD STOPPED REFUSING"))
    if proc.returncode != 2:
        return "a red check beside the edit did not block: exit %d" % proc.returncode
    if "GUARD STOPPED REFUSING" not in proc.stderr:
        return "the check's own output was swallowed: %r" % proc.stderr.strip()
    return None


def case_a_green_check_says_nothing(t):
    """A rung that speaks on every edit is a rung people switch off."""
    proc = edit(t, beside(t, 0))
    if proc.returncode != 0:
        return "a green check blocked: exit %d" % proc.returncode
    if proc.stderr.strip() or delivered(proc):
        return "spoke on a green check: %r" % (proc.stderr.strip()
                                               or delivered(proc))
    return None


def case_could_not_judge_informs_and_does_not_block(t):
    """The distinction this file is built on, in its second place.

    Exit 2 is COULD NOT JUDGE. Blocking on it leaves the agent no way forward
    -- it cannot fix a check that did not run -- but staying silent makes an
    unchecked edit indistinguishable from a checked one. So it is told, on the
    channel that arrives, and not blocked on."""
    proc = edit(t, beside(t, 2, "no interpreter for that"))
    if proc.returncode != 0:
        return "could-not-judge blocked the turn: exit %d" % proc.returncode
    got = delivered(proc)
    if not got:
        return "an unchecked edit was passed over in silence"
    if "could not judge" not in got:
        return "the abstention did not say what it was: %r" % got
    return None


def case_a_directory_with_no_selftest_is_silent(t):
    """The rule is "the check beside the file", and most files have none.

    A hook that complained about every directory without a selftest would be
    telling a repository to adopt a layout, which is not what this measures."""
    d = os.path.join(t, "src")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "app.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    proc = edit(t, path)
    if proc.returncode != 0 or proc.stderr.strip() or delivered(proc):
        return "spoke about a directory with no check in it"
    return None


def case_a_document_is_not_run_against_a_selftest(t):
    """A `.md` beside a `selftest.py` is not code that selftest verifies.

    Without this, editing a note in `guards/` runs the guard suite -- seconds
    paid for an edit that could not have broken it."""
    path = beside(t, 1, "SHOULD NOT RUN")
    doc = os.path.join(os.path.dirname(path), "NOTES.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("Some prose.\n")
    proc = edit(t, doc)
    if proc.returncode != 0:
        return "editing a document ran the code's selftest: exit %d" % proc.returncode
    return None


CASES = [
    ("a red check beside the edit blocks", case_a_red_check_beside_the_edit_blocks),
    ("a green check says nothing", case_a_green_check_says_nothing),
    ("could not judge informs and does not block",
     case_could_not_judge_informs_and_does_not_block),
    ("a directory with no selftest is silent",
     case_a_directory_with_no_selftest_is_silent),
    ("a document is not run against a selftest",
     case_a_document_is_not_run_against_a_selftest),
    ("a judged failure blocks the stop", case_a_judged_failure_blocks_the_stop),
    ("could not judge never blocks a stop", case_cannot_judge_never_blocks_a_stop),
    ("stop_hook_active short-circuits", case_stop_hook_active_short_circuits),
    ("a missing check is not a failure", case_a_missing_check_is_not_a_failure),
    ("a green tree ends the turn", case_a_green_tree_ends_the_turn),
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
    for path in (HOOK, ON_STOP):
        if not os.path.exists(path):
            print(f"cannot run: {path} is missing", file=sys.stderr)
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
