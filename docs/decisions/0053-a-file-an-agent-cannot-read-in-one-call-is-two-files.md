# 0053 — A file an agent cannot read in one call is two files

Date: 2026-09-02
Status: accepted

## Context

0052 kept one true finding from the second opinion we otherwise retired:
`shared/scripts/assess/selftest.py` at 6074 lines is too long for an agent
to read in one call. Nothing here had said so before, because nothing here
measured it. The failure it causes is specific and silent: the Read tool
shows 2000 lines by default, a longer file is read in pieces, and the piece
an agent did not ask for a second time is where the defect it did not see
lives. A reviewer skimming a diff has the same blind spot for the same
reason — the part of the file that did not change is the part nobody
reopened.

This is not a style question. A 2500-line module and a 900-line module
carrying the same rules are not equally readable; the first one is read
wrong by default, and the second is read whole by default. Nothing else in
this repository's checks caught it: `check_context_budget.py` caps what
loads unconditionally at launch, which is a different budget from what a
tool call can see in one shot, and `check_layering.py` judges direction, not
size.

## Decision

**`check_file_size.py` caps every tracked text file at 2000 lines.** The
cap is the Read tool's own default page size, not an arbitrary style
number — the point is not "files should be short," it is "a file should
fit the tool that reads it." Generated, vendored, and non-prose files are
out of scope by construction (`docs/generated/`, `node_modules/`,
`vendor/`, `third_party/`, `.venv/`, lockfiles, minified bundles, SVG) —
none of them is prose an agent reads top to bottom, and a cap over the
first two would just be pressure to stop regenerating or vendoring
correctly.

**An exemption needs a reason, and the reason expires.** `.claude/guards.json`
can list a file this gate should not flag, but an exemption with no reason
is red — the same rule `check_docs_index.py` applies to `<!-- unrouted:
reason -->` — and an exemption for a file that has since shrunk under the
cap, or been deleted, is also red. A stale exemption is indistinguishable
from a forgotten one, and the gate is the only thing positioned to notice
that the file it excuses has changed shape since the excuse was written.

`shared/scripts/assess/selftest.py` is exempt for now: it is mid-split on a
parallel branch, and the exemption names that branch so its own staleness
check retires it the day that branch lands.

## Consequences

`shared/scripts/assess/dimensions.py`, the other file this gate found over
cap in this repository, was split rather than exempted — the same choice
the gate's own hint offers first. Every future addition to `shared/` now
gets this feedback at the size where splitting is still a small edit,
rather than at the size where it is a rewrite.
