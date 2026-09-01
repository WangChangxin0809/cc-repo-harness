#!/usr/bin/env python3
"""Whether the verification can be walked around.

    python3 assess/merge.py [--root .] [--json OUT]

Exit codes:
    0 = read
    2 = cannot judge (no workflows, no remote, nothing to read)

## Not "does it work" -- "can it be skipped"

Dimension 2 already injects defects and watches whether CI turns red. That is
the question of whether the checks work, it is measured rather than read, and
nothing here repeats it.

This asks the other question, and it is the one a repository can fail while
every check passes: **is anything obliged to look before the change lands?**

## Three states, not two

| | what it means | what reads it |
|---|---|---|
| nothing on pull requests | no verification happens before a merge at all | the workflow file |
| runs, not required | verification happens and can be merged past | the workflow file |
| required | it cannot be walked around | branch protection, and only that |

The first two separate offline. Only the third needs the API, and the reason
to keep the distinction sharp is that a repository in the middle state looks
identical to one in the last on every surface a person normally sees: green
ticks on the pull request, a passing badge, a workflow file full of checks.
The difference shows up once, on the day somebody merges past a red run.

## What "not readable" must never become

No remote, no `gh`, no auth, a private repository somebody lacks rights on --
all of those read as **not readable**. Never as *not required*. A tool that
turns its own blindness into a finding about the subject is worse than one
that abstains, because the finding is confident and wrong.

The one case that *is* readable without permission to read protection: GitHub
answers 404 `Branch not protected` for an unprotected branch on a public
repository. A 404 is an answer. A 403 is not.

## Status swallowing, listed and not judged

A step with `continue-on-error: true`, or a command ending `|| true`, turns a
red run green. That is worse than an absent check, because the badge says the
opposite of the truth.

It is also where a purely mechanical reading goes wrong, and this repository
is the example: two of its three hits are legitimate -- a labelled exemption
and a corpus measurement that deliberately must not fail the job -- and both
have a comment saying so. So these are collected as **candidates with their
context** and handed over, not counted. Machine narrows, agent judges.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from blast import default_branch                          # noqa: E402

API_TIMEOUT = 30

# `on:` at column zero, then everything until the next column-zero key. Enough
# to answer "does this run on pull requests" without a YAML parser, which is
# not available: shared/ is standard library only, in a repository that
# installs nothing.
_ON_BLOCK = re.compile(r"^on:\s*(.*?)(?=^\S)", re.M | re.S)
_SWALLOW = (("continue-on-error: true", "the step's failure is ignored"),
            ("|| true", "the command's status is discarded"))


def _workflows(root):
    where = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(where):
        return []
    out = []
    for name in sorted(os.listdir(where)):
        if not name.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(where, name), encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        block = _ON_BLOCK.search(text)
        on = block.group(1) if block else text[:400]
        out.append({
            "file": ".github/workflows/" + name,
            "on_pull_request": "pull_request" in on,
            "swallows": _swallows(text),
        })
    return out


def _swallows(text):
    """Lines that could turn a red run green, each with the comment above it.

    The comment is carried deliberately. Every legitimate use of these two
    constructs that this project has seen was accompanied by a sentence
    explaining why, and every illegitimate one was not -- which is a signal an
    agent can use and a counter cannot."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            # A comment *about* swallowing is not swallowing. This repository
            # is the example: ci.yml carries a line saying no step may use
            # `|| true`, and the first version of this reader flagged that
            # sentence as a violation of itself.
            continue
        for needle, what in _SWALLOW:
            if needle not in line:
                continue
            # Backwards to the step boundary, which in YAML is the `- `
            # that starts a list item -- not the first non-comment line,
            # because the step's own keys sit between the comment and the
            # construct:
            #
            #     # the corpus measurement must not fail the job
            #     - name: measure
            #       continue-on-error: true
            #
            # So one `- ` may be crossed, and the comments above it belong to
            # this step. A second one is the previous step and stops the walk.
            # When the construct is itself on the `- ` line, that boundary has
            # already been crossed and anything above belongs to somebody else.
            comment, crossed = "", line.strip().startswith("- ")
            for j in range(i - 1, max(-1, i - 9), -1):
                stripped = lines[j].strip()
                if not stripped:
                    break
                if stripped.startswith("#"):
                    comment = stripped.lstrip("# ") + " " + comment
                    continue
                if stripped.startswith("- "):
                    if crossed:
                        break
                    crossed = True
                    continue
                if crossed:
                    break
            out.append({"line": i + 1, "text": line.strip()[:120],
                        "what": what, "reason_given": comment.strip()})
    return out


