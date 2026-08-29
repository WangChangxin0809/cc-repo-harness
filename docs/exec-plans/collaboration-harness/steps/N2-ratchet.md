# N2 · The ratchet: no single agent may make it worse

A baseline of known violations, committed, that can only shrink. New violations
fail; existing ones are recorded and tolerated until fixed.

## Consulted

- **Prior art**: `Gizele1/harness-init`, `references/boundary-test-template.md`,
  read in full. It stores `tests/architecture/known-violations.json` and asserts
  the count only shrinks. The idea is right and the implementation has a hole —
  see below.
- **Prior art**: OpenAI's Symphony spec, §8.3. Concurrency control is
  `available_slots = max(max_concurrent_agents - running_count, 0)` plus
  per-state caps, and isolation is by workspace. There is no mechanism anywhere
  in the spec for keeping quality monotonic across concurrently landing agents —
  which is what makes this step ours rather than the orchestrator's.
- **Existing skills**: `writing-checks`, which owns the shape this has to take
  and the rule that it is not done until watched failing.
- **Research**: none. This is a mechanism, not an open question.

## The hole in the prior art, and the fix

Both of their skeletons compare **counts**:

```python
assert len(all_violations) <= len(known)
```

```javascript
expect(allViolations.length).toBeLessThanOrEqual(knownViolations.length);
```

So fixing one violation and introducing a different one passes. Under one human
that is a small leak. Under N concurrent agents it is the normal case: agent A
fixes something in its workspace while agent B adds something in its own, the
count is unchanged, and the ratchet reports success while the codebase moved
sideways.

Compare **sets**, keyed by something stable. Which key is the real decision:
`file:line` moves whenever anything above it moves, so every unrelated edit
would look like a new violation. The key has to survive reformatting and line
drift — likely `(file, importer, imported)` for a layering violation, and
whatever the equivalent identity is per check.

## Why the justification changed

This was first proposed for adoption: a large existing repository cannot be made
green before merging anything, so baseline it. That argument does not survive
the positioning — the intervention point is a *small* project, and a small
project can go green. `ci.sh --fast` being red, with the red as the to-do list,
is right for it.

The surviving argument is stronger and is about growth rather than adoption:
**with agents landing pull requests autonomously, quality needs a direction no
single agent can reverse.** A ratchet is exactly the statement *no agent may
make this worse*. It matters least on day one and most at the moment the
project stops being small, which is the moment this plan exists to survive.

## What has to be decided

**Which checks ratchet and which stay absolute.** Not everything should: a guard
that blocks a destructive command has no acceptable baseline, and giving it one
would be a way of tolerating the thing it exists to prevent. Roughly, the
tolerable ones are checks over pre-existing code the repository inherited; the
absolute ones are checks over actions.

**How the baseline is established without becoming a dumping ground.** A file
that anyone can append to is not a ratchet. Growing it has to be a visible,
reviewed act — and by the same argument as `<!-- unrouted: reason -->`, an entry
without a stated reason becomes a blanket exemption.

## Done when

- [ ] Set comparison, not count, with the identity key chosen and its
      stability argued in this file
- [ ] Watched failing: same count, different violation, must go red — that is
      the case their implementation passes and the reason this step exists
- [ ] Watched failing the other way: a fixed violation still listed must be
      reported, or the baseline never shrinks in practice
- [ ] Selftest cases in both directions, per `writing-checks`
- [ ] Stated which checks ratchet and which are absolute, and why

## Notes

*(Decisions land here as the step runs.)*
