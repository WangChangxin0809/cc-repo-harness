#!/usr/bin/env python3
"""Find documents that no longer describe the code they claim authority over.

    python3 scripts/drift.py pairs    [--root .] [--json]
    python3 scripts/drift.py prepare  [--root .] [--out .drift] [--all]
    python3 scripts/drift.py report   [--out .drift]
    python3 scripts/drift.py selftest [--verbose]

    0 = done   1 = findings need review (report)   2 = cannot judge

## Why this exists, and why it is not a gate

`check_docs_runnable.py` catches a document whose commands would not run. That
is the mechanical half of drift and it is the smaller half. The other half needs
judgement: a document describing a bug that was fixed, stating a threshold the
code no longer uses, or denying the existence of a measurement that has since
been taken. Every one of those was found in this repository by reading, and no
check here could have found any of them.

Judgement cannot be a gate. A gate that is sometimes wrong gets disabled within
a week, and drift findings are *claims that two things disagree*, not proof that
either is wrong. So this prepares the work and collects the answers; it never
decides.

## Why the unit is a `Governs:` pair

A pass over "the documentation" is a summarising job and produces summarising
output. `Governs:` narrows it to a named pair -- this document asserts it
describes that code -- and a disagreement inside a pair is a specific, checkable
claim. In this repository that is six pairs instead of forty documents.

## The triage is free

Git already knows whether the code moved after the document did. Pairs where no
governed file has changed since the document's last commit are not suspects, and
skipping them is the difference between a pass you run and one you do not. It is
a prior, not a verdict: a document can be wrong on the day it is written.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

GOVERNS = re.compile(r"^Governs:\s*(.+)$", re.M)
GOVERNS_HEAD = 60          # must equal index/build.py; the index selftest holds it
PACKET_BYTES = 120_000     # per pair; what is cut is always reported

BRIEF = """\
# Drift review

One packet per pair. Each holds a document and the code it claims to describe.

## The question

For each concrete claim the document makes about that code — a threshold, a
flag, an exit code, a filename, a described behaviour, a stated limitation —
does the code still do that?

## The rule that matters most

Report **"these two disagree"**. Never report "the document is wrong".

A document encodes intent, and intent legitimately runs ahead of code: a rule
the team decided and has not implemented, a limitation recorded before it was
removed, a design described so somebody builds it. A pass that silently aligns
documents to code deletes exactly that material, reads beautifully afterwards,
and is unrecoverable. Which side is wrong is a human decision, and often the
answer is that the code should change.

## What counts

* a threshold, count, or window that differs from the code's constant
* a flag, subcommand, path, or filename the code does not have
* behaviour described that the code no longer has — especially a **workaround
  for a defect that has since been fixed**, which reads as correct forever
* a limitation or open question the document states and the repository has since
  closed, including elsewhere in the repository
* an inventory the document presents as complete and is not

## What does not

* wording, tone, ordering, or anything you would call an improvement
* anything you cannot point at a specific line of code to support
* the document being shorter than you would have written it

Silence is a valid result. A pair with nothing to report gets an empty findings
file, and that is worth more than a list of things somebody could have phrased
differently.

## Output

Write findings to `findings/<packet name>`. One finding per section:

    ## <the claim, quoted from the document>

    Document: <path>:<line>
    Code:     <path>:<line>
    They disagree because: <one or two sentences>
    Which is wrong: <document | code | cannot tell from here>