def _slug(root):
    r = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                       cwd=root, capture_output=True, text=True)
    url = (r.stdout or "").strip()
    m = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else ""


def protection(root):
    """Whether anything is required, or why that could not be established."""
    slug = _slug(root)
    if not slug:
        return {"readable": False,
                "why": "no github remote — protection is a server-side fact "
                       "and there is no server to ask"}
    if shutil.which("gh") is None:
        return {"readable": False, "slug": slug,
                "why": "`gh` is not installed, so branch protection cannot be "
                       "read. It is a server-side setting; nothing in the tree "
                       "records it"}
    branch = default_branch(root)
    try:
        r = subprocess.run(
            ["gh", "api", "repos/%s/branches/%s/protection" % (slug, branch)],
            cwd=root, capture_output=True, text=True, timeout=API_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"readable": False, "slug": slug, "branch": branch,
                "why": "asking github failed: %s" % exc}

    return interpret(r.returncode, r.stdout or "", r.stderr or "", slug, branch)


def interpret(code, stdout, stderr, slug="", branch=""):
    """What the API's answer means, separated from the asking.

    Split out because the distinction it draws is the whole of this module's
    honesty and it must be testable on a machine with no `gh`, no network and
    no repository: a 404 is an answer and a 403 is not."""
    base = {"slug": slug, "branch": branch}
    body = stdout + stderr
    if code == 0:
        try:
            data = json.loads(stdout)
        except ValueError:
            data = {}
        checks = ((data.get("required_status_checks") or {}).get("contexts")
                  or [])
        base.update(readable=True, protected=True,
                    required_checks=list(checks),
                    required_reviews=data.get(
                        "required_pull_request_reviews") is not None)
        return base
    # A 404 on a repository that exists is an answer: the branch has no
    # protection rule. A 403 is not an answer -- it is this tool lacking the
    # right to look, and reporting that as `nothing is required` would be a
    # confident claim about a repository nobody read.
    squashed = body.replace(" ", "")
    if "Branchnotprotected" in squashed or '"status":"404"' in squashed:
        base.update(readable=True, protected=False, required_checks=[],
                    required_reviews=False)
        return base
    base.update(readable=False,
                why="github would not answer (" + body.strip()[:120] + ")")
    return base


def assess(root):
    flows = _workflows(root)
    if not flows and not os.path.isdir(os.path.join(root, ".github")):
        return None, ("cannot judge: no .github/ — nothing here describes what "
                      "should happen before a change lands")
    prot = protection(root)
    on_pr = [f for f in flows if f["on_pull_request"]]
    swallows = [dict(s, file=f["file"]) for f in flows for s in f["swallows"]]

    if not on_pr:
        state = "nothing on pull requests"
    elif prot.get("readable") and prot.get("required_checks"):
        state = "required"
    elif prot.get("readable"):
        state = "runs, not required"
    else:
        state = "runs; whether it is required is not readable"

    return {"state": state, "workflows": flows,
            "on_pull_request": [f["file"] for f in on_pr],
            "protection": prot, "swallow_candidates": swallows}, ""


def render(r):
    if not r:
        return "merge gate: could not judge\n"
    out = ["can the verification be skipped?  -- %s" % r["state"],
           "  on pull_request    %s" % (", ".join(r["on_pull_request"]) or "nothing")]
    p = r["protection"]
    if p.get("readable"):
        out.append("  required checks    %s" %
                   (", ".join(p["required_checks"]) or "none — a red run can "
                    "be merged past"))
    else:
        out.append("  required checks    not readable: %s" % p.get("why", ""))
    if r["swallow_candidates"]:
        out.append("  status swallowed?  %d candidate(s), for an agent to judge"
                   % len(r["swallow_candidates"]))
        for s in r["swallow_candidates"][:5]:
            out.append("     %s:%d  %s%s" % (
                s["file"], s["line"], s["what"],
                "  [reason given: %s]" % s["reason_given"][:60]
                if s["reason_given"] else "  [no reason given]"))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    r, why = assess(os.path.abspath(a.root))
    if not r:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1)
    sys.stdout.write(render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
