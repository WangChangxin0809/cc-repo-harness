---
name: github-surface
description: Write everything GitHub itself reads — README.md, CONTRIBUTING.md, the community health files (SECURITY, CODE_OF_CONDUCT, LICENSE, issue and pull request templates), and the workflows under .github/workflows/. Use this when creating or rewriting any of those, when deciding whether a sentence belongs in the README or in CONTRIBUTING, when GitHub's Community Standards page reports something missing, when adding or reviewing CI, or when a repository is going public. Not for docs/ — that is the writing-docs skill.
---

# The GitHub surface

Three documents answering three different questions. Mixing them is the
expensive mistake in this category, because the result reads complete.

| File | Answers | Reader | Failure mode |
|---|---|---|---|
| `README.md` | What is this, and how do I run it | Someone passing through | Becomes a shrunken architecture document |
| `CONTRIBUTING.md` | How do I take part, and what do you want | Someone about to change it | **Becomes a second quick start** |
| Community health | Conduct, disclosure, licence, templates | The platform, and outside arrivals | Missing — and GitHub publishes the gap for you |

**Writing CONTRIBUTING as a second quick start is the standard failure.** It
reads fine: install the dependencies, run it, here is the directory layout. And
every single thing that actually stops a contributor is absent — who reviews
their pull request, how long before anyone replies, what kind of change will
simply not be accepted, where to send a vulnerability. Unable to answer those,
they guess, or they leave.

## These files need conventions of their own

`docs/` conventions are designed for someone already inside: a scope header
answers "does this document cover my situation", a routing table answers "which
one do I read", immutability answers "is this still current". The public face
has none of those problems. Its reader has a repository URL and thirty seconds.
Adding a "does not cover" section to a README applies internal governance to a
problem that does not exist there.

In exchange it has a constraint `docs/` does not: **GitHub renders it.** File
name, location, and in places even heading level change what the platform does —
`SECURITY.md` becomes the "Report a vulnerability" button, `CODE_OF_CONDUCT.md`
appears in the community profile, `.github/ISSUE_TEMPLATE/*.yml` replaces the
blank issue box. Getting the path wrong is not a style problem; the feature
silently does not appear.

## README

Ten sections. Take the content of each from a document that already exists in
this repository, and note where you took it from. A section you have to invent
is a document the repository is missing — record that in
`docs/exec-plans/tech-debt-tracker.md` rather than writing plausible text.

