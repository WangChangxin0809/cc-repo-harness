# Architecture

- **Covers**: how this system works, for someone who does not yet know what to
  ask. Read on demand, so it may be long.
- **Does not cover**: how to perform a task (`docs/index.md` routes there), why
  a specific choice was made (`docs/decisions/`), what must never happen
  (`CLAUDE.md`, paid on every turn, so it stays short).

<!-- Written by hand. A generated rollup describes the current accident; this
     describes the intent, including the constraints that are not visible
     anywhere in the code. That is the whole reason this file exists. -->

## What it does

A coding agent reads `CLAUDE.md` on every turn and still repeats the same
mistake, because a paragraph is advice and advice gets skipped. This plugin
puts each rule where it actually takes effect: a hook that refuses the command
before it runs, a check that fails the build, a document that loads only when
the agent opens that directory. Then it measures, in numbers that can be taken
again later, whether the setup is earning what it costs on every turn.

The one sentence that decides where every new file goes: **the repository keeps
the harness, the plugin keeps the instrument.** Anything a repository needs in
order to work is copied into it and must keep working after this plugin is
uninstalled. Anything that only *reports on* a repository stays here and is run
against it. A repository that behaves differently for a teammate who has not
installed the plugin is a bug (hard rule 4).

So most of this repository is not the plugin. It is payload, written for a
repository nobody here has seen, and a measuring instrument pointed at that
payload from outside.

## Codemap

Three identities, one tree. Every file is exactly one of them.

| Directory | Holds | Talks to |
|---|---|---|
| `.claude-plugin/` | manifest, marketplace entry; `agents` lists every agent file, and the list *replaces* the default directory | the plugin validator, `release.yml`, which tags whenever the manifest changes on main |
| `skills/bootstrap-repo-harness/` | the one skill that stays in the plugin: how a person arrives | every session on the machine, ~39 tokens a turn (0024); the whole plugin is capped at 100 by `check_plugin_structure.py` |
| `agents/` | `assess/` only: the reader, and the blind promise tester | spawned by `commands/assess.md`; they read a run and write answers or a reading, never the repository |
| `hooks/` | `first_look.py` on SessionStart; `run_repo_guards.py`, which runs a *subject* repository's own `scripts/guards/` until it wires them itself | the subject repository's tree; nothing here changes what it does |
| `shared/agents/` **payload, copied** | `repo-explorer`, copied to `.claude/agents/` at tier C beside the `repo-index` skill that names it | the repository that asked for it; nothing is charged to the ones that did not |
| `shared/scripts/guards/` **payload, copied** | one file per rule; `dispatch.py` runs them all and fails open; `selftest.py` proves each can refuse and checks the wiring names every tool a guard judges | `.claude/settings.json` PreToolUse, matcher `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit` |
| `shared/scripts/gates/` **payload, copied** | checks over the worktree at CI time, each with a selftest that plants its own defect | `ci.sh` / `ci.yml`; `scripts/check.py` runs them locally |
| `shared/scripts/context/` **payload, copied** | `before_write.py` delivers `Governs:` documents and the rules the native loader misses; `same_turn.py` runs the selftest beside an edited file; `on_stop.py`; `session_brief.py` is generated per repository | PreToolUse, PostToolUse, Stop, SessionStart |
| `shared/scripts/index/` **payload, copied** | the repo graph: `build.py`, `query.py`, a gold set | tier C repositories only |
| `shared/scripts/scaffold.py` **payload, run from here** | the `COPY` table and the `PLAN`: what lands where, at which tier; the only thing that has to know about a new payload directory | a fresh repository, once |
| `shared/scripts/probe_repo.py` `drift.py` `check_plugin_structure.py` **run from here** | what a repository has and lacks; pairs of files that used to move together and stopped; the plugin surface, which only this repository has | `factsheet.py` |
| `shared/scripts/assess/` **the instrument, run from here** | `factsheet.py` measures five dimensions and writes a run; `briefs.py` writes what the instrument could not answer; `review.py` turns readings into a page | the reader agents; the repository under assessment, in a bench clone, never in place |
| `shared/skills/` **payload, copied by tier** | five skills, each with a `Governs:` line naming the paths it is delivered for | `scaffold.py` copies them into `.claude/skills/`; here, `before_write.py` delivers them on a write to the governed path |
| `CLAUDE.md` `ARCHITECTURE.md` `docs/` `guide/` | the two nothing can generate; the routing table; every decision; the reader's guide to the assessment | people, and the model on every turn (`CLAUDE.md` only) |
| `.claude/` | wiring only, never knowledge: `settings.json` points hooks at `shared/` (source, not copy), `guards.json`, `rules/` | Claude Code |
| `scripts/` | our own harness: `check.py` reads `ci.yml` and runs the steps out of it; `session_brief.py` is our instance of the generated one | us |
| `eval/` | the corpus lane: needs an API backend and quota, `workflow_dispatch` only | nightly workflows, never CI |

