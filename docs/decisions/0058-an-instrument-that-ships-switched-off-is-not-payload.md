# 0058. An instrument that ships switched off is not payload

## Status

Accepted, 2026-09-03.

## Context

`check_plugin_structure.py` lived in `shared/scripts/gates/` and so was copied
into every tier-B repository, where it exited 2 because nothing there has a
`.claude-plugin/`. The generated `ci.sh` carried it commented out. `drift.py`
was in the scaffold's `SCRIPTS` table because the `writing-docs` skill taught
its commands, though only the plugin's `/assess` ever ran it. The template
repository, which is what a stranger actually clones, held both, plus a
`.claude/readings/` that only the assessment writes.

Rule 4 in `CLAUDE.md` says the repository keeps the harness and the plugin
keeps the instrument. A file a repository never runs is an instrument.

## Decision

- `check_plugin_structure.py` moves up to `shared/scripts/`, beside
  `probe_repo.py` and `drift.py`: run from here, copied nowhere. It carries
  its own `--selftest`, because the gates' harness only knows `gates/`.
- `drift.py` leaves the scaffold's `SCRIPTS` table. `writing-docs` stops
  teaching its commands and says instead who reads the pairs.
- The template drops both files and `.claude/readings/`.

While here, the context budget grows two per-item ceilings, because a sum
lets one file eat the budget of five:

| what | cap |
|---|---|
| one scoped rule | 50 tokens |
| one skill description | 100 tokens |
| the plugin, all always-on components summed | 100 tokens, down from 150 |

Both rules and all five payload skill descriptions were rewritten under the
caps rather than the caps set where the files were.

## Consequences

- `sync_template.py` no longer re-plants the two instruments. The template's
  `scripts/gates/` is now the same list a tier-B scaffold produces.
- A tool only we need has a place that is not a copied directory. The
  `shared/scripts/CLAUDE.md` exception paragraph is gone.
- Fifty tokens is one sentence and a pointer. A rule that needs more is a
  document, and the gate will say so.
