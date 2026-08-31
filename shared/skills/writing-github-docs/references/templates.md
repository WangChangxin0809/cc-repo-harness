# Skeletons for the public face

Fill each section from something that already exists in the repository. A
section you have to invent from nothing is a document the repository is missing;
record that in `docs/exec-plans/tech-debt-tracker.md` rather than writing
plausible text that nobody can later verify.

---

## `README.md`

```markdown
# <project>

> <One sentence. A concrete noun, not a category. This line sets the pitch for
> everything below, so write it first and rewrite it last.>

[![CI](…)](…) [![License](…)](…)

<A paragraph for someone who does not know the domain: what problem, for whom,
and what makes this answer different from the obvious one.>

<!-- A screenshot or a 30-second demo goes here. For anything with a visible
     surface this is the highest-value block on the page — higher than any
     paragraph you could write instead. -->

## Quick start

```bash
git clone <url> && cd <project>
<one command>
```

<What you should now see. Being concrete here is what lets a reader tell
"working" from "silently did nothing".>

## Requirements

- <runtime> <version>
- <the one non-obvious system dependency, if there is one>

## Usage

<The two or three things people actually do, each with the command.>

## How it fits together

<Three or four lines. Then: see [ARCHITECTURE.md](ARCHITECTURE.md).>

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

<SPDX identifier> — see [LICENSE](LICENSE).
```

The quick start is the block to test rather than review. Run it verbatim in a
fresh clone; an untested quick start is the most common broken thing in any
README and the first thing a newcomer hits.

---

## `CONTRIBUTING.md`

```markdown
# Contributing

Thanks for looking. This file answers what you cannot find out by reading the
code — the code will tell you how things work, not what we want.

## What we are looking for right now

- **Welcome**: <kinds of change>
- **Ask first**: <changes worth a discussion before the work>
- **Will be declined**: <however well made — and why>

Saying this is a kindness. Finding it out after two weeks of work is not.

## Before you open a pull request

```bash
./ci.sh
```

It must be green. It is silent when it passes; if it prints anything, that is
the failure telling you what to do.

<What review looks for beyond green — a test that would have caught the bug,
a decision record for anything that changes an interface.>

## What happens next

<Who reviews. How fast, honestly — "usually within a week, sometimes longer"
beats silence, because unstated expectations are read as neglect.>

## Filing an issue

<What to include: version, platform, the exact error. Where logs live.>

## Security

Not here, and not in the issue tracker: [SECURITY.md](SECURITY.md).

## Conventions

<Commit format, branch naming — only if enforced. If a check enforces one,
name the check instead of restating the rule: the check's failure output is
where the rule will actually be read.>
```

Development setup goes here **only if it differs from the README's quick start**.
If it does not, link to it. This is the exact spot where CONTRIBUTING turns into
a second quick start, which is the standard failure of this document.

---

## `SECURITY.md`

```markdown
# Security policy

## Supported versions

| Version | Supported |
|---|---|
| <x.y> | yes |
| < <x.y> | no |

## Reporting a vulnerability

<Where to send it — a private channel, never the issue tracker.>
<What response time to expect. An honest slow number beats no number.>

## What counts

<What this project treats as a vulnerability, and what it does not. Without
this, you will receive reports about things you deliberately allow.>

## Where the rules are enforced

The rules themselves are not prose here, because prose is not enforcement:

| Rule | Enforced by |
|---|---|
| No credentials in the tree | `scripts/gates/` |
| No secrets piped to an outbound command | `scripts/guards/no_piped_outbound.py` |

The threat model belongs in `docs/decisions/` — it is a choice with
alternatives, and it will be revisited.
```

---

## `.github/ISSUE_TEMPLATE/bug.yml`

```yaml
name: Bug report
description: Something behaves differently from what it should
body:
  - type: textarea
    id: what
    attributes:
      label: What happened, and what you expected instead
    validations: {required: true}
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
      placeholder: |
        1.
        2.
    validations: {required: true}
  - type: input
    id: version
    attributes: {label: Version or commit}
    validations: {required: true}
  - type: input
    id: platform
    attributes: {label: OS and runtime version}
    validations: {required: true}
```

Required fields earn their keep here more than anywhere else in the repository:
this is the one place you can ask for the version, the platform, and the exact
error **before** the round trip that would otherwise cost a week.

---

## `.github/PULL_REQUEST_TEMPLATE.md`

```markdown
## What this changes

## Why

<Link the issue or the decision record. A change whose reason lives only in the
PR description becomes unexplainable the moment the PR scrolls out of view.>

## How it was verified

<The command, and what its output was. "Tests pass" is not verification —
which tests, and would they have failed before this change?>

- [ ] `./ci.sh` is green from a clean worktree
- [ ] Documentation updated, or deliberately not — say which
```

---

## `LICENSE`

Copy the full text from [choosealicense.com](https://choosealicense.com); do not
paraphrase or summarize a licence. Without this file nobody may legally use the
code, whatever the README says — and GitHub's sidebar will show "no license",
which is the first thing an evaluating reader checks.
