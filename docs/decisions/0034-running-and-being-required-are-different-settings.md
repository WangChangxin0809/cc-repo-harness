# 0034 — Running and being required are different settings

Date: 2026-09-01
Status: accepted
Dimension 3 asked what evidence a change arrives with. It never asked whether
anybody was obliged to look at it.

## Context

Dimension 2 injects defects and watches which layer turns red. That measures
whether the checks **work**, and it is measured rather than read.

It cannot see the failure a repository can have while every check passes:
nothing requires the check to be green before the change lands. Both states
produce identical evidence on every surface a person normally sees — a green
tick on the pull request, a passing badge, a workflow file full of checks. The
difference appears exactly once, on the day somebody merges past a red run.

Measured here first: `.github/workflows/ci.yml` runs on `pull_request`, and
`main` has no branch protection at all. The guard from dimension 1 refuses a
direct push to `main`, but that guard lives in this repository's hooks and
protects only people who have them wired. Anybody else — a bot, a person
merging from the web interface — has nothing in the way. The two dimensions
were describing the same hole from opposite sides and neither said so.

## Decision

**Three states, not two.**

| | what it means | what reads it |
|---|---|---|
| nothing on pull requests | no verification before a merge at all | the workflow file |
| runs, not required | verification happens and can be merged past | the workflow file |
| required | it cannot be walked around | branch protection, and only that |

The first two separate offline. Only the third needs the API, and keeping the
middle state distinct is the entire point of the row.

**Not readable is never reported as not required.** No remote, no `gh`, no
auth, no rights on a private repository — all of them read as *not readable*.
A tool that turns its own blindness into a finding about the subject is worse
than one that abstains, because the finding is confident and wrong.

**A 404 is an answer; a 403 is not.** GitHub returns 404 `Branch not
protected` for a branch with no protection rule, and that is a fact about the
repository. A 403 is this tool lacking the right to look. The two arrive
through the same non-zero exit code and mean opposite things, so the
interpretation is a separate pure function that can be exercised on a machine
with no `gh`, no network and no repository.

**Status swallowing is listed, not counted.** `continue-on-error: true` and
`|| true` turn a red run green, which is worse than an absent check because
the badge then says the opposite of the truth. But a mechanical count is
wrong here and this repository is the proof: of its four hits, one is a corpus
measurement that deliberately must not fail the job and three are `kill ... ||
true` in cleanup. So each candidate is carried with **the comment above it**,
because every legitimate use this project has seen came with a sentence saying
why and every illegitimate one did not — a signal an agent can use and a
counter cannot. Machine narrows, agent judges.

**The repair log is removed.** It counted places repaired more than once and
read that as churn. The reading does not hold: plenty of code is revised
repeatedly on purpose, and a counter cannot tell that from a place nobody can
get right. A number nobody can act on is worse than no number, because it
occupies the space where an actionable one would go.

## Rejected

**A YAML parser.** `shared/` is standard library only in a repository that
installs nothing. What is needed is not general YAML: it is *does this file
trigger on pull requests*, which an anchored regex over the `on:` block
answers. A parser would be the right tool for a question nobody is asking.

**Flagging bare `exit 0`.** Too noisy to survive contact with a real workflow.
Both of this repository's own uses are legitimate and documented, and a check
whose first output is two false positives on its author's own tree teaches
people to ignore it.

**Reading `CODEOWNERS` as a requirement.** A CODEOWNERS file assigns reviewers.
Whether review is *required* is, again, branch protection. Treating the file
as the setting would recreate exactly the confusion this row exists to remove.

## Consequences

**Dimension 3's headline can now be wrong in a new way, and that is correct.**
A repository with excellent checks and no protection rule reads BAD on this row
while reading well on every other. That is the finding.

**Dimension 1 and dimension 3 now say the same thing twice about `main`**, from
the client side and the server side. Left as is: a guard that stops the person
who has it wired and a protection rule that stops everybody are genuinely
different protections, and a reader who sees only one of them draws the wrong
conclusion about who is covered.

## Evidence status

| Claim | Grade |
|---|---|
| A 404 is an answer and a 403 is not | **checked** — planted "any failure reads as unprotected" |
| Unreadable protection does not become `not required` | **checked** — planted the fall-through |
| A push-only workflow is not a merge gate | **checked** — planted `on_pull_request: True` |
| A comment about swallowing is not swallowing | **checked** — planted the comment skip out, on the line in this repository's own ci.yml that says no step may swallow a status |
| The comment beside a swallow is attributed to the right step | **checked** — the walk crosses one YAML list boundary and stops at the second |
| Listing rather than counting swallows is right | **argued** — three of this repository's four candidates are legitimate, which is one repository's evidence |