"""


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def tracked(root):
    out = sh(["git", "-c", "core.quotePath=false", "ls-files"], root)
    return out.stdout.split() if out.returncode == 0 else None


def last_commit_time(root, path):
    out = sh(["git", "log", "-1", "--format=%ct", "--", path], root)
    try:
        return int(out.stdout.strip())
    except ValueError:
        return 0


def covers(target, rel):
    """Same segment-aware rule as index/build.py and context/before_write.py.

    Prefix matching would make `Governs: src/bill` cover `src/billing_old/`, and
    an over-broad claim reads as though somebody documented that code."""
    t = target.rstrip("*").rstrip("/")
    return rel == t or rel.startswith(t + "/")


def pairs(root):
    """[(doc, [governed files], [files newer than the doc])], docs first."""
    files = tracked(root)
    if files is None:
        return None
    out = []
    for doc in sorted(f for f in files if f.endswith(".md")):
        try:
            with open(os.path.join(root, doc), encoding="utf-8",
                      errors="replace") as fh:
                head = "".join(fh.readlines()[:GOVERNS_HEAD])
        except OSError:
            continue
        targets = [t for spec in GOVERNS.findall(head)
                   for t in re.split(r"[,\s]+", spec.strip()) if t]
        if not targets:
            continue
        governed = sorted({f for t in targets for f in files if covers(t, f)})
        if not governed:
            # A target resolving to nothing is drift too, and build.py already
            # reports it as dangling. Not repeated here.
            continue
        doc_time = last_commit_time(root, doc)
        newer = [f for f in governed
                 if last_commit_time(root, f) > doc_time]
        out.append((doc, governed, newer))
    return out


def slug(doc):
    return re.sub(r"[^a-z0-9]+", "-", doc.lower().replace(".md", "")).strip("-")


def cmd_pairs(root, as_json):
    found = pairs(root)
    if found is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2
    if not found:
        print("no Governs: pairs — nothing claims authority over anything.\n"
              "See the writing-docs skill; without them documents and code are\n"
              "two disconnected components.")
        return 0
    if as_json:
        import json
        print(json.dumps([{"doc": d, "governed": g, "newer": n}
                          for d, g, n in found], indent=2))
        return 0

    suspects = [p for p in found if p[2]]
    for doc, governed, newer in found:
        mark = "SUSPECT" if newer else "  ok   "
        print(f"{mark} {doc}   ({len(newer)}/{len(governed)} governed files "
              f"changed after the document)")
        for f in newer:
            print(f"            {f}")
    print(f"\n{len(suspects)} of {len(found)} pairs worth reading. This is a "
          f"prior, not a verdict:\na document can be wrong on the day it is "
          f"written, and `--all` reviews every pair.")
    return 0


def cmd_prepare(root, out, review_all):
    found = pairs(root)
    if found is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2
    chosen = [p for p in found if review_all or p[2]]
    if not chosen:
        print("nothing to review: no governed file has changed since its "
              "document.\nUse --all to review every pair anyway.")
        return 0

    packets = os.path.join(out, "packets")
    findings = os.path.join(out, "findings")
    if os.path.exists(packets):
        shutil.rmtree(packets)
    os.makedirs(packets)
    os.makedirs(findings, exist_ok=True)
    with open(os.path.join(out, "BRIEF.md"), "w", encoding="utf-8") as fh:
        fh.write(BRIEF)

    truncated = []
    for i, (doc, governed, newer) in enumerate(chosen, 1):
        # The changed files first: they are why this pair is here at all, and
        # they are what survives the budget when a pair is too large.
        ordered = newer + [f for f in governed if f not in newer]
        name = f"{i:02d}-{slug(doc)}.md"
        body = [f"# {doc}\n", f"Governs {len(governed)} file(s); "
                f"{len(newer)} changed after the document.\n",
                "\n## The document\n", "```markdown"]
        body.append(read(root, doc))
        body.append("```\n")
        used, cut = 0, []
        for f in ordered:
            text = read(root, f)
            if used + len(text) > PACKET_BYTES:
                cut.append(f)
                continue
            used += len(text)
            tag = "  (changed after the document)" if f in newer else ""
            body.append(f"\n## {f}{tag}\n")
            body.append(f"```\n{text}\n```\n")
        if cut:
            # A packet that silently drops half its inputs produces a review
            # that reads as complete coverage of something never looked at.
            body.append(f"\n## Not included — packet budget\n\n"
                        f"{len(cut)} file(s) exceeded {PACKET_BYTES} bytes and "
                        f"are NOT in this packet:\n\n"
                        + "".join(f"- {f}\n" for f in cut))
            truncated.append((name, len(cut)))
        with open(os.path.join(packets, name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(body))

    print(f"brief     {os.path.join(out, 'BRIEF.md')}")
    print(f"packets   {packets}  ({len(chosen)} pair(s))")
    print(f"findings  {findings}  (empty — the review writes here)")
    for name, n in truncated:
        print(f"  truncated: {name} omits {n} file(s) over the packet budget")
    print("\nNext: for each packet, a subagent reads BRIEF.md and that packet,\n"
          "and writes findings/<same name>. Then: drift.py report")
    return 0


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8",
                  errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def cmd_report(out):
    packets = os.path.join(out, "packets")
    findings = os.path.join(out, "findings")
    if not os.path.isdir(packets):
        print(f"cannot judge: no packets in {out} — run `drift.py prepare` first",
              file=sys.stderr)
        return 2
    expected = sorted(f for f in os.listdir(packets) if f.endswith(".md"))
    written = (sorted(f for f in os.listdir(findings) if f.endswith(".md"))
               if os.path.isdir(findings) else [])
    missing = [f for f in expected if f not in written]
    if missing:
        # Not the same as "no drift". A packet nobody reviewed is an unknown,
        # and reporting it as clean is how a review pass becomes decoration.
        print(f"cannot judge: {len(missing)} of {len(expected)} packet(s) have "
              f"no findings file:", file=sys.stderr)
        for f in missing:
            print(f"  {f}", file=sys.stderr)
        print("\nAn unreviewed packet is an unknown, not a clean result. Write "
              "an empty\nfile to record that a pair was read and had nothing.",
              file=sys.stderr)
        return 2

    total, quiet = 0, []
    for name in expected:
        text = read(findings, name).strip()
        if not text:
            quiet.append(name)
            continue
        n = len(re.findall(r"^## ", text, re.M))
        total += n
        print(f"\n=== {name}  ({n} finding(s))\n")
        print(text)
    print(f"\n{total} finding(s) across {len(expected) - len(quiet)} pair(s); "
          f"{len(quiet)} pair(s) read and quiet.")
    if total:
        print("\nEach is a disagreement, not a verdict. Decide which side moves "
              "— often\nit is the code, and a document describing intent the "
              "code has not caught\nup to is the most valuable kind there is.")
    return 1 if total else 0


# --- selftest ---------------------------------------------------------------

def _repo(tmp, files):
    for rel, body in files.items():
        p = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(p) or tmp, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    sh(["git", "init", "-q"], tmp)
    return tmp


def _commit(tmp, when):
    env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    sh(["git", "add", "-A"], tmp)
    subprocess.run(["git", "-c", "user.email=s@e.x", "-c", "user.name=s",
                    "commit", "-qm", "x"], cwd=tmp, env=env,
                   capture_output=True)


def case_code_newer_is_suspect(t):
    """A governed file committed after its document must be flagged."""
    _repo(t, {"docs/a.md": "# A\n\nGoverns: src/a.py\n",
              "src/a.py": "X = 1\n"})
    _commit(t, "2020-01-01T00:00:00")
    with open(os.path.join(t, "src/a.py"), "w") as fh:
        fh.write("X = 2\n")
    _commit(t, "2021-01-01T00:00:00")
    found = pairs(t)
    if not found or found[0][2] != ["src/a.py"]:
        return f"expected src/a.py flagged as newer, got {found}"
    return None


def case_doc_newer_is_quiet(t):
    """The reverse must NOT be flagged, or every pair is a suspect forever."""
    _repo(t, {"docs/a.md": "# A\n\nGoverns: src/a.py\n",
              "src/a.py": "X = 1\n"})
    _commit(t, "2020-01-01T00:00:00")
    with open(os.path.join(t, "docs/a.md"), "a") as fh:
        fh.write("\nMore.\n")
    _commit(t, "2021-01-01T00:00:00")
    found = pairs(t)
    if not found or found[0][2]:
        return f"document is newer than its code; should be quiet, got {found}"
    return None


def case_governs_is_segment_aware(t):
    """`Governs: src/bill` must not drag in `src/billing_old/`.

    The same defect the index had. Two implementations of one convention that
    disagree is how a repository ends up with an edge and no hint."""
    _repo(t, {"docs/a.md": "# A\n\nGoverns: src/bill\n",
              "src/bill/x.py": "X = 1\n", "src/billing_old/y.py": "Y = 1\n"})
    _commit(t, "2020-01-01T00:00:00")
    found = pairs(t)
    if not found:
        return "no pair found"
    if "src/billing_old/y.py" in found[0][1]:
        return f"over-matched into src/billing_old/: {found[0][1]}"
    if "src/bill/x.py" not in found[0][1]:
        return f"did not cover the directory it names: {found[0][1]}"
    return None


def case_unreviewed_packet_cannot_judge(t):
    """A packet with no findings file must exit 2, never report clean.

    Reporting an unreviewed pair as having no drift is how this becomes
    decoration -- the number goes up, the reading never happened."""
    _repo(t, {"docs/a.md": "# A\n\nGoverns: src/a.py\n", "src/a.py": "X = 1\n"})
    _commit(t, "2020-01-01T00:00:00")
    out = os.path.join(t, ".drift")
    if cmd_prepare(t, out, True) != 0:
        return "prepare failed"
    rc = cmd_report(out)
    if rc != 2:
        return f"expected exit 2 for an unreviewed packet, got {rc}"
    name = sorted(os.listdir(os.path.join(out, "packets")))[0]
    open(os.path.join(out, "findings", name), "w").close()
    if cmd_report(out) != 0:
        return "an empty findings file should read as reviewed-and-quiet"
    return None


def case_truncation_is_reported(t):
    """A packet over budget must name what it dropped, inside the packet."""
    files = {"docs/a.md": "# A\n\nGoverns: src/\n"}
    for i in range(4):
        files[f"src/f{i}.py"] = "# pad\n" * 12000
    _repo(t, files)
    _commit(t, "2020-01-01T00:00:00")
    out = os.path.join(t, ".drift")
    cmd_prepare(t, out, True)
    name = sorted(os.listdir(os.path.join(out, "packets")))[0]
    body = read(os.path.join(out, "packets"), name)
    if "Not included — packet budget" not in body:
        return "packet exceeded the budget and did not say what it omitted"
    return None


CASES = [
    ("code newer than its document is a suspect", case_code_newer_is_suspect),
    ("a document newer than its code is quiet", case_doc_newer_is_quiet),
    ("Governs: matches by path segment", case_governs_is_segment_aware),
    ("an unreviewed packet cannot judge", case_unreviewed_packet_cannot_judge),
    ("a truncated packet says what it dropped", case_truncation_is_reported),
]


def cmd_selftest(verbose):
    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    failures = []
    for label, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="drift-selftest-")
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                problem = fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif verbose:
            print(f"  ok  {label}")
    if failures:
        print(f"{len(failures)} of {len(CASES)} drift case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if verbose:
        print(f"{len(CASES)} drift cases held")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["pairs", "prepare", "report", "selftest"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=".drift")
    ap.add_argument("--all", action="store_true",
                    help="review every pair, not only the ones git suspects")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if a.command == "selftest":
        return cmd_selftest(a.verbose)
    if a.command == "pairs":
        return cmd_pairs(root, a.json)
    out = a.out if os.path.isabs(a.out) else os.path.join(root, a.out)
    if a.command == "prepare":
        os.makedirs(out, exist_ok=True)
        return cmd_prepare(root, out, a.all)
    return cmd_report(out)


if __name__ == "__main__":
    sys.exit(main())
