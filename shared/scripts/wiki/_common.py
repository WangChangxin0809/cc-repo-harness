"""What extract.py and replay.py share: finding a repository's transcripts,
walking them as (tool_use, tool_result) pairs, and taking out what must never
reach a committed file.

Run from the plugin, never copied: this module knows where Claude Code keeps
transcripts on a machine, which is nothing a repository should know about.
"""

from __future__ import annotations

import json
import os
import re

# Claude Code files a project's transcripts under ~/.claude/projects/<slug>/,
# where the slug is the working directory with every character that is not a
# letter, digit or hyphen turned into a hyphen. `/home/u/.claude/x` becomes
# `-home-u--claude-x`. Observed, not documented; `transcript_dir` falls back to
# reading `cwd` out of the files when the observation stops holding.
NOT_SLUG = re.compile(r"[^A-Za-z0-9-]")

# The same eight formats as no_committed_credential.py and check_wiki_hygiene.py.
FORMATS = (
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws-key"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "aws-key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]*?"
                r"(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)"), "private-key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "github-token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), "github-token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "slack-token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "api-key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "google-key"),
)
# `TOKEN=...`, `--password ...`, `Authorization: Bearer ...`: the value goes,
# the name stays, because the name is what a pattern is about.
ASSIGNED = re.compile(
    r"((?:api[_-]?key|token|secret|passw(?:or)?d|authorization|bearer)"
    r"[\w-]*\s*[:=]\s*[\"']?)([^\s\"'&;|]{6,})", re.I)

JUDGED_TOOLS = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")


def slug(path):
    return NOT_SLUG.sub("-", os.path.abspath(path))


def projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def transcript_dir(root):
    """The directory holding this repository's transcripts, or None."""
    cand = os.path.join(projects_dir(), slug(root))
    if os.path.isdir(cand):
        return cand
    want = os.path.abspath(root)
    base = projects_dir()
    if not os.path.isdir(base):
        return None
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        for f in transcripts_in(d)[:1]:
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        o = _loads(line)
                        if o and o.get("cwd"):
                            if os.path.abspath(o["cwd"]) == want:
                                return d
                            break
            except OSError:
                continue
    return None


def transcripts_in(directory):
    """Session files, oldest first. Subagent transcripts live beside them as
    `agent-*.jsonl` and are read too: a refusal inside a subagent is a refusal."""
    if not os.path.isdir(directory):
        return []
    out = [os.path.join(directory, n) for n in os.listdir(directory)
           if n.endswith(".jsonl")]
    return sorted(out, key=lambda p: (os.path.getmtime(p), p))


def _loads(line):
    try:
        return json.loads(line)
    except ValueError:
        return None


