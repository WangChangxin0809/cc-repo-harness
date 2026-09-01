#!/usr/bin/env python3
"""Where a document promises something the code does not do.

    python3 assess/promises.py --root .                 # what is testable
    python3 assess/promises.py --brief RUN.json         # round one: write tests
    python3 assess/promises.py --check RUN.json --tests T.json --work W
    python3 assess/promises.py --brief2 CHECKED.json    # round two: write code
    python3 assess/promises.py --grade CHECKED.json --impls I.json --work W

Exit codes:
    0 = a round completed
    2 = cannot judge (nothing testable, or a round it cannot run)

## Why asking a model to compare them does not work

The obvious design is to hand a model the document and the code and ask where
they disagree. It has been tried and measured, and the false-positive rate
makes it unusable: a model reads the ordinary gap between high-level prose and
detailed implementation as a contradiction, so most of what comes back is a
paragraph that is *less specific* than the code rather than wrong about it.

CASCADE (arXiv:2604.19400) replaces the comparison with an experiment, and
the experiment is what this module is:

1. An agent writes **several tests** from the document alone, never having
   read the implementation. The paper generates 8.4 per method on average,
   5 to 20 per function, and the count is not incidental -- the decision in
   step 4 is arithmetic over a set and cannot be taken from one test.
2. The tests run against the real code. All passing ends it.
3. Any failing is not yet a finding, because a test may simply be wrong. So
   the agent writes an implementation from the same document, still without
   reading the real one, and **the same tests** run against that.
4. The two runs are crossed:

| | meaning |
|---|---|
| `p2p` | passed on both |
| `f2f` | failed on both -- the test was wrong |
| `f2p` | failed on the real code, passed on the document's -- evidence |
| `p2f` | passed on the real code, failed on the document's -- **a warning about the document's code** |

An inconsistency is reported only when **`f2p > 0` and `p2f == 0`**.

`p2f == 0` is the guard, and it is the part of this design that is easiest to
drop and most expensive to lose. A `p2f` means the implementation written from
the document is *worse* than the real one on something the tests already
covered -- so it is incomplete, and its passing of the `f2p` tests is no
longer evidence of anything. Without that condition the method degrades into
"an LLM said the code was wrong", which is the design being replaced: the
paper measures the naive comparison at **0.53 precision**, roughly 27 false
positives per 71 real ones.

## Two numbers to keep in view

CASCADE reports **precision 0.88, recall 0.21**. It finds about a fifth of the
inconsistencies that are there, and is right about seven of eight it reports.
That trade is the right one for this page -- a finding must be real or nobody
will read the next one -- but it means **an empty result says almost nothing**,
and the row has to say so rather than reading as a clean bill.

Both numbers are also measured on method-level Javadoc against a single Java
method. This module's input is prose documentation across a whole repository,
which is a harder problem in every direction, so 0.88 is an upper bound we
have no claim on.

## What the machine contributes

Not the judgement -- the narrowing. A repository's documents contain thousands
of sentences and almost none of them are testable: a claim needs to name
something executable and assert something checkable about it. This finds the
ones that do, so an agent is spent writing tests for claims that can have
tests rather than reading prose to discover that most cannot.

## What this costs, and why it is off by default

Two agent rounds and up to two suite runs per claim, against mutation's one
run per mutant. It is the dearest thing on the page. `--promises N` is opt-in
for the same reason `--mutate N` is: the caller is the only one who can bound
it.

Everything runs in a throwaway clone. The agent's test and the agent's
implementation are both code this repository did not write, and neither ever
touches the subject.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TEST_TIMEOUT = 300

SKIP_DIRS = ("node_modules", "vendor", "venv", "dist", "build", "target",
             "__pycache__", "third_party", "fixtures", "testdata")

# A claim needs a subject that can be executed and a predicate that can be
# checked. These are the shapes that carry both.
_EXIT_CODE = re.compile(r"\bexit(?:s| code| status)?\s+(\d+)\b", re.I)
_FLAG = re.compile(r"(--[a-z][\w-]{1,30})")
_DEFAULT = re.compile(r"\bdefaults?\s+(?:to|is)\s+`?([\w./-]+)`?", re.I)
_CALLABLE = re.compile(r"`([a-z_][a-z0-9_]*)\(\)`|`([\w./-]+\.py)`")
_MODAL = re.compile(r"\b(must|never|always|refuses?|returns?|writes?|exits?|"
                    r"defaults?|raises?|blocks?|rejects?)\b", re.I)

_FENCE = re.compile(r"^```", re.M)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(300_000)
    except OSError:
        return ""


def _tracked(root):
    r = subprocess.run(["git", "ls-files"], cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {x.strip() for x in (r.stdout or "").splitlines() if x.strip()}


def _sentences(text):
    """Prose sentences, with fenced blocks removed.

    A fence is an example, not a promise. It is also the place a document is
    most likely to be literally correct, so testing fences would spend the
    budget on the claims least likely to be wrong."""
    out, fenced = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for chunk in re.split(r"(?<=[.!?])\s+", line):
            chunk = chunk.strip(" -*|#")
            if 30 <= len(chunk) <= 400:
                out.append(chunk)
    return out


def claims(root):
    """Sentences that name something executable and assert something checkable.

    Everything here is narrowing. Nothing is judged, and a claim reaching the
    output means only that a test could be written for it."""
    keeps = _tracked(root)
    found, seen = [], set()
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            if not name.endswith((".md", ".rst", ".txt")):
                continue
            rel = os.path.relpath(os.path.join(base, name), root)
            rel = rel.replace(os.sep, "/")
            if keeps is not None and rel not in keeps:
                continue
            for sentence in _sentences(_read(os.path.join(base, name))):
                if not _MODAL.search(sentence):
                    continue
                subjects = set()
                for m in _CALLABLE.finditer(sentence):
                    subjects.add(m.group(1) or m.group(2))
                subjects |= set(_FLAG.findall(sentence))
                if not subjects:
                    continue
                kind = ("exit code" if _EXIT_CODE.search(sentence) else
                        "default value" if _DEFAULT.search(sentence) else
                        "behaviour")
                key = (rel, sentence[:80])
                if key in seen:
                    continue
                seen.add(key)
                found.append({"id": len(found) + 1, "doc": rel,
                              "says": sentence, "names": sorted(subjects),
                              "kind": kind})
    # An exit code or a documented default is a promise with one right answer;
    # a behaviour claim is a promise an agent has to interpret. Ordering by
    # that puts the claims whose tests are least arguable first, so a caller
    # who asks for five gets the five most testable rather than the five that
    # happened to be near the top of the tree.
    rank = {"exit code": 0, "default value": 1, "behaviour": 2}
    found.sort(key=lambda c: (rank[c["kind"]], c["doc"]))
    for i, c in enumerate(found, 1):
        c["id"] = i
    return found


BRIEF_ONE = """\
# Round one: write a test from the document, without reading the code

