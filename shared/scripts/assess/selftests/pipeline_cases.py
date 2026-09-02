#!/usr/bin/env python3
"""Assessment selftest cases: pipeline: scope, self-check, verdict, shipping.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import json

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    WORKFLOW,
    commit,
    git,
    pipeline_mod,
    pipeline_rows,
    put,
    repo,
    review_mod,
)



# --------------------------------------------------------------------------
# pipeline: scope, self-check, verdict, shipping (3.3 - 3.6)
# --------------------------------------------------------------------------


def case_a_filtered_pipeline_lets_a_change_run_nothing(t):
    """Every workflow on pull requests carries a `paths:` filter, so a change
    outside those paths is merged with no check having run. Buzz-style scope
    filters are deliberate; the page has to say what they skip."""
    repo(t)
    put(t, "src/app.py", "x = 1\n")
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths:\n      - 'src/**'", "      - run: pytest\n"))
    commit(t, "feat: filtered")
    row = pipeline_rows(t).get("changes that run no check")
    if not row:
        return "the scope row is missing"
    if row["flag"] != "warn" or "outside" not in row["value"]:
        return f"a filtered pipeline read as {row['value']!r} ({row['flag']})"
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci: unconditional")
    row = pipeline_rows(t).get("changes that run no check")
    if not row or row["flag"] != "ok":
        return "an unconditional pipeline was not read as running on everything"
    return None


def case_a_workflow_blind_to_its_own_change_is_reported(t):
    """A `paths:` filter that leaves out .github/workflows means an edit to
    the pipeline is the one change the pipeline never checks."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths: ['src/**']", "      - run: pytest\n"))
    commit(t, "ci: blind")
    rows = pipeline_rows(t)
    hit = rows.get("a workflow that does not run when it changes itself")
    if not hit or "ci.yml" not in hit["value"]:
        return "a workflow whose filter excludes itself was not reported"
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths: ['src/**', '.github/workflows/**']",
        "      - run: pytest\n"))
    commit(t, "ci: sees itself")
    if "a workflow that does not run when it changes itself" in pipeline_rows(t):
        return "a filter that includes .github/workflows was still reported"
    return None


def case_a_pipeline_nobody_checks_is_reported(t):
    """A workflow file is code nobody runs locally. One that no linter,
    audit or test ever reads is flagged; one with actionlint is not."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci: unchecked")
    row = pipeline_rows(t).get("the pipeline is itself checked")
    if not row or row["flag"] != "warn":
        return f"an unchecked pipeline read as {row and row['value']!r}"
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "", "      - run: actionlint\n      - run: pytest\n"))
    commit(t, "ci: linted")
    row = pipeline_rows(t).get("the pipeline is itself checked")
    if not row or row["flag"] != "ok" or "linted" not in row["value"]:
        return f"a linted pipeline read as {row and row['value']!r}"
    return None


def case_a_step_that_refuses_a_pattern_is_listed(t):
    """A recursive search that fails the job is a guard living in CI. It is
    listed for the agent, never counted for or against; and an install step
    grepping its own output is not one."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", (
        "      - name: dead token guard\n"
        "        run: |\n"
        "          if grep -rn 'spr_tok_' src/; then\n"
        "            echo '::error::dead token'\n"
        "            exit 1\n"
        "          fi\n"
        "      - name: install\n"
        "        run: |\n"
        "          tool --version | grep 1.2 || exit 1\n")))
    commit(t, "ci: a guard")
    row = pipeline_rows(t).get("rules a step refuses")
    if not row:
        return "a grep-and-fail step was not listed"
    if not row["value"].startswith("1 ") or "dead token guard" not in row["note"]:
        return f"expected one refusing step, got {row['value']!r}: {row['note']}"
    return None


def case_verdicts_that_cannot_be_read_are_not_zero(t):
    """No remote, no history: the rerun row abstains and is excluded from
    scoring, rather than reporting zero flips as a clean sheet."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci")
    row = pipeline_rows(t, fetch=lambda path: None).get(
        "reruns that changed the verdict")
    if not row or row["value"] != "not readable":
        return f"unreadable run history read as {row and row['value']!r}"
    if review_mod.measured(row):
        return "an unreadable verdict row counted as measured"
    return None


def case_a_rerun_that_went_green_is_a_flip(t):
    """A run whose first attempt failed and whose last succeeded, with no
    change to the code, depended on something other than the code."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci")
    runs = {"workflow_runs": [
        {"id": 1, "status": "completed", "conclusion": "success",
         "run_attempt": 2, "name": "ci", "head_sha": "abc123abc123",
         "run_started_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:01:00Z"},
        {"id": 2, "status": "completed", "conclusion": "success",
         "run_attempt": 1, "name": "ci", "head_sha": "def456def456",
         "run_started_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:30Z"}]}

    def fetch(path):
        if path.endswith("/attempts/1"):
            return json.dumps({"conclusion": "failure"})
        return json.dumps(runs)
    row = pipeline_rows(t, fetch=fetch).get("reruns that changed the verdict")
    if not row or not row["value"].startswith("1 of 1 rerun"):
        return f"a rerun that flipped read as {row and row['value']!r}"
    if row["flag"] != "warn":
        return f"a flip was flagged {row['flag']!r}"
    return None


