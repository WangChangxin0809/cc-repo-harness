# 0057 — The template is a repository, not a string

Date: 2026-09-03
Status: accepted

## Context

There was no artefact here anyone could be handed. `scaffold.py` was 862 lines
of which 372 — 43% — were prose held as triple-quoted string literals:
`CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, `ci.sh` and five more. Held that
way they are invisible to every check in this repository. No linter reads them,
no gate judges them, nobody opens them; they are edited by editing Python.

The root of this repository is not a substitute. Its own `CLAUDE.md` says so —
`CLAUDE.md .claude/ scripts/ docs/ eval/ guide/` are marked **only us** — and it
does not even satisfy the tier B layout `scaffold.py` writes for other people:
there is no `ci.sh` here, because CI is `.github/workflows/ci.yml` plus
`scripts/check.py`. A repository that fails its own template is not the template.

So the parts that were genuinely reusable — 21 check scripts and six skills —
were reusable *as parts*, and there was no assembled thing.

## Decision

A separate repository, `cc-repo-harness-template`, is the starting point for a
new repository. `scaffold.py` keeps the other case: adding the harness to a
repository that already exists, where "everything already present is SKIP" and
the additive `settings.json` merge are the whole difficulty.

**Machine is real, prose is placeholder.** `ci.sh` runs, the guards refuse, the
selftests pass; only the sentences nobody but the owner can write are `<...>`.
The acceptance criterion is one line, and it is checked:

```
./ci.sh          # 2 — nobody has said what this project is
                 #     ...fill in the prose, delete START-HERE.md
./ci.sh          # 0
```

**Exit 2, not 1, on the unfilled state.** A harness cannot say whether a project
is sound when nobody has written down what the project is. That is not a
failure, it is the absence of a subject — and because 2 is never a pass, nothing
ships on it either. It is also the first thing the new owner meets, which is the
best available place to teach the idea.

`START-HERE.md` is the only file in that repository about the *template* rather
than about the project. It is a checklist whose last item is deleting itself,
and `ci.sh`'s first ten lines are what make that deletion mean something. Not
the `README.md`: `check_community_health.py` inspects README sections, so a
README holding template instructions would pass that gate while being wrong,
where a placeholder README correctly fails it.

**Neither side has two sources.** Machinery is authored here and pushed there.
Prose is authored there and does not come back. `scaffold.py`'s 372 lines of
string literals are therefore scheduled for removal, not duplication.

**Tier B, without `index/`.** The tier system exists to stop a *probe* from
over-installing into an existing repository; it has nothing to measure on a
repository that does not exist yet, and someone who chooses a harness template
has opted in rather than been retrofitted. Tier A would ship no `gates/` at all,
which is a strange template. `index/` is a retrieval layer for repositories past
800 files, is dead weight on day one, and is the cheapest thing to add later.

## Consequences

Building it found five defects that had been shipping, none of which any check
here could see, because no check here had ever looked at an assembled repository:

| Found | Fix |
|---|---|
| The acceptance suite ran `ci.sh` against an **untracked tree**, so every `git ls-files` gate examined nothing | `ci()` stages first (#72) |
| `consolidating-notes` named `${CLAUDE_PLUGIN_ROOT}/…/consolidate.py`, which dies when the plugin is uninstalled | ships as `scripts/consolidate.py` (#72) |
| `drift.py` and `consolidate.py` were documented by a shipping skill and installed by nothing | added at tier B (#72) |
| `check_docs_runnable.py` read a ` ```markdown ` sample as a live command | fenced samples skipped (#70) |
| `repo-explorer` lived in the plugin and was named by a payload skill | moved to `shared/agents/` (#73) |

Two absences the template had to fill, both of which the scaffolder had been
shipping to strangers:

- **No `.github/workflows/`.** The scaffolder produced only `ci.sh` — the
  laptop-only layer this repository's own README calls the weakest of three.
- **A `TODO` in `SESSION_BRIEF`**, asking for the in-flight plan to be reported.
  Shipped as a TODO, to other people (#74).

`scripts/selftests/` and `scripts/baselines/` are gone. Nothing ever used
either, and `probe_repo.py` already records that the `selftests/` spelling lost
to `selftest.py` sitting beside the checks it proves — an empty directory in the
losing spelling is an invitation to fork the convention. The kept-answer store
moved from `docs/readings/` to `.claude/readings/`: it is machine-written state,
not documentation.

## Alternatives

**Extract the template from this repository.** Rejected: what is here is a
plugin-development repository plus a parts bin. Copying it hands somebody
`eval/`, `guide/`, eleven `docs/decisions/` about our choices, and a `CLAUDE.md`
describing three identities they do not have.

**Ship a filled-in example project.** Rejected: the new owner must then delete
somebody else's content, and will not delete all of it. Six months later the
repository still carries the example's name in three files. A placeholder is
worse to read and better to finish — and `check_templates_filled.py` can see it,
which is the whole argument.

**One template per tier.** Rejected: three trees to keep in step, and two of
them for a probe result that a new repository cannot produce.
