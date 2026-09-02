---
description: Validate the plugin manifest with the first-party checker
allowed-tools: Bash(claude plugin validate:*)
---

Run the first-party manifest checker:

```bash
claude plugin validate . --strict
```

Type it exactly like that. Past PRs have written this command two ways —
`claude plugin validate . --strict` and `claude plugin validate --strict`,
dropping the `.` — which is the retyping drift a slash command exists to end.

This is not `/check`. It isn't wired into `ci.yml`, so `scripts/check.py`
never runs it, and it stays a separate manual step for that reason. Nor is it
a substitute for `python3 shared/scripts/gates/check_plugin_structure.py`,
which `/check` already runs: that gate reads the *prose* in `commands/`,
`skills/` and `agents/` for paths nothing but `${CLAUDE_PLUGIN_ROOT}` can
resolve, which this checker has no way to see. Run this one whenever
`.claude-plugin/`, `commands/`, `skills/`, `agents/`, or `hooks/` changed —
it catches what a schema check catches, no more.