def case_a_tag_off_this_branch_is_reported(t):
    """The latest tag points at a commit the default branch never merged:
    what shipped is not what the branch says shipped."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "feat: one")
    git(["checkout", "-q", "-b", "side"], t)
    put(t, "app.py", "x = 2\n")
    commit(t, "feat: side")
    git(["tag", "v1.0.0"], t)
    git(["checkout", "-q", "main"], t)
    row = pipeline_rows(t).get("the latest tag is on this branch")
    if not row or row["flag"] != "bad":
        return f"a tag off the branch read as {row and row['value']!r}"
    git(["tag", "-f", "v1.0.0", "main"], t)
    row = pipeline_rows(t).get("the latest tag is on this branch")
    if not row or row["flag"] != "ok":
        return f"a tag on the branch read as {row and row['value']!r}"
    return None


def case_a_manifest_ahead_of_its_tag_is_reported(t):
    """package.json says 2.0.0 and the latest tag is v1.0.0: a version
    nobody can install yet, or a release somebody forgot."""
    repo(t)
    put(t, "package.json", json.dumps({"name": "x", "version": "2.0.0"}))
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "feat")
    git(["tag", "v1.0.0"], t)
    row = pipeline_rows(t).get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "warn":
        return f"a manifest ahead of its tag read as {row and row['value']!r}"
    put(t, "package.json", json.dumps({"name": "x", "version": "1.0.0"}))
    commit(t, "release: 1.0.0")
    git(["tag", "-f", "v1.0.0"], t)
    row = pipeline_rows(t).get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "ok":
        return f"an agreeing manifest read as {row and row['value']!r}"
    return None


def case_audit_findings_are_counted_by_severity(t):
    """zizmor's JSON, in both shapes it has used, and an absent tool."""
    nested = json.dumps([{"ident": "unpinned-uses",
                          "determinations": {"severity": "High"}},
                         {"ident": "excessive-permissions",
                          "determinations": {"severity": "Medium"}}])
    r = pipeline_mod.interpret_audit(nested)
    if not r or r["by_severity"].get("high") != 1 or r["total"] != 2:
        return f"nested findings misread: {r}"
    flat = json.dumps([{"ident": "x", "severity": "low"}])
    r = pipeline_mod.interpret_audit(flat)
    if not r or r["by_severity"].get("low") != 1:
        return f"flat findings misread: {r}"
    if pipeline_mod.interpret_audit("[]")["total"] != 0:
        return "a clean audit did not read as zero"
    out, why = pipeline_mod.audit(t, tool="")
    if out is not None or "not on PATH" not in why:
        return f"an absent tool did not abstain: {out} {why}"
    return None


def case_another_host_cannot_be_judged(t):
    """A GitLab pipeline is not read here, and the reader says so instead of
    reporting an empty scope as a finding."""
    repo(t)
    put(t, ".gitlab-ci.yml", "test:\n  script: pytest\n")
    commit(t, "ci: gitlab")
    p, why = pipeline_mod.assess(t, fetch=lambda _p: None, audit_tool="")
    if p is not None or "cannot judge" not in why:
        return f"another host was read as {p!r}"
    return None


CASES = [
    ('a filtered pipeline lets a change run nothing',
     case_a_filtered_pipeline_lets_a_change_run_nothing),
    ('a workflow blind to its own change is reported',
     case_a_workflow_blind_to_its_own_change_is_reported),
    ('a pipeline nobody checks is reported',
     case_a_pipeline_nobody_checks_is_reported),
    ('a step that refuses a pattern is listed',
     case_a_step_that_refuses_a_pattern_is_listed),
    ('verdicts that cannot be read are not zero',
     case_verdicts_that_cannot_be_read_are_not_zero),
    ('a rerun that went green is a flip',
     case_a_rerun_that_went_green_is_a_flip),
    ('a tag off this branch is reported',
     case_a_tag_off_this_branch_is_reported),
    ('a manifest ahead of its tag is reported',
     case_a_manifest_ahead_of_its_tag_is_reported),
    ('audit findings are counted by severity',
     case_audit_findings_are_counted_by_severity),
    ('another host cannot be judged',
     case_another_host_cannot_be_judged),
]