Below are sentences from this repository's own documentation that name
something executable and assert something checkable about it.

**Do not open the implementation.** That is not a formality, it is the
experiment. A test written after reading the code tests the code; a test
written from the document alone tests the promise, and only the second can
show that the two have come apart.

For each claim you can test, write **several small tests, not one** -- five to
twenty, around eight is typical. This is not thoroughness for its own sake:
the decision at the end is arithmetic across the set, and a single test cannot
produce it. Tests that pass on the real code are as necessary as the ones that
fail, because they are what will catch an implementation that satisfies the
sentence by breaking everything else.

Each test is a self-contained Python file that

* exercises **one** thing the sentence promises, not what you assume around it,
* exits **0** when that holds and **non-zero** when it does not,
* imports or invokes the named thing by the path the document gives,
* prints one line saying what it checked, so a person reading the run can see
  what the exit code meant.

Skip any claim you cannot test from the document alone -- a sentence too vague
to test is a finding about the sentence, and saying so is more useful than a
test that asserts something the document never said.

## What happens next, so you can calibrate

Your tests run against the real code. All passing ends it. Any failing and you
will be asked to write an implementation from the same sentence, after which
the same tests run against yours and the two runs are crossed. A contradiction
is reported only when some test goes fail-to-pass **and none goes
pass-to-fail** -- so a test that is merely wrong costs nothing and reports
nothing, and neither does an implementation that only looks right.

## Answer

    {"tests": [{"claim_id": 1,
                "targets": "path/to/the/file/the/claim/is/about.py",
                "cases": [{"name": "exits_two_when_it_cannot_see",
                           "source": "...the whole file..."},
                          {"name": "exits_zero_on_a_clean_tree",
                           "source": "..."}]},
               {"claim_id": 2, "skip": "why it cannot be tested from prose"}]}

`targets` is the file an implementation would replace in round two. Get it
from the document, not from the tree.

## Claims
"""

BRIEF_TWO = """\
# Round two: write the implementation the document describes

