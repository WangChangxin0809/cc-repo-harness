# agent-harness

A plugin that lays the foundation which makes a repository teach coding agents
how to work in it — and then becomes unnecessary.

The acceptance test is literal: install it, run the bootstrap, **uninstall the
plugin**, hand a fresh agent a real task, and the repository must still teach it
the conventions. Everything the plugin installs lives in the target repository —
`CLAUDE.md`, `.claude/settings.json`, `docs/`, `scripts/` — under version
control, reviewable in a pull request, and working for teammates who have never
heard of this plugin.

## Install

```bash
/plugin marketplace add <this-directory-or-repo>
/plugin install agent-harness
```

Then, in the repository you want to set up: *"set this repo up so the rules
actually get enforced"* — or invoke `bootstrap-repo-harness` directly.

## What is in it

| Skill | Enter it when |
|---|---|
| `bootstrap-repo-harness` | Once, to lay the foundation |
| `writing-docs` | Every time you write or restructure a document |
| `writing-checks` | Every time a rule needs enforcing rather than documenting |
| `writing-github-docs` | README, CONTRIBUTING, and the community health files |
| `repo-index` | Large repo; an agent cannot find the relevant code |
| `consolidating-notes` | Notes have accumulated, drifted, or contradicted |

Plus one subagent (`repo-explorer`, small model, own context) and one hook that
runs a repository's own guards during the window before it has wired them.

## The argument

Knowledge only changes behaviour if it arrives at the moment of acting. A
repository has seven such moments and each has a different cost and reach; most
repositories use one of them — a `CLAUDE.md` that is paid on every turn, read
once, and followed unevenly.

Two rules follow, and everything else is detail:

- **Knowledge lives in the repository, not in agent memory.** Memory is
  per-machine, invisible to review, and cannot be corrected by a teammate.
- **What cannot tolerate a miss never goes through retrieval.** Retrieval is
  best-effort by construction. Rules whose violation is irreversible or silent
  become a guard that blocks the action or a gate that fails the build.

## Verifying the plugin itself

```bash
python3 shared/scripts/guards/selftest.py
python3 shared/scripts/gates/selftest.py --verbose
```

Both build throwaway repositories, plant a defect each check must catch, and
assert the check turns red **and names the defect** — then that it turns green
without it. A check nobody has watched fail is a file, not a check.

## Requirements

- Python 3.9+ (standard library only — no dependencies)
- git
- Claude Code with plugin support

`tree-sitter-languages`, if installed, upgrades the index's symbol extraction.
Without it the index falls back to per-language regexes and says so in its
report, so you always know which one produced the graph you are reading.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues go to
[SECURITY.md](SECURITY.md), not the issue tracker.

## License

MIT — see [LICENSE](LICENSE).
