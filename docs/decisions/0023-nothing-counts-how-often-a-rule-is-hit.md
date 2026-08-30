# 0023 — Nothing counts how often a rule is hit

Date: 2026-08-30
Status: accepted
Removes a mechanism that was built, tested, dogfooded, and then taken out.

## Context

The README has claimed since the beginning that a rule which keeps being hit
stops being prose and becomes a file — *"the third time the same rule is hit"*.
Nothing counted to three. An arrow between two boxes with nothing under it is
the same defect as a check nobody has watched fail, so a counter was built:
`shared/scripts/guards/_recurrence.py`, wired into the dispatcher, twelve
planted defects each caught by exactly one case.

It is gone. What follows is why, because the *reasoning* is the thing worth
keeping — the code is in the history and the reasoning is not obvious.

## What the sentence actually promised, and why a script cannot deliver it

It promised counting violations of a rule that lives in **prose**. A script
cannot detect those: if it could, the rule would already be a gate rather than a
paragraph. That is the definition of why it is prose.

So the counter was narrowed to count **refusals** — a guard fired, which is
observable. That is a defensible thing to count and a different thing from what
the sentence said.

## What five agent products do instead

| Product | Feature | Mechanism | Counter |
|---|---|---|---|
| Cursor | Rules | `/create-rule`, user-invoked. The docs say only: *"When you see Agent make a mistake, update the rule."* | none |
| Cursor | Memories | a background process proposes, the user approves | none |
| Cognition — Devin | Knowledge | *"Devin will automatically suggest Knowledge to remember based on your feedback in chat."* The docs specify no threshold, no repetition count, no dedup algorithm | none |
| Anthropic — Claude Code | memory | Claude decides whether a fact would be useful in a future conversation | none |
| GitHub — Copilot | Memory (public preview) | patterns learned across sessions | none documented |

**Zero of five count.** The one place a number appears is a community skill
("the user corrects the same pattern 2+ times"), and it states that deciding
whether two corrections are the same is contextual judgement rather than
automated matching.

The reason is consistent: what they detect is semantic, in natural language, and
has no canonical form. A model is the only thing that can recognise it.

## Why the counter went anyway, even though refusals *are* structured

Three reasons, in order of weight.

**Nobody has ever wanted the number.** The need was derived from one sentence in
this repository's own README that was itself never validated. This repository's
second hard rule says a check nobody has watched fail is a file, not a check;
the same sentence inverted is that a signal nobody has acted on is noise, not a
signal.

**The signal is weak by construction.** Following `git rerere`, the count lived
in `.git/` — per checkout, never committed, gone on a fresh clone, invisible to
teammates. "The third time" degrades to "the third time, for me, on this
laptop." That objection was raised in the first hour of designing it and then
walked past.

**The assessment already covers the same ground, with the mechanism the industry
converged on.** A guard being routed around, a matcher too narrow, a rule that
keeps causing trouble — an agent reading finds all of these, and the assess step
already ends in a checklist a person decides on.

The strongest argument for keeping it was that it speaks **at the moment of the
attempt**, cross-session, with nobody running anything — moment 5, which this
repository's own doctrine calls the one place prose is guaranteed to be read.
That argument establishes that the mechanism was right. It does not establish
that the need exists.

## What replaces it

Nothing mechanical. When an agent hits a real problem it writes the guard or the
gate, which is the loop that actually closes — a counter telling it to was never
the missing part. The README's arrow now says that instead of *"the third time"*,
because the number had no evidence behind it: fail2ban's default `maxRetry` is
3, the community skill says 2+, and flaky-test practice uses a failure *rate*
over a window with a minimum sample. None of them is about this.

## What was learned that outlived the code

Reading the four reference implementations was worth more than the counter.

**Nobody guesses which part is variable.** fail2ban's identity is the `<HOST>`
its filter captured and nothing else — the log line's content never enters the
key, it is kept as evidence capped at five. Drain3 learns templates by
position-wise disagreement across a cluster (`token2 if token1 == token2 else
"<*>"`), with declared masking regexes for known variables. SonarQube hashes the
literal first line with whitespace removed, then falls back to line number plus
message. Sentry checks a custom fingerprint first, then progressively weaker
automatic signals. Every comparison in all four is literal equality against
either a declared field or the original text.

The removed `normalize()` decided variability positionally — *"index ≥ 2 and not
starting with a dash"* — from a single string with no corpus. That heuristic
appears in none of them. It is also unfixable in principle: which positions vary
cannot be known from one line, which is exactly why Drain needs a cluster.

**fail2ban does not keep timestamps.** `adjustTime` holds one scalar and
rescales it to a rate when the observed interval exceeds the window
(`retry / (now - firstTime) * maxTime`). O(1) memory, and it degrades to a rate
instead of falling off a cliff. Crossing the threshold `del`s the entry, so
"say it once" needs no flag.

**A count is not the hard part.** Deciding that two things are the same is, and
every implementation either routes around it (hash the literal), delegates it
(the rule declares the key), or pays for a model.

## Rejected

**Keeping it and fixing it.** The fix — fail2ban's shape, no invented
heuristic — is strictly better code and would have been about a hundred lines
less. It does not touch either reason the thing should not exist. Fixing
something that should be removed leaves it removed-and-polished.

**Counting gate failures instead.** Same objection, plus a detection problem:
a gate that fails on CI fails on a server, not on anyone's laptop, and reaching
it would take payload out of "standard library, offline" for a number nobody
has asked for either.

## What would have to become true to revisit

Somebody says *"I keep hitting X"* — an actual person, about an actual rule.
That is the evidence that was missing, and it is cheap to wait for.

## Consequences

The counter found one real thing in the minutes it existed: this repository's
own `no_piped_outbound.py` refusing a heredoc whose *body* contained a piped
outbound command, four times in one session. That is logged in the tech-debt
tracker and survives the tool being deleted, which is the point — a one-off
diagnostic that found one thing is not a case for permanent payload in
strangers' repositories.

## Evidence status

| Claim | Grade |
|---|---|
| No mainstream agent product counts repetitions | **checked** against five products' own documentation; absence in docs is not proof of absence in the implementation |
| Prose-rule violations cannot be counted by a script | **argued**, and it is the definition of why they are prose |
| The `.git/` count is too weak to act on | **argued**, never measured — nobody used it long enough |
| An agent writes the guard when it hits a real problem | **unmeasured**. This is the claim the removal rests on, and it is the same claim the whole assess step rests on |
| The four reference implementations work as described | **read in source**: `failmanager.py`, `ticket.py`, `drain.py`; SonarQube and Sentry from their documentation only |