1. **One sentence.** Write this before anything else; the other nine take their
   pitch from it. Criterion: it contains a concrete noun ("3v3 tactical
   top-down shooter"), not a category ("a game project").
2. **Badges** — build, licence, version. Only ones that are live.
3. **What it does**, in a paragraph, for someone who does not know the domain.
4. **Screenshot or a thirty-second demo.** For anything with a visible surface
   this is the highest-value block on the page.
5. **Quick start** — the shortest path from clone to something happening.
   Criterion: run it verbatim in a fresh clone. Untested quick starts are the
   most common broken thing in any README, and the first thing a newcomer hits.
6. **Requirements**, with versions.
7. **Usage** — the two or three things people actually do.
8. **How it fits together**, in a few lines, pointing at `ARCHITECTURE.md`.
9. **Contributing** — one line pointing at `CONTRIBUTING.md`.
10. **Licence.**

Length follows the size of the project, not the number of sections. A small tool
merges several of these into a paragraph and is finished.

## CONTRIBUTING

Answer what a contributor cannot find out by reading the code:

- **What this project wants right now.** Which kinds of change are welcome, and
  which will be declined however well made. Saying so is a kindness; discovering
  it after two weeks of work is not.
- **Before you open a pull request** — the one command that must pass, and what
  a review looks for. If the repository has `./ci.sh`, this is one line.
- **Who reviews, and how fast.** An honest "usually within a week, sometimes
  longer" beats silence. Unstated expectations are read as neglect.
- **How to file a good issue** — what to include, where the logs live.
- **How to say something is a security problem** — one private channel, named,
  pointing at `SECURITY.md`. A public issue tracker publishes the report.
- **Development setup**, only if it differs from the README's quick start. If it
  does not, link to it. This is where the second quick start creeps in.
- **Commit and branch conventions**, if enforced. If a check enforces them, name
  the check instead of restating the rule — the check's failure output is where
  the rule will actually be read.

## Community health files

| File | Location | What the platform does with it |
|---|---|---|
| `LICENSE` | root | Shown in the sidebar; without it, nobody may legally use the code |
| `SECURITY.md` | root or `.github/` | Becomes the "Report a vulnerability" path |
| `CODE_OF_CONDUCT.md` | root or `.github/` | Listed in the community profile |
| `CONTRIBUTING.md` | root or `.github/` | Linked from the new-issue and new-PR pages |
| `.github/ISSUE_TEMPLATE/*.yml` | fixed | Replaces the blank issue box |
| `.github/PULL_REQUEST_TEMPLATE.md` | fixed | Prefills the PR description |

`SECURITY.md` holds how to report and what counts as a vulnerability. The rules
themselves live where they run, and each has one home:

- what must never leave the machine is a guard
- what must never enter the tree is a gate
- why the boundary sits where it does is a decision record

See `writing-checks`.

Issue templates are worth more than they look: they are the one place you can
ask for the version, the platform, and the exact error *before* the round trip
that would otherwise cost a week.

## Check it rather than remembering it

```bash
python3 scripts/gates/check_community_health.py
```

Ships with this plugin. It reports which community health files are absent,
which README sections are missing, and — the one that actually rots — which
links in the public-facing files point at nothing. Broken links in a README are
the first thing an outsider hits and the last thing anyone re-reads.

Two things it deliberately does not judge: whether the prose is any good, and
whether the quick start works. The second one has no substitute for running it
in a fresh clone, so put that in `CONTRIBUTING.md` as a release step.

## What runs on the platform

`.github/workflows/` is the third layer, and the only one nobody can skip: the
hooks act while an agent is working, `ci.sh` acts before you push, and this acts
before anything merges. A check that lives only on a laptop is the weakest of the
three, because it is the one no one is obliged to run.

**Call the roster; do not restate it.** One step running `./ci.sh` beats twelve
steps naming twelve scripts. Two lists drift, and the day they do, the laptop and
the server disagree about whether the repository is sound — with the laptop being
the one people believe.

**Judgement does not belong in YAML.** A condition written into a workflow cannot
be run before pushing, cannot be tested, and dies with the provider. Every step
is one line invoking a script; the script is where the thinking goes.

Six settings, each of which was a real defect somewhere before it was a rule:

| | Why |
|---|---|
| `uses: owner/action@<40-char sha>  # vN` | A tag is mutable. Referencing by tag is a standing promise from whoever can move it |
| `persist-credentials: false` on checkout | Otherwise the job's token sits in `.git/config` where every later step, and anything a later step runs, can read it |
| `permissions:` at the top, least privilege | The default is generous and invisible |
| `timeout-minutes:` on every job | The default is six hours, which turns a hang into a queue nobody notices |
| `cancel-in-progress` on pull requests **only** | A cancelled run on the default branch leaves a commit nobody ever judged in the history every later bisect is measured against |
| no `paths:` filters | A docs-only change is exactly what breaks a routing table or a link check, so "skip CI for docs" skips the checks most likely to catch it |

**Never `|| true`, and never swallow a status.** Exit 2 means *could not judge*
and must fail the step. A step that returns 0 when it could not run manufactures
a green square somebody will trust.

Pin linters in a requirements file rather than inline, so Dependabot can see
them. A version written into YAML is one nothing updates.

### Check it rather than reviewing it

```bash
actionlint                              # syntax, expression types, shellcheck over every run:
zizmor --no-progress .github/workflows/ # unpinned actions, credential persistence
```

Run against this repository's own workflow the day it was written — by someone
who had read the security section of its README that morning — `zizmor` found
ten: seven unpinned actions and three checkouts leaving the token behind. That
is the whole argument for a check over a convention, and it is why these two run
in CI rather than living in a contributing note.

## When the repository is bilingual

Keep the public face in the language of the audience you are asking to
contribute, and say in one line where the other language lives. What breaks
silently is a check whose patterns were written for one language and which keeps
scanning the file after it is translated: it still runs, still passes, and
matches nothing. If a gate covers these files, verify it can still turn red
after a translation — see `writing-checks` on vacuous passes.

## References

| File | Read when |
|---|---|
| `references/templates.md` | You want the skeletons, and the community health file bodies |
| `references/workflows.md` | You are writing or reviewing `.github/workflows/` |

Related skills: `writing-docs` (everything under `docs/`), `writing-checks`
(the gate above), `bootstrap-repo-harness` (`SECURITY.md` is scaffolded there).