### The assessment, end to end

```
factsheet.py --root R --json RUN            measure: probe, blast, catch, coverage, drift, docs, cost
briefs.py --run RUN --dimension N --out D   write every question dimension N left open
assess-reader (answer) x3                   answer them: what an agent can watch, twenty legitimate
                                            actions, which document candidates are real
factsheet.py --from RUN --*-answers ...     apply the answers; nothing is re-measured
review.py --brief RUN --dimension N         the brief for one dimension
assess-reader (read) x10                    a score, a why, and moves_if per sub-item, twice
review.py --grade RUN --answers ...         pool the readings; the page opens with what would move it
```

The instrument produces rows. The readers produce numbers. `commands/assess.md`
holds neither: it is the order the steps run in, and who is spawned when.

## Invariants

Properties that must hold across the whole system, each with the place that
enforces it. A property with no enforcement point is an aspiration.

1. **Everything under `shared/` works in a tree that has never seen this plugin**: standard library only, Python 3.9 and up, no path or name of ours assumed — `shared/scripts/selftest.py` scaffolds a throwaway repository, deletes the plugin, and checks it still holds; CI runs the suite on 3.9 and 3.13.
2. **A check nobody has watched fail is not a check** — every `selftest.py` plants the defect its checks exist to catch; `writing-checks` arrives on a write under `guards/` or `gates/` and says so.
3. **Exit 2 is COULD NOT JUDGE and is never a pass** — `scripts/check.py` treats it as red; `ci.yml`'s header forbids `|| true` and `no_silenced_check` refuses the edit that adds one; every assessment row that cannot be judged says so instead of printing a zero.
4. **Installing the plugin changes nothing a repository does** — `hooks/hooks.json` wires two hooks and neither writes to the tree; `run_repo_guards.py` stays out once a repository wires its own dispatcher; decision 0021.
5. **Wiring points at the source, not at a copy** — `.claude/settings.json` calls `shared/`; `check_docs_index.py` holds `docs/index.md` and the tree to each other in both directions; `no_committed_credential` keeps `settings.local.json` out of history.
6. **A guard is a speed bump and fails open** — `dispatch.py` swallows a crashing guard by design, which is why `guards/selftest.py` sits in the fast CI lane and why anything that must not be missed is a deny rule or branch protection first.
7. **The instrument asks a hook only what Claude Code would ask it** — `catch.applicable` filters every probe by the hook's matcher; decision 0049.
8. **Absence in the repository is measured; absence on the machine abstains** — no test file is a red row, a missing toolchain is an abstention; decision 0047.

## Constraints that are not visible in the code

- **A `paths:` rule loads only on Read.** Not on `Write` of a new file, not on a heredoc through the shell. Four issues asked for the Write half and all were closed. `before_write.py` exists because this is permanent.
- **A plugin skill is paid for on every turn of every session on the machine**, in repositories that never asked for it. That is why one skill lives here and five are copied (0024), and why the plugin's own manifest description is kept short.
- **A manifest `agents` list replaces the default directory** rather than adding to it, and the first-party validator takes `.md` files only. Drop one from the list and it silently stops existing.
- **A change to `.claude-plugin/plugin.json` on main is a release.** `release.yml` tags and publishes on that path; `release-hygiene` refuses a shipping pull request that does not raise the version.
- **Deleting a base branch closes every pull request stacked on it**, and `gh pr merge --auto` is not allowed on this repository. Land stacked work bottom-up.
- **`git push` and mutating `gh` must run alone.** `no_piped_outbound` refuses them inside a pipe, because a pipeline reports the last command's status.
- **Some readings depend on where the reader stands.** Shipping (3.6) is read against the default branch; a clone made from a feature checkout inherits that checkout as `origin/HEAD`, which is why `blast.py` resolves the default branch itself.
- **The eval lane needs an API backend and quota** and only ever runs on dispatch; nothing in CI depends on it, and nothing in the assessment does.