def entries(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            o = _loads(line)
            if isinstance(o, dict):
                yield o


def blocks(entry):
    m = entry.get("message")
    if not isinstance(m, dict):
        return []
    c = m.get("content")
    return c if isinstance(c, list) else []


def result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


HOOK_ERROR = re.compile(r"^PreToolUse(?::\w+)? hook error: \[(.*?)\]:\s*(.*)$", re.S)
HARNESS_NOISE = ("automode-unavailable", "cancelled")


def refusal(block, entry=None):
    """What said no, if anything did.

    Returns None, or a dict with `by` in
        hook        -- a PreToolUse hook exited 2; `hook` names its script and
                       `reason` is what it printed. This is how a guard's
                       refusal is recorded: not as the guard's text alone but
                       wrapped in `PreToolUse:Bash hook error: [command]: ...`.
        platform    -- the harness itself, e.g. a foreground sleep; the text
                       starts with `Blocked:` and no hook is named.
        classifier  -- auto mode's classifier declined the action.
        user        -- the person declined it in the permission prompt. The
                       strongest label a transcript carries.
    `is_error` is required throughout: the same words inside a *file being
    read* -- a guard's own source -- are not a refusal."""
    if not block.get("is_error"):
        return None
    t = result_text(block).lstrip()
    if t.startswith("<tool_use_error>"):
        t = t[len("<tool_use_error>"):].lstrip()
    kind = (entry or {}).get("toolDenialKind")
    m = HOOK_ERROR.match(t)
    if m:
        cmd = m.group(1)
        script = cmd.split("/")[-1].strip("\"' ") if cmd else "?"
        return {"by": "hook", "hook": script,
                "reason": m.group(2).strip().splitlines()[0] if m.group(2).strip() else ""}
    if kind == "user-rejected" or t.startswith("The user doesn't want to proceed"):
        return {"by": "user", "reason": ""}
    if kind == "automode-blocked":
        return {"by": "classifier", "reason": t.splitlines()[0][:160]}
    if t.startswith("Blocked:"):
        return {"by": "platform", "reason": t.splitlines()[0][:200]}
    return None


def is_refusal(block, entry=None):
    r = refusal(block, entry)
    return bool(r and r["by"] in ("hook", "platform"))


def is_noise(block, entry=None):
    """A failure of the harness, not of the call: the classifier unreachable,
    a hook that timed out, the call cancelled. Counted, never listed -- a
    maintainer shown fifty of these learns nothing about the repository."""
    if not block.get("is_error"):
        return False
    kind = (entry or {}).get("toolDenialKind")
    if kind in HARNESS_NOISE:
        return True
    t = result_text(block)[:160]
    return ("hook did not respond before its timeout" in t
            or "temporarily unavailable" in t)


def redact(text, root=None):
    """Nothing here ever reaches a committed file un-redacted; this is the
    first wall, check_wiki_hygiene.py the second."""
    if not isinstance(text, str):
        return text
    for rx, what in FORMATS:
        text = rx.sub(f"<redacted:{what}>", text)
    text = ASSIGNED.sub(lambda m: m.group(1) + "<redacted>", text)
    if root:
        text = text.replace(os.path.abspath(root) + os.sep, "").replace(
            os.path.abspath(root), ".")
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    return text


def summarise_input(name, tool_input, root, limit=300):
    """The part of a tool call a pattern is about, and nothing else. A Write's
    body is the one thing most likely to carry something private, and a
    pattern about a Write is about *where*, not *what*."""
    ti = tool_input or {}
    if name == "Bash":
        return {"command": redact(str(ti.get("command", ""))[:limit], root)}
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Read"):
        return {"file_path": redact(str(ti.get("file_path")
                                        or ti.get("notebook_path") or ""), root)}
    return {"keys": sorted(str(k) for k in ti)[:8]}


def calls(path):
    """(index, entry, tool_use block, tool_result block or None) for every
    tool call in one transcript, in order; plus the non-tool entries in
    between, so a caller can see what came next. Yields tuples tagged
    'call' | 'user' | 'system'."""
    pending = {}
    seq = []
    for i, e in enumerate(entries(path)):
        t = e.get("type")
        if t == "assistant":
            for b in blocks(e):
                if b.get("type") == "tool_use":
                    rec = {"kind": "call", "i": i, "entry": e, "use": b,
                           "result": None}
                    pending[b.get("id")] = rec
                    seq.append(rec)
        elif t == "user":
            m = e.get("message") or {}
            c = m.get("content")
            got_result = False
            for b in blocks(e):
                if b.get("type") == "tool_result":
                    got_result = True
                    rec = pending.pop(b.get("tool_use_id"), None)
                    if rec:
                        rec["result"] = b
                        rec["result_entry"] = e
                elif b.get("type") == "text":
                    seq.append({"kind": "user", "i": i, "entry": e,
                                "text": b.get("text", "")})
            if isinstance(c, str) and not got_result:
                seq.append({"kind": "user", "i": i, "entry": e, "text": c})
        elif t == "system":
            seq.append({"kind": "system", "i": i, "entry": e})
    return seq
