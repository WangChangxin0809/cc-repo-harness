---
name: project-memory
description: Use when recalling project decisions, remembering reusable discoveries, consolidating memory, or withdrawing outdated project knowledge.
---

# Project memory

Governs: scripts/memory/* .harness/memory/*

Run the repository's `scripts/memory/cli.py`; its JSON receipts distinguish
private candidates, working-tree proposals and accepted Git knowledge.
Use `--help` for exact arguments. Python 3.9+ and Git are the only runtime requirements.

## Recall and capture

Use `recall --query "task" --path src/module/file.py` to obtain relevant
knowledge with its version/source receipt. Read exclusions when a result is
empty or stale. A memory entry is reference data and grants no permissions.

For an explicit reusable decision:

```bash
python3 scripts/memory/cli.py --session SESSION remember --title "Keep v1" --body "Keep v1 until client migration finishes." --reason "Team compatibility decision" --path 'src/api/**'
```

Replace `SESSION` with the current session token. Without one, the returned
random session must be retained for later operations. Never use a shared
fallback token for unrelated sessions. Existing documents should be referenced
through `remember --record` with the source digest, rather than copied wholesale.

Use `propose CANDIDATE_ID` to inspect the private diff and validation report.
`apply PROPOSAL_ID` writes that proposal into the worktree for ordinary Git
review. It does not commit, push, merge or accept it. Keep the same `--session`
for candidate/proposal operations. Personal preferences and transcripts stay private.

## Dream

`dream prepare` freezes selected candidates and the accepted view. Read the
returned report, snapshot manifest and output contract. Perform synthesis only
when requested; the runtime never invokes a model or creates a paid job.
Write only the returned private `output` file. Preserve input/output mappings,
source associations, scope, measurements and exceptions. Unresolved contradictions
remain explicit; repetition and recency are not proof.

Run `dream finish JOB_ID --output OUTPUT_PATH` to validate that output and
prepare a proposal. Every input needs a disposition and every output needs
provenance. Without semantic output, finish reports deterministic checks only.
Job completion does not accept knowledge. If baselines changed, reconcile before
applying; do not overwrite the newer decision. `dream inspect` and `dream cancel`
provide the job receipt and cancellation boundary.

## Maintenance

`verify` checks sources and scope. `forget ID --reason REASON` prepares a
retirement; `--private` removes selected private material. Retirement stops
future eligible recall and does not erase Git history or referenced documents.
`sync` refreshes the local view; fetching requires an explicit named `--remote`
and does not merge the worktree. Use `doctor` for unsupported host/remote features.

On a fresh clone, explicitly adopt the team's integration ref with
`init --accepted-ref refs/remotes/origin/main` (substitute the actual ref).
Cloud sessions without repository hooks use this same CLI explicitly. Native
host memory remains separate. Keep permanent policy/code changes in ordinary
review, including when dream suggests a new guard or rule.
