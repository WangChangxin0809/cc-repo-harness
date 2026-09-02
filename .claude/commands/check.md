---
description: Run the whole pre-push suite and report the verdict honestly
argument-hint: "[--list]"
allowed-tools: Bash(python3 scripts/check.py:*)
---

Run the suite CLAUDE.md asks for before every push:

```bash
python3 scripts/check.py $ARGUMENTS
```

It reads `.github/workflows/ci.yml` and runs what a laptop can, so there is no
second list here to drift against it — do not re-derive that list yourself by
reading the workflow.

Report the verdict as it actually came back, not as you'd like it to read:

- **0** — green. Say how many steps ran.
- **1** — a real failure. Name the step and quote its own output; do not
  summarize a red step into something softer than it said.
- **2** — **COULD NOT JUDGE, and CLAUDE.md rule 3 says that is never a pass.**
  An unreadable step or a linter this machine lacks lands here. The fix is
  to make the step judgable — install what's missing, or repair the step —
  never to treat the exit code as good enough to push on.

`python3 scripts/check.py --list` prints every step's verdict (run, skip, or
cannot-classify) and why, without running anything — reach for it when a
result needs explaining, instead of opening `ci.yml`.

This runs everything wired into CI. It does not run
`claude plugin validate . --strict`, which isn't part of `ci.yml` at all —
that's `/validate`, and it's a separate step for exactly that reason.
