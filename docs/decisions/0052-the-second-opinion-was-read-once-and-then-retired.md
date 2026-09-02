# 0052 — The second opinion was read once, and then retired

Date: 2026-09-02
Status: accepted

## Context

Since 0037 the hygiene job ran AgentLint, a third-party scorer of the same
subject our assessment measures, with a threshold one point under its first
score. The reasoning was that where it disagreed with our page, one of the
two was wrong and that was worth knowing. Nobody ever chased a
disagreement: no decision, no exec-plan and no issue mentions it. Its score
drifted from 68 to 66 against a red line of 65 while our own readings rose,
so it was one unrelated change from turning main red, and the honest
response to that red would have been to lower the line.

Before retiring it we ran the two dimensions CI cannot: Deep, with one
sonnet reader per prompt, and Session, against this repository's own
Claude Code logs.

| Dimension | Result |
|---|---|
| Deep | 9/10: no contradictions, no dead weight, two rules called vague |
| Session | not judged: it could not see this repository |
| Core | 68 locally, 66 on the pinned commit |

Session could not see the repository because its rule parser only counts
bullet lines beginning `Don't`, `NEVER` or `IMPORTANT` as rules; our
`CLAUDE.md` has none, so the project was dropped from its catalogue and
every session was unmatched. Its Instructions findings are the same lens:
counts of emphasis keywords and of one sentence pattern. That is a
measurement of resemblance to its template, the thing 0020 rejects.

Its Workability and Safety deductions were checked one by one. All but
two were filename tests failing on content that exists: the documented
test command (it wanted a `## Local test` heading), the linter (it did not
recognise `ruff.toml`), the release version check, the hook event
`InstructionsLoaded` (a real event, which `context/selftest.py` relies
on), a rules file declaring `paths:` rather than `globs:`, and the guard
and gate fixtures that deliberately contain the patterns they detect. The
two that held: `assess/selftest.py` at 6074 lines is too long for an agent
to read in one call, and CI runs no secret scanner beyond the write-time
guard.

## Decision

The step is removed. Nothing it found that was true was something our
instrument had missed; what it found that was false would have cost us
points for changing our documents to look like its template. The two true
findings become work of our own: a file-size gate (0053), and a note on
secret scanning for later.

A second opinion is still welcome, on one condition: the day it disagrees,
somebody writes down which of the two was wrong. A scorer whose
disagreements are never read is a printout with a threshold.

## Consequences

- The hygiene job is one step shorter and no longer depends on a scorer
  fetched from a third party's repository.
- Dimension 3.5 will record that this run of main was rerun once, for a
  network reset during a linter install; that is unrelated to this
  decision and is why the install now retries.
- The AgentLint plugin, installed on a maintainer's machine by an `install
  --help` that ignored `--help`, was uninstalled the same day.