Each claim below has a test you wrote from the document, and **the real code
failed it**. That is not yet a finding: the test may be wrong.

So write the implementation the sentence describes, from the sentence alone,
still without reading the real one. Your test then runs against yours.

Two conditions decide it, and the second is the one worth writing for:

* some test must go **fail-to-pass** -- the document described something the
  real code does not do and yours does;
* **no** test may go **pass-to-fail**. A test the real code passed and yours
  fails means your implementation is incomplete, and an incomplete
  implementation's successes prove nothing. One such test discards the whole
  claim.

So do not write a stub that satisfies only the failing tests. Write the
smallest thing that could satisfy the **sentence**, and expect the tests that
already passed to keep passing.

This is not a patch and it will never be merged. It exists to decide whether
the sentence was buildable as written.

## Answer

    {"impls": [{"claim_id": 1, "source": "...the whole replacement file..."},
               {"claim_id": 2, "give_up": "why the sentence cannot be built"}]}

## Claims whose test the real code failed
"""


def brief(cs, header=BRIEF_ONE, limit=40):
    if not cs:
        return ""
    out = [header]
    for c in cs[:limit]:
        out.append("\n### %d. %s -- names %s\n\n> %s\n"
                   % (c["id"], c["kind"], ", ".join("`%s`" % n
                                                    for n in c["names"]),
                      c["says"]))
        out.append("\nfrom `%s`\n" % c["doc"])
        if c.get("real"):
            failed = [n for n, code in sorted(c["real"].items()) if code]
            out.append("\n%d of your %d tests failed against the real code "
                       "(%s), which replaces `%s`:\n```\n%s\n```\n"
                       % (len(failed), len(c["real"]), ", ".join(failed[:6]),
                          c.get("targets", "?"),
                          (c.get("output") or "(no output)")[:900]))
    return "".join(out)


def _run_many(work, root, label, replace, cases):
    """Every test for one claim, in a clone of its own. {name: exit code}.

    One clone per claim rather than per test: the tests share a subject and
    must see the same tree, and a clone per test would multiply an already
    expensive measurement by 8.4. One clone per *run* is not negotiable
    though -- the agent's tests and the agent's implementation are both code
    this repository did not write, and neither may reach the subject."""
    import catch as catch_mod
    bench = catch_mod.bench(root, os.path.join(work, label))
    catch_mod.park(bench, "HEAD")
    if replace:
        full = os.path.join(bench, replace["targets"].replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or bench, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(replace["source"])
    codes, output = {}, []
    for case in cases:
        name = str(case.get("name") or "case%d" % (len(codes) + 1))
        path = os.path.join(bench, "_promise_%s.py" % re.sub(r"\W", "_", name))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(case.get("source", ""))
        try:
            r = subprocess.run([sys.executable, path], cwd=bench,
                               capture_output=True, text=True,
                               timeout=TEST_TIMEOUT)
            codes[name] = r.returncode
            output.append("%s -> %d\n%s" % (name, r.returncode,
                          ((r.stdout or "") + (r.stderr or ""))[:400]))
        except subprocess.TimeoutExpired:
            codes[name] = 124
            output.append("%s -> did not finish in %ds" % (name, TEST_TIMEOUT))
        except OSError as exc:
            codes[name] = 125
            output.append("%s -> %s" % (name, exc))
    return codes, "\n".join(output)[:4000]


def check(root, cs, tests, work):
    """Round one. A claim with any failing test comes back pending."""
    by_id = {t.get("claim_id"): t for t in tests.get("tests", [])
             if isinstance(t, dict)}
    out = []
    for c in cs:
        t = by_id.get(c["id"])
        cases = (t or {}).get("cases") or []
        if not t or t.get("skip") or not cases:
            c["verdict"] = "not tested"
            c["why"] = (t or {}).get("skip", "no test was written")
            out.append(c)
            continue
        codes, output = _run_many(work, root, "real-%d" % c["id"], None, cases)
        c["real"], c["cases"] = codes, cases
        c["targets"] = t.get("targets", "")
        c["output"] = output
        c["verdict"], c["counts"] = verdict(codes, None)
        out.append(c)
    return out


def cross(real, from_doc):
    """{p2p, f2f, f2p, p2f} over two runs of the same tests.

    Keyed by test name so a test that vanished between the runs is counted in
    neither -- silently pairing runs by position would let one crashed test
    shift every verdict after it."""
    out = {"p2p": 0, "f2f": 0, "f2p": 0, "p2f": 0}
    for name, before in sorted(real.items()):
        if name not in from_doc:
            continue
        after = from_doc[name]
        if before == 0 and after == 0:
            out["p2p"] += 1
        elif before != 0 and after != 0:
            out["f2f"] += 1
        elif before != 0 and after == 0:
            out["f2p"] += 1
        else:
            out["p2f"] += 1
    return out


def verdict(real, from_doc):
    """CASCADE's condition, and it is a conjunction for a reason.

    `f2p > 0` is the evidence: the document described something the real code
    does not do and the document's own implementation does. `p2f == 0` is the
    guard: a test the real code passed and the document's code failed means
    the document's implementation is incomplete, and an incomplete
    implementation's successes are not evidence about anything.

    Dropping the guard turns this back into the design it replaces, which the
    paper measures at 0.53 precision."""
    if not real:
        return "not tested", {}
    if all(code == 0 for code in real.values()):
        return "consistent", {}
    if from_doc is None:
        return "pending", {}
    counts = cross(real, from_doc)
    if counts["f2p"] > 0 and counts["p2f"] == 0:
        return "inconsistent", counts
    if counts["p2f"] > 0:
        return "the document's own code is incomplete", counts
    return "the test was wrong", counts


def grade(root, checked, impls, work):
    """Round two. The same tests, against the code the document describes."""
    by_id = {i.get("claim_id"): i for i in impls.get("impls", [])
             if isinstance(i, dict)}
    for c in checked:
        if c.get("verdict") != "pending":
            continue
        impl = by_id.get(c["id"])
        if not impl or impl.get("give_up") or not impl.get("source"):
            c["why"] = (impl or {}).get("give_up",
                                        "no implementation was supplied")
            continue
        if not c.get("targets"):
            c["verdict"] = "not tested"
            c["why"] = "round one named no file for an implementation to replace"
            continue
        codes, output = _run_many(
            work, root, "doc-%d" % c["id"],
            {"targets": c["targets"], "source": impl["source"]},
            c.get("cases") or [])
        c["from_doc"], c["from_doc_output"] = codes, output
        c["verdict"], c["counts"] = verdict(c["real"], codes)
    return checked


def render(cs):
    if not cs:
        return "documented promises: nothing testable found\n"
    counts = {}
    for c in cs:
        counts[c.get("verdict", "not run")] = \
            counts.get(c.get("verdict", "not run"), 0) + 1
    out = ["does the code do what the documents promise?",
           "  %d testable claim(s)" % len(cs)]
    for key in ("inconsistent", "consistent", "the test was wrong",
                "pending", "not tested", "not run"):
        if counts.get(key):
            out.append("     %-20s %d" % (key, counts[key]))
    for c in cs:
        if c.get("verdict") == "inconsistent":
            out.append("  !! %s — %s" % (c["doc"], c["says"][:110]))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--brief", default="")
    ap.add_argument("--brief2", default="")
    ap.add_argument("--check", default="")
    ap.add_argument("--tests", default="")
    ap.add_argument("--grade", default="")
    ap.add_argument("--impls", default="")
    ap.add_argument("--work", default="")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    def load(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    if a.brief:
        text = brief(load(a.brief).get("claims") or load(a.brief),
                     BRIEF_ONE, a.limit)
        if not text:
            print("cannot judge: no testable claims", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if a.brief2:
        cs = [c for c in load(a.brief2) if c.get("verdict") == "pending"]
        text = brief(cs, BRIEF_TWO, a.limit)
        if not text:
            print("cannot judge: no claim the real code failed",
                  file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if a.check:
        if not a.tests or not a.work:
            print("cannot judge: --check needs --tests and --work",
                  file=sys.stderr)
            return 2
        got = check(root, load(a.check).get("claims") or load(a.check),
                    load(a.tests), a.work)
        with open(a.json or "checked.json", "w", encoding="utf-8") as fh:
            json.dump(got, fh, indent=1)
        sys.stdout.write(render(got))
        return 0

    if a.grade:
        if not a.impls or not a.work:
            print("cannot judge: --grade needs --impls and --work",
                  file=sys.stderr)
            return 2
        got = grade(root, load(a.grade), load(a.impls), a.work)
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fh:
                json.dump(got, fh, indent=1)
        sys.stdout.write(render(got))
        return 0

    cs = claims(root)
    if not cs:
        print("cannot judge: no sentence names something executable and "
              "asserts something checkable about it", file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"claims": cs}, fh, indent=1)
    sys.stdout.write(render(cs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
