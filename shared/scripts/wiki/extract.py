#!/usr/bin/env python3
"""Turn a repository's session transcripts into the events a maintainer reads.

    python3 wiki/extract.py --root REPO [--since YYYY-MM-DD] [--sessions N]
                            [--transcripts DIR] [--out packet.json]
                            [--digest digest.md]
    python3 wiki/extract.py --from packet.json --match REGEX [--kind KIND]
    python3 wiki/extract.py --selftest

    0 = a packet was written    2 = cannot judge (no transcripts found)

## Why a packet and not the transcripts

A transcript is every token that passed through a session. One here runs to
fifty megabytes; the maintainer's context does not. WikiSkill samples traces
to fit; this does something narrower, because a coding session is not a
benchmark rollout with one answer at the end. The signal that a repository
keeps tripping an agent is a handful of event kinds, and each is recognisable
without a model:

- a **refusal** -- something said no before the call ran: a PreToolUse hook
  (a guard, recorded as `PreToolUse:Bash hook error: [script]: Blocked: ...`),
  the harness itself, or auto mode's classifier. What the agent did *next* is
  recorded with it, because a guard that is obeyed and one that is routed
  around are different findings.
- a **decline** -- the person said no in the permission prompt. The strongest
  label a transcript carries, and the rarest.
- an **error** -- a tool call ran and failed. Exit code, first line, and
  whether the same call was tried again unchanged. Failures of the harness
  rather than the call -- the classifier unreachable, a hook timing out -- are
  counted and not listed; fifty of them teach nothing about the repository.
- a **stop** -- the Stop hook held the turn, or a stop hook broke.
- a **user message** -- the strongest label there is, and the one no script
  can classify. Kept short and handed over as is; the maintainer decides
  which are corrections. Notifications and IDE chatter (`<task-notification>`,
  `<ide_selection>`) are dropped.

Nothing else is kept. In particular no assistant text, no file contents, no
tool output beyond a first line: the wiki is committed, the transcript is
not, and the extractor is the first of the two walls between them.

## Reading a packet back

`--from ... --match` is the second mode, and it exists for the proposer: given
a packet and a regular expression, it prints every event whose tool input
matches, as JSON. That is how one pattern's own instances are recovered from
a run that recorded thousands of calls -- the cases a candidate guard must
refuse, and the near misses beside them that it must not.

## Redaction

Absolute paths under the repository become relative; the home directory
becomes `~`; the eight credential formats `no_committed_credential.py` knows
become `<redacted:kind>`; `TOKEN=...`-shaped assignments keep the name and
lose the value. A Write's body is never copied at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import (calls, is_noise, redact, refusal, result_text,  # noqa: E402
                     summarise_input, transcript_dir, transcripts_in)

EXIT_CODE = re.compile(r"[Ee]xit code[:\s]+(\d+)")
NOISE = ("<task-notification>", "<ide_selection>", "<ide_opened_file>",
         "<system-reminder>", "<command-name>", "<local-command")
USER_LIMIT = 240
LINE_LIMIT = 200


def first_line(text, limit=LINE_LIMIT):
    """The first line that says something. A failed Bash call's result opens
    with `Exit code N` and the message is underneath; the first run of the
    maintainer read eighty-two errors that all said `Exit code 1` and could
    make nothing of them."""
    t = text.lstrip()
    if t.startswith("<tool_use_error>"):
        t = t[len("<tool_use_error>"):].lstrip()
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    for l in lines:
        if not EXIT_CODE.match(l):
            return l[:limit]
    return lines[0][:limit] if lines else ""


def what_next(seq, k, this_use):
    """What the agent did after call k: the next tool call, unless the user
    spoke first."""
    for rec in seq[k + 1:]:
        if rec["kind"] == "user":
            return "user_intervened"
        if rec["kind"] != "call":
            continue
        nxt = rec["use"]
        if nxt.get("name") != this_use.get("name"):
            return "moved_on"
        a, b = this_use.get("input") or {}, nxt.get("input") or {}
        if this_use.get("name") == "Bash":
            ca, cb = a.get("command", ""), b.get("command", "")
            if ca == cb:
                return "retried_same"
            if ca.split()[:1] == cb.split()[:1]:
                return "retried_changed"
            return "moved_on"
        if a.get("file_path") == b.get("file_path"):
            return "retried_changed" if a != b else "retried_same"
        return "moved_on"
    return "session_ended"


def session_events(path, root):
    seq = calls(path)
    ses = {"file": os.path.basename(path), "id": None, "started": None,
           "ended": None, "branch": None, "entries": 0, "tools": {},
           "compactions": 0, "api_errors": 0, "harness_failures": 0,
           "refusals": [], "declined": [], "errors": [], "stops": [], "user": []}
    for k, rec in enumerate(seq):
        e = rec["entry"]
        ts = e.get("timestamp")
        if ts:
            ses["started"] = ses["started"] or ts
            ses["ended"] = ts
        ses["id"] = ses["id"] or e.get("sessionId")
        ses["branch"] = ses["branch"] or e.get("gitBranch")
        if rec["kind"] == "system":
            sub = e.get("subtype")
            if sub == "compact_boundary":
                ses["compactions"] += 1
            elif sub == "api_error":
                ses["api_errors"] += 1
            elif sub == "stop_hook_summary":
                if e.get("preventedContinuation") or e.get("hookErrors"):
                    ses["stops"].append({
                        "at": ts, "held": bool(e.get("preventedContinuation")),
                        "reason": redact(first_line(str(e.get("stopReason") or "")), root),
                        "hook_errors": [redact(first_line(str(x)), root)
                                        for x in (e.get("hookErrors") or [])][:3]})
            continue
        if rec["kind"] == "user":
            text = rec["text"].strip()
            if not text or any(text.startswith(n) for n in NOISE):
                continue
            ses["user"].append({"at": ts, "text": redact(text[:USER_LIMIT], root),
                                "after": _last_tool(seq, k)})
            continue
        use, res = rec["use"], rec["result"]
        name = use.get("name", "?")
        ses["tools"][name] = ses["tools"].get(name, 0) + 1
        if res is None:
            continue
        text = result_text(res)
        rentry = rec.get("result_entry") or {}
        who = refusal(res, rentry)
        if who and who["by"] == "user":
            ses["declined"].append({
                "at": ts, "tool": name,
                "input": summarise_input(name, use.get("input"), root),
                "next": what_next(seq, k, use)})
        elif who:
            ses["refusals"].append({
                "at": ts, "tool": name, "by": who["by"],
                "hook": who.get("hook"),
                "input": summarise_input(name, use.get("input"), root),
                "reason": redact(who["reason"][:LINE_LIMIT], root),
                "sidechain": bool(e.get("isSidechain")),
                "next": what_next(seq, k, use)})
        elif is_noise(res, rentry):
            ses["harness_failures"] += 1
        elif res.get("is_error"):
            m = EXIT_CODE.search(text)
            ses["errors"].append({
                "at": ts, "tool": name,
                "input": summarise_input(name, use.get("input"), root),
                "exit": int(m.group(1)) if m else None,
                "line": redact(first_line(text), root),
                "next": what_next(seq, k, use)})
    ses["entries"] = len(seq)
    return ses


def _last_tool(seq, k):
    for rec in reversed(seq[:k]):
        if rec["kind"] == "call":
            return rec["use"].get("name")
    return None


def build(root, files, since=None):
    sessions = []
    for f in files:
        try:
            ses = session_events(f, root)
        except OSError:
            continue
        if since and ses["started"] and ses["started"][:10] < since:
            continue
        sessions.append(ses)
    totals = {"sessions": len(sessions),
              "refusals": sum(len(s["refusals"]) for s in sessions),
              "declined": sum(len(s["declined"]) for s in sessions),
              "harness_failures": sum(s["harness_failures"] for s in sessions),
              "errors": sum(len(s["errors"]) for s in sessions),
              "stops": sum(len(s["stops"]) for s in sessions),
              "user": sum(len(s["user"]) for s in sessions),
              "calls": sum(sum(s["tools"].values()) for s in sessions)}
    return {"root": os.path.abspath(root), "since": since,
            "sessions": sessions, "totals": totals}


KINDS = ("refusals", "declined", "errors")


def find(packet, rx, kinds=KINDS):
    """Every recorded event whose tool input matches. The input is matched,
    not the reason: a pattern is about what was attempted, and matching the
    refusal text would only ever find what some guard already says."""
    out = []
    for ses in packet["sessions"]:
        for kind in kinds:
            for e in ses.get(kind, []):
                blob = json.dumps(e.get("input", {}), ensure_ascii=False)
                if rx.search(blob):
                    out.append(dict(e, kind=kind, session=ses["file"],
                                    date=(ses["started"] or "")[:10]))
    return out


def _show(ev):
    i = ev["input"]
    return i.get("command") or i.get("file_path") or ",".join(i.get("keys", []))


def digest(packet, examples=3):
    """The packet as a maintainer reads it: grouped, counted, with a few
    examples each, and every user message in order. Markdown, so it can be
    read whole; the JSON stays beside it for the detail."""
    ss = packet["sessions"]
    t = packet["totals"]
    days = sorted(x["started"][:10] for x in ss if x["started"])
    out = [f"# Events from {t['sessions']} session(s) of {packet['root']}",
           f"{days[0] if days else '?'} .. {days[-1] if days else '?'}. "
           f"{t['calls']} tool calls; {t['refusals']} refusals; {t['declined']} "
           f"declined by the user; {t['errors']} errors; {t['stops']} stops; "
           f"{t['user']} user messages; {t['harness_failures']} harness "
           f"failures (counted, not listed)."]

    def group(kind, key):
        groups = {}
        for x in ss:
            for ev in x[kind]:
                groups.setdefault(key(ev), []).append((x, ev))
        return sorted(groups.items(), key=lambda kv: -len(kv[1]))

    out.append("\n## Refusals, grouped by what said no\n")
    for k, evs in group("refusals", lambda e: (e["by"], e.get("hook") or "", e["reason"][:90])):
        nxt = {}
        for _, e in evs:
            nxt[e["next"]] = nxt.get(e["next"], 0) + 1
        by = k[0] + (f" {k[1]}" if k[1] else "")
        out.append(f"- **{len(evs)}×** [{by}] {k[2]}  · next: "
                   + ", ".join(f"{a} {b}" for a, b in sorted(nxt.items())))
        for x, e in evs[:examples]:
            out.append(f"    - {e['at'][:10] if e['at'] else '?'} {x['file'][:8]} "
                       f"{e['tool']}: `{_show(e)[:110]}`")
    out.append("\n## Declined by the user\n")
    for x in ss:
        for e in x["declined"]:
            out.append(f"- {e['at'][:10] if e['at'] else '?'} {x['file'][:8]} "
                       f"{e['tool']}: `{_show(e)[:110]}` · next: {e['next']}")
    out.append("\n## Errors, grouped by tool, exit code and first line\n")
    for k, evs in group("errors", lambda e: (e["tool"], e["exit"], e["line"][:70])):
        nxt = {}
        for _, e in evs:
            nxt[e["next"]] = nxt.get(e["next"], 0) + 1
        out.append(f"- **{len(evs)}×** {k[0]} exit {k[1]}: {k[2]}  · next: "
                   + ", ".join(f"{a} {b}" for a, b in sorted(nxt.items())))
        for x, e in evs[:examples]:
            out.append(f"    - {e['at'][:10] if e['at'] else '?'} {x['file'][:8]}: "
                       f"`{_show(e)[:110]}`")
    out.append("\n## Stops\n")
    for x in ss:
        for e in x["stops"]:
            out.append(f"- {e['at'][:10] if e['at'] else '?'} {x['file'][:8]} "
                       f"{'held' if e['held'] else 'hook error'}: {e['reason']} "
                       + " ".join(e["hook_errors"]))
    out.append("\n## User messages, in order\n")
    for x in ss:
        if not x["user"]:
            continue
        out.append(f"\n### {x['file'][:8]} · {x['started'][:10] if x['started'] else '?'}"
                   f" · branch {x['branch'] or '?'} · {sum(x['tools'].values())} calls\n")
        for e in x["user"]:
            line = e["text"].replace("\n", " ")
            out.append(f"- ({e['after'] or 'start'}) {line}")
    return "\n".join(out) + "\n"


# --- selftest ----------------------------------------------------------------

def _fixture(tmp, root):
    """One session with each event kind once, plus the near miss that must
    not count: the word Blocked inside a file being *read*."""
    def use(i, name, inp, ts):
        return {"type": "assistant", "timestamp": ts, "sessionId": "s1",
                "gitBranch": "main", "cwd": root,
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}

    def result(i, text, err=False, extra=None):
        e = {"type": "user", "timestamp": "2026-09-01T10:00:00Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": f"t{i}",
                  "content": text, "is_error": err}]}}
        e.update(extra or {})
        return e

    tok = "ghp_" + "A" * 36
    lines = [
        use(1, "Bash", {"command": f"git push origin main | tail -1  # {tok}"},
            "2026-09-01T10:00:00Z"),
        result(1, "PreToolUse:Bash hook error: [python3 \"${CLAUDE_PROJECT_DIR}/scripts/guards/dispatch.py\"]: "
                  "Blocked: git push origin main piped into tail.\n\nInstead:\n    git push origin main\n",
               err=True, extra={"toolDenialKind": "permission-rule"}),
        use(2, "Bash", {"command": "git push origin main"}, "2026-09-01T10:00:05Z"),
        result(2, "Everything up-to-date"),
        use(3, "Bash", {"command": f"pytest {root}/tests -q"}, "2026-09-01T10:01:00Z"),
        result(3, "Exit code 1\nFAILED tests/test_a.py::test_x", err=True),
        use(4, "Bash", {"command": f"pytest {root}/tests -q"}, "2026-09-01T10:01:30Z"),
        result(4, "Exit code 1\nFAILED tests/test_a.py::test_x", err=True),
        {"type": "user", "timestamp": "2026-09-01T10:02:00Z",
         "message": {"role": "user", "content": "不对，先看日志再改。"}},
        {"type": "user", "timestamp": "2026-09-01T10:02:01Z",
         "message": {"role": "user", "content": "<task-notification>done</task-notification>"}},
        use(5, "Read", {"file_path": f"{root}/scripts/guards/no_piped_outbound.py"},
            "2026-09-01T10:03:00Z"),
        result(5, "1\t#!/usr/bin/env python3\n2\t'''Blocked: is what this prints'''\n"),
        use(6, "Write", {"file_path": f"{root}/notes.md",
                         "content": f"password=hunter22 {tok}"}, "2026-09-01T10:04:00Z"),
        result(6, "<tool_use_error>Blocked: notes.md is not where notes go.\n", err=True),
        use(7, "Bash", {"command": "git push --force origin main"}, "2026-09-01T10:04:30Z"),
        result(7, "The user doesn't want to proceed with this tool use.", err=True,
               extra={"toolDenialKind": "user-rejected"}),
        use(8, "Edit", {"file_path": f"{root}/a.py"}, "2026-09-01T10:04:40Z"),
        result(8, "claude-x is temporarily unavailable (connection failed), so auto mode cannot determine the safety of Edit right now.",
               err=True, extra={"toolDenialKind": "automode-unavailable"}),
        {"type": "system", "subtype": "stop_hook_summary", "timestamp": "2026-09-01T10:05:00Z",
         "preventedContinuation": True, "stopReason": "docs/index.md routes to every document",
         "hookErrors": []},
        {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-09-01T10:06:00Z"},
    ]
    d = os.path.join(tmp, "projects", "-x")
    os.makedirs(d)
    with open(os.path.join(d, "s1.jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")
    return d


def selftest(verbose=False):
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "repo")
        os.makedirs(root)
        d = _fixture(tmp, root)
        packet = build(root, transcripts_in(d))
        text = json.dumps(packet, ensure_ascii=False)
        s = packet["sessions"][0]

        def expect(cond, what):
            (failures if not cond else []).append(what)
            if verbose:
                print(("ok   " if cond else "FAIL ") + what)

        expect(len(s["refusals"]) == 2, "two refusals, and only two: the Read "
               "of a file containing the word is not one")
        expect(s["refusals"][0]["by"] == "hook" and s["refusals"][0]["hook"] == "dispatch.py"
               and s["refusals"][0]["reason"].startswith("Blocked: git push"),
               "a hook refusal names the script and keeps the guard's first line")
        expect(s["refusals"][0]["next"] == "retried_changed",
               "after the first refusal the agent obeyed the replacement")
        expect(s["refusals"][1]["by"] == "platform" and s["refusals"][1]["next"] == "moved_on",
               "the second refusal is the harness's own, and the agent moved on")
        expect(len(s["declined"]) == 1 and "force" in s["declined"][0]["input"]["command"],
               "the user's decline is its own kind")
        expect(s["harness_failures"] == 1 and len(s["errors"]) == 2,
               "the classifier being unreachable is counted, not listed")
        hits = find(packet, re.compile(r"git push"))
        expect(len(hits) == 2 and {h["kind"] for h in hits} == {"refusals", "declined"}
               and all("git push" in h["input"]["command"] for h in hits),
               "--match finds a pattern's instances across every event kind")
        expect(find(packet, re.compile("Blocked")) == [],
               "--match reads the attempt, not the refusal text")
        d = digest(packet)
        expect("**1×** [hook dispatch.py] Blocked: git push" in d and "不对" in d
               and "ghp_" not in d, "the digest groups, keeps the user, and leaks nothing")
        expect(len(s["errors"]) == 2 and s["errors"][0]["exit"] == 1
               and s["errors"][0]["next"] == "retried_same",
               "a failing command retried unchanged is recorded as such")
        expect(s["errors"][0]["line"].startswith("FAILED tests/test_a.py"),
               "the error line is the message under the exit code, not the code")
        expect(len(s["stops"]) == 1 and s["stops"][0]["held"],
               "the Stop hook holding the turn is a stop")
        expect(len(s["user"]) == 1 and s["user"][0]["text"].startswith("不对"),
               "the user's correction is kept, the task notification is not")
        expect("ghp_" not in text, "the token is gone from every field")
        # The packet's own `root` field is the one place the path belongs.
        inside = json.dumps(packet["sessions"], ensure_ascii=False)
        expect(root not in inside and "pytest tests -q" in inside,
               "absolute paths under the repository became relative")
        expect("hunter22" not in text, "a Write's body is never copied")
        expect(s["compactions"] == 1 and s["tools"].get("Bash") == 5,
               "the counts are right")
        expect(packet["totals"]["calls"] == 8, "the totals add up")
    for f in failures:
        print("FAIL " + f, file=sys.stderr)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--transcripts", help="read this directory instead of "
                    "the machine's transcript store")
    ap.add_argument("--since", help="only sessions started on or after "
                    "this date, YYYY-MM-DD")
    ap.add_argument("--sessions", type=int, help="only the last N sessions")
    ap.add_argument("--out", help="write the packet here (default: stdout)")
    ap.add_argument("--digest", help="also write the maintainer's markdown "
                    "digest here")
    ap.add_argument("--from", dest="packet", help="read a packet back "
                    "instead of the transcripts, and query it with --match")
    ap.add_argument("--match", help="regular expression over a recorded "
                    "tool input; prints the matching events as JSON")
    ap.add_argument("--kind", choices=KINDS + ("all",), default="all")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.verbose)

    if a.packet:
        if not a.match:
            print("cannot judge: --from needs --match", file=sys.stderr)
            return 2
        try:
            with open(a.packet, encoding="utf-8") as fh:
                packet = json.load(fh)
            rx = re.compile(a.match)
        except (OSError, ValueError, re.error) as exc:
            print(f"cannot judge: {exc}", file=sys.stderr)
            return 2
        kinds = KINDS if a.kind == "all" else (a.kind,)
        hits = find(packet, rx, kinds)
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        print(f"{len(hits)} event(s) matched {a.match!r}", file=sys.stderr)
        return 0

    root = os.path.abspath(a.root)
    d = a.transcripts or transcript_dir(root)
    if not d:
        print(f"cannot judge: no transcripts for {root} under "
              f"{os.path.join(os.path.expanduser('~'), '.claude', 'projects')}",
              file=sys.stderr)
        return 2
    files = transcripts_in(d)
    if not files:
        print(f"cannot judge: {d} holds no .jsonl", file=sys.stderr)
        return 2
    if a.sessions:
        files = files[-a.sessions:]
    packet = build(root, files, a.since)
    if not packet["sessions"]:
        print("cannot judge: every session is older than --since",
              file=sys.stderr)
        return 2
    body = json.dumps(packet, ensure_ascii=False, indent=1)
    if a.digest:
        with open(a.digest, "w", encoding="utf-8") as fh:
            fh.write(digest(packet))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(body + "\n")
        t = packet["totals"]
        print(f"{t['sessions']} session(s), {t['calls']} tool calls: "
              f"{t['refusals']} refusals, {t['declined']} declined, "
              f"{t['errors']} errors, {t['stops']} stops, {t['user']} user "
              f"messages, {t['harness_failures']} harness failures -> {a.out}"
              + (f", digest -> {a.digest}" if a.digest else ""))
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
