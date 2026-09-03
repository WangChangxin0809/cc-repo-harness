#!/usr/bin/env python3
"""Gate: the wiki stays a record, and nothing else gets in.

    python3 scripts/gates/check_wiki_hygiene.py [--root .]

    0 = well-formed, or there is no wiki    1 = malformed, dangling, or leaking
    2 = cannot judge (a wiki file could not be read)

## What `.claude/wiki/` is

The plugin's `/learn` reads the session transcripts on the machine that ran
it and writes what keeps going wrong into `patterns/`, one file per recurring
mistake. `index.md` is the catalogue, `logs.md` the run log, `impact.md` the
table of every proposal that came out of a pattern. It is committed, so a team
shares it, and it is read by nobody during a session: an agent handed its own
failure catalogue does worse, not better (WikiSkill, arXiv 2608.27454).

A record that nobody reads while working is only useful if it stays a record.
Three ways it stops being one, each a check here:

1. **A pattern without its fields.** `count`, `sessions`, `route` and `status`
   are what make a pattern actionable: how often, when, what kind of thing
   would stop it, and whether that thing exists yet. Missing any of them, the
   file is a note, and notes are what `consolidating-notes` exists to clear.
2. **A shipped pattern pointing nowhere.** `status: shipped` claims a guard,
   gate or rule exists at `ships:`. When that file is renamed or deleted, the
   claim stays behind and the pattern reads as handled. It is not.
3. **A secret.** The maintainer reads transcripts, and a refused command can
   carry a token. Redaction happens upstream, in the extractor; this is the
   second wall, and it uses the same eight formats `no_committed_credential`
   refuses. Kept in two places on purpose: a tier-A guard and a tier-B gate
   cannot import each other in a repository that installed only one.

No wiki at all is 0, not 2. A repository that has not run `/learn` has nothing
to judge and nothing wrong.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

WIKI = os.path.join(".claude", "wiki")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
ROUTES = ("guard", "gate", "prose", "none")
STATUSES = ("open", "proposed", "shipped", "retired")

# The same list as no_committed_credential.py, for the reason given above.
FORMATS = (
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "an AWS temporary access key id"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "a private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "a GitHub personal access token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), "a GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "an API secret key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "a Google API key"),
)


def fields(block):
    """`key: value` pairs, with `key:` followed by `- item` lines read as a
    list and `[a, b]` read as one too. Enough YAML for a frontmatter the
    maintainer writes; not a YAML parser."""
    out, key = {}, None
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                out[key] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
            elif val == "":
                out[key] = []
            else:
                out[key] = val
            continue
        m = re.match(r"^\s+-\s+(.*)$", line)
        if m and key is not None and isinstance(out.get(key), list):
            out[key].append(m.group(1).strip())
    return out


def check_pattern(root, rel, text, out):
    m = FRONTMATTER.match(text)
    f = fields(m.group(1)) if m else {}
    missing = []
    count = f.get("count")
    if not (isinstance(count, str) and count.isdigit() and int(count) >= 1):
        missing.append("count (a whole number, at least 1)")
    if not (isinstance(f.get("sessions"), list) and f["sessions"]):
        missing.append("sessions (a list of dates or ids, at least one)")
    if f.get("route") not in ROUTES:
        missing.append("route (" + " | ".join(ROUTES) + ")")
    if f.get("status") not in STATUSES:
        missing.append("status (" + " | ".join(STATUSES) + ")")
    body = text[m.end():] if m else text
    if not re.search(r"^#\s+\S", body, re.M):
        missing.append("a heading naming the trigger")
    if missing:
        out.append(f"{rel} is missing its fields:\n"
                   + "".join(f"    {x}\n" for x in missing)
                   + "  Without them it is a note, not a pattern. The maintainer\n"
                     "  writes all four; a hand edit that drops one turns the\n"
                     "  catalogue back into the pile it came from.")
    if f.get("status") == "shipped":
        ships = f.get("ships")
        if not isinstance(ships, str) or not ships:
            out.append(f"{rel} is shipped but names no `ships:` path.")
        elif not os.path.exists(os.path.join(root, ships)):
            out.append(f"{rel} is shipped but there is nothing at {ships}.\n"
                       "  The guard, gate or rule was renamed or removed and the\n"
                       "  pattern still reads as handled. Point `ships:` at the\n"
                       "  file, or set `status: open`.")


def check_secrets(rel, text, out):
    for rx, what in FORMATS:
        if rx.search(text):
            out.append(f"{rel} contains a credential-shaped string: {what}.\n"
                       "  The wiki is committed and shared. The extractor should\n"
                       "  have replaced it; remove it here and fix the extractor.")
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    wiki = os.path.join(root, WIKI)
    if not os.path.isdir(wiki):
        return 0

    failures = []
    files = sorted(glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True))
    texts = {}
    for path in files:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                texts[rel] = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"cannot judge: {rel} could not be read ({exc})",
                  file=sys.stderr)
            return 2

    if ".claude/wiki/index.md" not in texts:
        failures.append(
            ".claude/wiki/ has no index.md.\n"
            "  The index is what tells a reader what this directory is and\n"
            "  that no agent is meant to read it. Without it the patterns are\n"
            "  loose files that look like documentation.")

    for rel, text in texts.items():
        if rel.startswith(".claude/wiki/patterns/"):
            check_pattern(root, rel, text, failures)
        check_secrets(rel, text, failures)

    if not failures:
        return 0
    for f in failures:
        print(f, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
