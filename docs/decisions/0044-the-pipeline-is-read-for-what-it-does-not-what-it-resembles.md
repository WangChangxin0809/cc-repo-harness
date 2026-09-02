# 0044 — The pipeline is read for what it does, not what it resembles

Date: 2026-09-02
Status: accepted
Extends dimension 3 with sub-items 3.3 to 3.6, all read by `pipeline.py`.
Adds `release.yml` and `self-assess.yml` to this repository's own CI.

## Context

Dimension 3 read two things about a pipeline: whether it runs a suite (3.1's
"CI runs the suite") and whether it can be walked around (3.2). Dimension 2
measures whether it catches anything. Nothing read the pipeline as an artefact
with properties of its own, and the properties that matter were invisible on
the page: a change that runs no check because every workflow carries a path
filter; a workflow file no linter or test ever reads; a verdict that went
green on a rerun of the same commit; a tag that points off the default
branch.

The obvious design was a sixth dimension called CI/CD with a score. It was
refused for two reasons. First, dimension 3 *is* the delivery dimension, and
a second home for the `ci` rung would put one fact in two places. Second, and
the one that shaped what was built: most of what a CI/CD score would count is
convention. Matrix breadth, caching, job count, reusable workflows, the runner
image, path-filtered jobs — a repository that runs one job on one Python is
not worse than one that runs six, it is smaller, and scoring it is scoring
resemblance -> [0020](0020-the-assessment-measures-behaviour-not-resemblance.md).

## Decision

Four rows, under dimension 3, each of which passes the test
[0043](0043-a-mechanism-is-not-a-convention.md) set: *is there another way to
get this effect?*

- **3.3 scope.** Which changes run which checks, and which run none. A
  workflow that runs on nothing has not chosen a different convention.
- **3.4 the pipeline checked.** Whether the workflow files are linted, audited
  or tested. A file nobody checks is not checked another way. Steps that
  search the tree and fail are listed as rules a step refuses: the CI-side
  twin of a guard, handed over, never counted.
- **3.5 the verdict's trust.** Reruns whose conclusion changed on the same
  commit, from run history. There is no second way to learn that a verdict
  depended on something other than the code.
- **3.6 what ships.** Tags, what makes them, whether the latest is on this
  branch, whether the manifest agrees. A tag off the branch is off the
  branch.

Three rules carried over from the rest of the page:

- **The ecosystem's tool does the auditing** -> [0033](0033-the-tools-do-the-measuring.md).
  Unpinned actions and `pull_request_target` are zizmor's findings, counted
  by severity when it is on PATH and abstained from when it is not.
- **Not readable is not zero.** Run history behind a remote nobody can ask
  reads as `not readable`, and the grader treats that word as an abstention.
  It had not been: 3.2's branch-protection row said `not readable` and was
  being scored. That is fixed here as a side effect and noted as one.
- **GitHub Actions only, and it says so.** Trigger and filter syntax differ
  per host; a reader that half-understands five hosts reports confidently
  wrong scope on four. Another host gets `cannot judge`.

And two workflows for this repository, because the instrument's own row for
it read *no workflow makes a tag or publishes anything: every release is a
person's hands*:

- `release.yml` tags `v<version>` and publishes a release when the version in
  `plugin.json` changes on `main`. The decision lives in
  `.github/scripts/release_tag.py`, which refuses a reused version and has a
  self-test, for the reason every step in `ci.yml` is one line.
- `self-assess.yml` runs the fact sheet on this repository weekly and keeps
  the page for ninety days. It reports and never gates. The guide's last
  stage is *re-measure months later*, and a stage that depends on somebody
  remembering is the stage that does not happen.

## What was considered and left out

**DORA metrics.** Deployment frequency, lead time, change failure rate, time
to restore. Lead time and change failure rate are derivable from history and
runs. They measure the team, and this page asks about the repository as a
place for an agent to work; the slice of them that bears on an agent is
3.5's time to a verdict, and that is what was kept.

**Reading the pipeline for what it enforces.** Buzz-style contract tests and
grep guards enforce rules a `CLAUDE.md` would otherwise carry, and mapping
each prohibition in the standing text to the step that enforces it would be
the strongest version of 4.2. It needs a matcher between prose and commands
that does not exist yet; 3.4 lists the steps and stops there.

## Consequence

The page on this repository moved the day the two workflows landed: 3.6 went
from *every release is a person's hands* to *made by release.yml*. That is
the instrument seeing a change to its own repository in its own units, which
is the only kind of claim this page carries.
