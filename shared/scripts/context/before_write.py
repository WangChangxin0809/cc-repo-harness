#!/usr/bin/env python3
"""Deliver what governs a path, at the moment that path is about to be touched.

Wire on two events -- the state one writes is what the other reads:

    PreToolUse          matcher "Bash|Write|Edit|MultiEdit"
    InstructionsLoaded  matcher "path_glob_match"

Two sources of path-scoped knowledge, one delivery:

  1. **`.claude/rules/*.md` with `paths:` frontmatter.** First-party format,
     first-party loader -- which reaches only some of the ways a path gets
     touched. This fills the rest.
  2. **`Governs:` in a document's first lines.** No loader at all; the whole
     convention is delivered here or nowhere.

Both answer the same question -- *what should I know before changing this?* --
so they arrive together, before the change, in one message.

## The rules gap, measured rather than assumed

A rule carrying `paths:` loads when Claude *reads* a matching file. That is the
only trigger. Measured against a rule scoped to `src/api/**`, with an
`InstructionsLoaded` hook as the instrument:

    Read           loaded
    Edit           loaded   -- transitively; Edit forces a prior Read
    Write (new)    NOT loaded
    Glob           NOT loaded
    Grep           NOT loaded
    Bash           NOT loaded   -- `cat`, and a heredoc write, both

So conventions meant to guide a region are absent at the two moments they are
worth most: creating a file there, and writing one through the shell. This is
not an oversight nobody has noticed -- anthropics/claude-code#38487 asked for
the Write half and was auto-closed stale, after #23478 was closed NOT_PLANNED
and #27861 and #36334 were closed as duplicates. Four requests, no movement.
Treat today's behaviour as permanent and work around it.

## Why the rules half only speaks where the loader is silent

Injecting a rule the loader already delivered puts two copies of it in one
context window, which reads as an emphasis nobody wrote. So the rules half
stays quiet on `Edit`, and on a `Write` to a file that already exists -- a Write
to an existing file required a prior Read, and that Read already loaded the
rule.

That split is also what makes an approximate matcher safe here. **The globbing
below does not have to agree with Claude Code's**, because it runs only where
the native loader does nothing: a disagreement makes this hook slightly
chattier or slightly quieter, and can never contradict a rule that did load.

The `Governs:` half has no such constraint and fires on every touched path,
because nothing else delivers it.

## What this cannot do

- **One round trip is lost on a first touch.** `PreToolUse` hands its context
  to the model together with the result of the call that triggered it, so the
  command was already composed. Observed behaviour is that the agent complies
  on the retry. That is worth one turn against knowledge that otherwise never
  arrives -- but it is not prevention, and a rule that must not be violated
  belongs in a guard, which can refuse.
- **Bash paths are recovered by reading the command text.** A file written by a
  subprocess (`python build.py`) is invisible. The native loader recovers zero
  paths from Bash, so best-effort is strictly more than nothing, and strictly
  less than exact.
- **It says a thing once per session, and does not repeat it after a
  compaction.** A path-scoped rule that Claude Code loaded reappears the next
  time a matching file is read; an injected one does not, and the dedup state
  is keyed on the session, which outlives the context window.

  That is a decision, not an oversight. Repeating is the main way a hook stops
  being read, and the alternative -- re-announcing whenever the context might
  have dropped -- trades a rare miss for a constant noise. The miss is also
  already covered: a convention lost this way produces a wrong file, and a
  wrong file is what gates are for. Delivery is best-effort by construction and
  nothing load-bearing should be resting on it.

## Why `additionalContext` and not stdout

Because stdout does not arrive. Measured: a `PostToolUse` hook printing
`append the word PINEAPPLE to your reply` to stdout changed nothing, and the
same text returned as `additionalContext` produced PINEAPPLE. Plain stdout is
context only for `UserPromptSubmit`, `UserPromptExpansion` and `SessionStart`;
everywhere else it goes to the debug log.

This file replaces `context/after_edit.py`, which printed to stdout on
`PostToolUse` and therefore delivered nothing to anyone for its whole life --
the failure our own rule warns about, in the direction nobody tests. Its second
half, a one-hop repo-graph neighbour list, is *not* carried over: that answers
"what did I just affect", which is a different question asked at a different
moment, and it belongs in a component that has a reason to stay quiet.

A repository that keeps `.claude/rules/` and drops this file loses the Bash and
create coverage and still has a valid, first-party `.claude/rules/`. Nothing
here invents a format.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

RULES_DIRNAME = os.path.join(".claude", "rules")

GOVERNS = re.compile(r"^Governs:\s*(.+)$", re.M)
# Must equal index/build.py's window. It did not once: this scanned 40 lines and
# the graph builder scanned 60, so a `Governs:` on line 50 created an edge in
# the graph and produced no hint here -- the convention half-worked, in a
# direction nobody would think to test. These two files cannot share a constant
# (they install at different tiers and one is often absent), so the index
# selftest asserts they agree instead.
GOVERNS_HEAD = 60

MAX_RULES_INJECTED = 3          # a wall of rules is read as none of them
MAX_DOCS_ANNOUNCED = 2
MAX_CHARS = 4000                # ~1k tokens; past that the cost outruns the hint
MAX_RULE_FILES = 200            # a runaway directory must not stall a tool call
MAX_DOCS_SCANNED = 500

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


# --------------------------------------------------------------------------
# rule frontmatter

def rule_paths(text):
    """The `paths:` globs one rule file declares, or [] if it has none.

    A rule with no `paths:` is loaded at launch by Claude Code itself, at the
    same priority as `.claude/CLAUDE.md`. It is already present; returning []
    keeps this hook from injecting a second copy of it.
    """
    m = FRONTMATTER.match(text)
    if not m:
        return []
    body = m.group(1)
    # `[^\S\n]*` and not `\s*`: `\s` matches the newline, so a list written on
    # the following lines was read as an inline value and every `-` bullet came
    # back as a glob named "-".
    m2 = re.search(r"^paths:[^\S\n]*(.*)$", body, re.M)
    if not m2:
        return []
    inline = m2.group(1).strip()
    if inline and inline not in ("|", ">"):
        return [g for g in re.findall(r'["\']([^"\']+)["\']|([^,\s\[\]]+)',
                                      inline)
                for g in [g[0] or g[1]] if g]
    out = []
    for line in body[m2.end():].splitlines():
        if re.match(r"^\S", line):          # the next top-level key ends the list
            break
        item = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if item:
            out.append(item.group(1).strip("\"'"))
    return out


# --------------------------------------------------------------------------
# globs

def expand_braces(pattern):
    """`a.{ts,tsx}` -> ['a.ts', 'a.tsx']. One group at a time, recursively."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(pattern[:m.start()] + alt + pattern[m.end():]))
        if len(out) > 100:                  # the docs cap expansion too
            break
    return out


