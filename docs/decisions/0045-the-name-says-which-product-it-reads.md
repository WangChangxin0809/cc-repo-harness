# 0045 — The name says which product it reads: `cc-repo-harness`

Date: 2026-09-02
Status: accepted
Supersedes the name chosen in 0002. Its scope argument stands: this is a
harness on the repository's side, and it never touches the loop.

## Context

0002 chose `repo-agent-harness` to say which side of the boundary the plugin
sits on. It says that. It does not say which product's surface it reads, and
that has become the more important fact.

Everything the instrument measures is a mechanism of Claude Code: a
`PreToolUse` hook, a `paths:`-scoped rule, a skill, a subagent, a slash
command, an MCP entry (0043, `surface.py`). Everything the scaffold writes
lands in `.claude/`. A repository is "harnessed" here in exactly one sense: it
has something at the places Claude Code offers. A name that does not say so
reads as if it were agent-agnostic, and the first question people asked was
whether it works with other agents. It does not, and the name should have
answered.

`repo-agent-harness` also parses two ways: a harness for a repo-agent, or a
repo-side harness for agents. Both readings needed the README to settle them.

## Decision

**`cc-repo-harness`.** `cc` is the host, `repo` is the side, `harness` is the
thing. It is the name people already used in conversation, which is the usual
sign the formal one was wrong.

The marketplace stays `wangchangxin-plugins`; 0002's reason for that holds.
The repository is renamed to match, and GitHub's redirect covers the old
install line until it is migrated.

## Consequences

**Trust is reset again**, for the reason 0002 gave: the trust store follows
the trusting component's name, and a component that changed its identity
should be re-trusted rather than inherit. `~/.claude/repo-agent-harness/` is
not read; `--trust` is one command.

**The install line changes.** `/plugin install cc-repo-harness@wangchangxin-plugins`.
Nobody had installed the old one outside this machine at the time of the
rename, which is why it was cheap and why it was done now rather than later.

**Decisions 0002 and 0022 keep the old name.** They are history, and the
history is that the plugin was called that when they were written.
