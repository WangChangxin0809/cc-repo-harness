---
name: writing-github-docs
description: Write the repository's public face — README.md, CONTRIBUTING.md, and the GitHub community health files (SECURITY, CODE_OF_CONDUCT, LICENSE, issue and pull request templates). Use this when creating or rewriting any of those, when deciding whether a sentence belongs in the README or in CONTRIBUTING, when GitHub's Community Standards page reports something missing, when a repository is going public or starting to accept outside contributions, or when someone asks how to make the project understandable to people who have never seen it. Not for docs/ — that is the writing-docs skill.
---

# The repository's public face

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

Related skills: `writing-docs` (everything under `docs/`), `writing-checks`
(the gate above), `bootstrap-repo-harness` (`SECURITY.md` is scaffolded there).