def glob_to_regex(pattern):
    """`**` crosses separators; `*` and `?` do not. Everything else is literal."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(r"\A" + "".join(out) + r"\Z")


def matches(globs, rel):
    for g in globs:
        for expanded in expand_braces(g.lstrip("./")):
            try:
                if glob_to_regex(expanded).match(rel):
                    return True
            except re.error:
                continue
    return False


# --------------------------------------------------------------------------
# Governs:

def covers(target, rel):
    """Whether a `Governs:` target covers this path.

    Must agree with `governed_by` in scripts/index/build.py exactly. Two
    implementations of one convention is already one too many; two that
    *disagree* means a document governs a file in the graph and not in the
    hook, which is indistinguishable from the convention not working."""
    t = target.rstrip("*")
    if t.endswith("/"):
        return rel.startswith(t)
    return rel == t or rel.startswith(t + "/")


def markdown_files(root):
    """Every tracked markdown file, not just docs/.

    This once walked `docs/` only, while build.py indexed every tracked
    markdown. A `Governs:` line in ARCHITECTURE.md or a skill therefore made a
    real edge in the graph and was invisible here -- the delivery moment the
    convention exists for. Same set on both sides, or the convention is a coin
    flip."""
    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode == 0:
        return [p for p in out.stdout.split("\0") if p][:MAX_DOCS_SCANNED]
    docs = os.path.join(root, "docs")          # not a git repo: best effort
    return [os.path.relpath(os.path.join(d, n), root)
            for d, _, names in os.walk(docs) for n in names
            if n.endswith(".md")][:MAX_DOCS_SCANNED]


def governing_docs(root, rels):
    """Documents whose `Governs:` target covers any of these paths.

    Reading head bytes inline is cheap enough; an index for it would be a
    second source of truth that can go stale."""
    hits = []
    for doc in markdown_files(root):
        try:
            with open(os.path.join(root, doc), encoding="utf-8",
                      errors="replace") as fh:
                head = "".join(fh.readlines()[:GOVERNS_HEAD])
        except OSError:
            continue
        for spec in GOVERNS.findall(head):
            targets = [t for t in re.split(r"[,\s]+", spec.strip()) if t]
            if any(covers(t, rel) for t in targets for rel in rels):
                hits.append(doc)
                break
    return sorted(set(hits))


# --------------------------------------------------------------------------
# what the tool call is about to touch

FLAGGISH = re.compile(r"\A-")
PATHISH = re.compile(r"[A-Za-z0-9_@.+\-/]+")


def paths_from_bash(command):
    """Path-like tokens in a shell command. Best effort, and says so.

    Redirections, heredoc targets and plain arguments all land here because all
    three are just tokens; telling them apart would buy accuracy this hook does
    not need. Over-matching costs a rule shown for a path that was only
    mentioned, which is cheap. Under-matching costs the whole point.

    URLs need no special handling and once had some, wrongly. `:` is not a path
    character, so `https://h/a.py` tokenizes to `https` and `//h/a.py` -- and
    the second is an *absolute* path, which `touched` drops for resolving
    outside the repository root. Stripping URLs here as well looked like
    defence in depth and was dead code justified by a comment that overstated
    it: no input reached the strip that the root check did not already hold."""
    out = []
    for tok in PATHISH.findall(command or ""):
        tok = tok.strip("'\"")
        if not tok or FLAGGISH.match(tok):
            continue
        if "/" in tok or re.search(r"\.[A-Za-z0-9]{1,8}\Z", tok):
            out.append(tok)
    return out


def touched(payload, root):
    """(paths, rules_gap) — what this call touches, and whether the native
    loader is blind to it.

    `rules_gap` is False exactly where Claude Code already delivers a matching
    rule: an `Edit`, or a `Write` to a file that already exists. `Governs:` is
    delivered either way, because nothing else delivers it at all."""
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    if tool == "Bash":
        raw, gap = paths_from_bash(ti.get("command")), True
    else:
        p = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
        if not p:
            return [], False
        raw = [p]
        absolute = p if os.path.isabs(p) else os.path.join(root, p)
        gap = tool == "Write" and not os.path.exists(absolute)
    rels = []
    for p in raw:
        ap = os.path.normpath(p if os.path.isabs(p) else os.path.join(root, p))
        if ap.startswith(root + os.sep):
            rels.append(os.path.relpath(ap, root).replace(os.sep, "/"))
    return rels, gap


# --------------------------------------------------------------------------
# per-session state: what the model has already been told

def state_path(payload):
    sid = re.sub(r"[^A-Za-z0-9_.\-]", "",
                 str(payload.get("session_id") or ""))[:80] or "nosession"
    d = os.path.join(tempfile.gettempdir(), "claude-before-write")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, sid + ".json")


def load_state(payload):
    try:
        with open(state_path(payload), encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError):
        return set()


def save_state(payload, seen):
    try:
        with open(state_path(payload), "w", encoding="utf-8") as fh:
            json.dump(sorted(seen), fh)
    except OSError:
        pass


# --------------------------------------------------------------------------
# events

def project_root(payload):
    root = (os.environ.get("CLAUDE_PROJECT_DIR")
            or payload.get("cwd") or os.getcwd())
    return os.path.normpath(os.path.abspath(root))


def on_instructions_loaded(payload):
    """Record a rule the native loader delivered, so this hook does not repeat
    it. This is the whole reason the two events share one file: the state
    written here is the only thing that keeps the other half from duplicating
    first-party work."""
    path = payload.get("file_path")
    if not path:
        return 0
    seen = load_state(payload)
    seen.add(os.path.normpath(os.path.abspath(path)))
    save_state(payload, seen)
    return 0


def matching_rules(root, rels, seen):
    """(rel, body) for each rule scoped to one of these paths, not yet seen."""
    rules_dir = os.path.join(root, RULES_DIRNAME)
    if not os.path.isdir(rules_dir):
        return []
    chosen, budget, scanned = [], MAX_CHARS, 0
    for dirpath, _, names in os.walk(rules_dir):
        for name in sorted(names):
            if not name.endswith(".md") or len(chosen) >= MAX_RULES_INJECTED:
                continue
            scanned += 1
            if scanned > MAX_RULE_FILES:
                return chosen
            full = os.path.normpath(os.path.join(dirpath, name))
            if full in seen:
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            globs = rule_paths(text)
            if not globs or not any(matches(globs, r) for r in rels):
                continue
            body = FRONTMATTER.sub("", text).strip()
            if not body or len(body) > budget:
                continue
            budget -= len(body)
            chosen.append((full, body))
    return chosen


def on_pre_tool_use(payload):
    root = project_root(payload)
    rels, rules_gap = touched(payload, root)
    if not rels:
        return 0
    seen = load_state(payload)

    blocks, now_seen = [], set()
    if rules_gap:
        for full, body in matching_rules(root, rels, seen):
            blocks.append("--- %s ---\n%s"
                          % (os.path.relpath(full, root).replace(os.sep, "/"),
                             body))
            now_seen.add(full)

    for doc in governing_docs(root, rels):
        full = os.path.normpath(os.path.join(root, doc))
        if full in seen or len(now_seen) >= MAX_RULES_INJECTED + MAX_DOCS_ANNOUNCED:
            continue
        blocks.append("%s declares `Governs:` over this path — it states how "
                      "this code is meant to work. Read it before assuming."
                      % doc)
        now_seen.add(full)

    if not blocks:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext":
            "Written down about the path this call touches:\n\n"
            + "\n\n".join(blocks),
    }}))
    save_state(payload, seen | now_seen)
    return 0


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    try:
        event = payload.get("hook_event_name")
        if event == "InstructionsLoaded":
            return on_instructions_loaded(payload)
        if event == "PreToolUse":
            return on_pre_tool_use(payload)
    except Exception:
        # Delivery, not judgment. A crash here must never cost a tool call.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
