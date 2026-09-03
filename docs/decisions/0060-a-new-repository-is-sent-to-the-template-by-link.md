# 0060 · A new repository is sent to the template, by link

**Date:** 2026-09-03. **Status:** accepted.

## Context

0057 split the two cases: `cc-repo-harness-template` is the starting point
for a repository that does not exist yet, and `scaffold.py` adds the harness
to one that does. The plugin then kept offering only the second. Its skill
ran `scaffold.py`; its first-session notice measured the tree and pointed at
the assessment; neither said the word *template*. Somebody installing the
plugin into an empty repository got a scaffold fitted around nothing —
placeholders, no CI workflow, no `START-HERE.md` — while the assembled tree
sat one repository away.

## Decision

**The plugin points at the template. It does not copy it.** Three places say
where it is: the `bootstrap-repo-harness` skill asks which case first and
gives the link and the one-line `gh repo create` command with `--template`;
the first-session notice prints
the link when the tree has nothing tracked; the README's scaffold section
has the two-way table.

A script that fetched the template's tarball into an already-initialised
empty repository was written and removed the same afternoon. GitHub's *Use
this template* and `gh repo create --template` already do the job for the
common case, the repository that does not exist yet; the remaining case, a
`git init` with nothing in it, is a clone away. Three hundred lines of
payload for that is the kind of convenience this plugin exists to refuse:
it would have been a second scaffolder, with its own selftest, its own
refusal rules and its own drift from the first.

## Consequences

- `git ls-files` still decides the case, and the skill says so. Nothing
  tracked, or only what GitHub writes at creation, is new and goes to the
  template. Anything else is a repository that exists and gets `scaffold.py`.
- Steps 1 to 3 of the skill — assess, decide, plan — have nothing to work on
  in a new repository and are skipped for it. Step 4's "read the guards
  before trusting them" is not: the template ships six.
- The template repository is the one place the assembled tree lives. The
  plugin carries its address, not its contents.
