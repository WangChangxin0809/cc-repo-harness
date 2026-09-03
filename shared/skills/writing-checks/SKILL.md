---
name: writing-checks
description: Enforce a convention with machinery instead of prose: PreToolUse guards that refuse an action before it runs, gates that judge the worktree in CI, selftests that prove a check can turn red, layering tests. Use when a written rule keeps being violated, when adding any lint or CI step, when asked to protect a branch or stop a destructive command, or when a check exists that nobody has seen fail.
---

# Guards and gates

Governs: shared/scripts/guards/, shared/scripts/gates/

Two mechanisms, one discipline. A **guard** reads one proposed action before it
runs and may block it. A **gate** reads the worktree at CI time and may fail the
build. Everything below applies to both, because the failure modes are the same.

| | Guard | Gate |
|---|---|---|
| Sees | one tool call, as JSON on stdin | the whole tree |
| Cost | every matching call | once per run |
| Use when | the action is irreversible | the state is detectable |
| Failure | exit 2, stderr goes to the model | non-zero, output goes to a human |

## A guard is a speed bump, not a boundary

Say this out loud before writing one, because the rest of this skill reads like
a promise it cannot keep. A guard matches the *text* of a proposed command:

```
git push origin main | tail -5          BLOCKED
B=push; git $B origin main | tail -5    allowed
```

It also fails open on purpose — a broken guard must not become an unbypassable
wall — so its coverage is best-effort in two independent directions. That is the
right trade for what a guard is actually for: catching the thing you were about
to do out of habit, and explaining why, at the moment you were doing it.

It is the wrong trade for anything adversarial, and for anything where a single
miss is unacceptable. Those get **three** layers, in this order:

| | Mechanism | Why it is stronger |
|---|---|---|
| 1 | `permissions.deny` in `.claude/settings.json` | Evaluated by the harness, not by a regex you maintain |
| 2 | Server-side branch protection, required CI | Survives the laptop, the config, and the plugin entirely |
| 3 | A guard here | Explains *why*, in prose, at the moment of the attempt |

Prefer a deny rule for anything a deny rule can express:

```json
"deny": ["Bash(git push --force:*)", "Bash(git push -f:*)"]
```

Write a guard when the rule is conditional in a way a deny pattern cannot state
— `no_protected_branch_push.py` is the worked example: the rule depends on the
refspec, so `Bash(git push:*)` would block the branch you are allowed to push.
And write a guard when the prose is the product, which is more often than it
sounds. The paragraph on stderr is the highest-value text in the repository.

What a guard must never be is the *only* thing standing between an agent and an
irreversible action.

## Layer 2, concretely: a GitHub ruleset

Layer 2 is the only one that is not running on the machine that would break the
rule, which is what makes it the one worth wiring first. On GitHub that is a
**ruleset** — the successor to branch protection, and worth preferring because
several can apply to one branch, the enforcement status can be flipped without
deleting the configuration, and anyone with read access can see what is
enforced. Overlapping rulesets aggregate, and the most restrictive version of a
rule wins, so adding one never quietly loosens another.

```bash
gh api -X POST repos/OWNER/REPO/rulesets --input ruleset.json
```

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request",
     "parameters": {"required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": false,
                    "require_code_owner_review": false,
                    "require_last_push_approval": false,
                    "required_review_thread_resolution": false}},
    {"type": "required_status_checks",
     "parameters": {"strict_required_status_checks_policy": true,
                    "required_status_checks": [{"context": "checks (3.13)"}]}}
  ]
}
```

Four things that are easy to get wrong:

- **`required_approving_review_count: 0` is not pointless on a solo project.**
  It still forces every change through a pull request, which is what makes the
  status checks run at all. Requiring an approval you cannot give would only
  teach you to add a bypass.
- **`non_fast_forward` is the force-push rule.** It is the one that matters
  most, because a force push is the only operation here that destroys history
  the reflog on someone else's clone cannot recover.
- **Require a status check only once the job producing it exists.** The name must
  the job as GitHub reports it — including the matrix suffix, `checks (3.13)`,
  not `ci`. A required check that never reports blocks every merge forever, and
  it looks exactly like a broken CI.
- **A bypass actor is a decision, not a detail.** Granting the admin role
  `bypass_mode: always` means the rule is advice for exactly the person most
  able to break it at 2am. Prefer no bypass, and accept the friction; if you
  add one, say why in the decision record.

The rule that cannot be expressed here goes back to layer 1 or 3. That is the
normal case, not a failure — the three layers exist because none of them covers
what the others do.

## Write the failure modes before the check

List how the thing you are guarding actually goes wrong — concretely, each one a
sentence naming an input and a wrong outcome. Then write one criterion per mode.

Doing this first is the single biggest predictor of a check that works. Writing
the implementation first and the criteria after produces criteria that are a
mirror of the implementation: they pass on the day you write them and are blind
to everything the implementation forgot.

A caveat that saves a day: some entries on your list will turn out not to be
real failure modes. When an injection cannot make a criterion go red, the
correct move is usually to delete the criterion, not to tighten it.

## Three exit codes, and the third is the one people get wrong

```
0 = judged, passed
1 = judged, failed
2 = could not judge
```

**Exit 2 is not a pass.** Missing tool, unparseable config, no baseline to
compare against — every one of those must be loud. A check that returns 0 when
it could not run is worse than no check, because it manufactures a green that
someone will trust.

And exit 2 is a *shared* observable: several different failures all exit 2. When
a selftest asserts only the code, it passes for the wrong reason. Assert the
reason too — grep the stderr for the specific message.

The same applies one layer up. Shell-level 126 and 127 mean the check never
started, and they look exactly like a check that ran. In a three-stage chain
each stage's exit code masks everything downstream, so after fixing one layer,
rerun — the layer beneath it has been invisible the whole time.

## Silent success, verbose failure

A check that prints on success trains everyone to skim its output, and then the
one run that printed a warning goes unread. Print nothing when passing. When
failing, print what was expected, what was found, and the command that fixes it,
with a path to the document that explains why the rule exists.

That failure message is the highest-value prose in the repository: it is the
only text guaranteed to be read at the moment it is relevant, by a reader who
has already made the mistake.

## Prove it can turn red

A check nobody has watched fail is a file, not a check.

```bash
cp target.py target.py.bak          # never `git checkout --` to restore:
                                    # it discards unrelated uncommitted work
                                    # and does not restore untracked files
# inject a defect the check must catch
python3 scripts/guards/selftest.py  # must report exactly one failure, by name
cp target.py.bak target.py && rm target.py.bak
```

Make the injection **silent**, not a crash. An injection that raises is the easy
case — it would be caught by anything. The injection that matters makes the
check return "clean" while the defect is present.

Every guard module ships a `CASES` list with at least one blocking and one
non-blocking case. The non-blocking one is not optional: it is what proves the
check has not become a wall that people learn to bypass.

## Where checks go blind

**A criterion can pass vacuously.** If the preconditions were never established
— the entities do not exist yet, the counter was captured by value, the signal
carries an argument the matcher does not accept — then every negative assertion
is true of nothing. Vacuous passes look identical to real ones.

**The defence is one positive assertion per group:** something that must be
non-empty, non-zero, present. `text != ""` catches what "does not contain X"
and "is tall enough" both let through.

**Redundant mechanisms mask each other.** When two things independently
guarantee a property, breaking one leaves the other holding it, and neither
check goes red. Give each mechanism an observable that belongs only to it.

**Superset matching hides a broken set operation.** Asserting that the report
"contains b.md" stays green when the code puts *everything* in the report.
Assert a count, or keep a control set that must always come back empty.

**A parsing check that normalizes away an operator reads the answer backwards.**
Stripping a `!`, or exempting matches inside string literals, is how a check
starts approving what it exists to forbid. When a false positive tempts you to
open an exemption channel, narrow the pattern instead.

## Structural tests for layering

The most durable convention is one a machine can check. Declare the layers —
`types → config → repo → service → runtime → ui` or whatever this codebase has —
and gate the direction of imports.

```bash
python3 scripts/gates/check_layering.py
```

A starter ships in this plugin under `shared/scripts/gates/`. It reads the layer
order from `.claude/guards.json`, walks imports, and reports each edge that
points the wrong way with both file paths. Prose describing a layering is
followed for about a month; a gate is followed indefinitely.

Two things decide whether this gate works:

1. **Judge on a median, not a maximum.** Variance across identical runs is
   real, and the maximum is the noisiest statistic available.
2. **Put it in a third place that always runs.** A cross-package rule living
   inside the packages it validates is never seen by a run that tests only the
   packages you changed.

## Run gates in a clean worktree

A working tree contains local files and, sometimes, another session's
half-finished work. Green measured there is not green. Use a fresh checkout, or
a `git worktree`, whenever the result will be reported as a fact.

Record every measured number with the commit it was measured on. Readings without
a commit expire silently, and the person who inherits the investigation restarts
from a number that stopped being true weeks ago.

## Wiring

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit",
  "hooks": [{"type": "command", "command": "python3 scripts/guards/dispatch.py"}]}]}}
```

One line, one script. `.claude/` holds wiring; the judgment lives in `scripts/`
where it is reviewable, testable, and portable. The dispatcher discovers every
`*.py` in its directory, so adding a rule is adding a file. The matcher names
every tool a guard judges, and `selftest.py` fails when a guard can refuse a
tool the matcher never shows it -- behind the wrong matcher, a guard is a file
that never runs, and a dispatcher that fails open never says so.

A broken guard **fails open** — deliberately. One syntax error in one module
must not become a wall nobody can get past, in a mechanism that runs before
every command. The selftest is what catches the broken module; the dispatcher's
job is to keep working.

## References

| File | Read when |
|---|---|
| `references/guard-contract.md` | The exact stdin/stdout/exit contract per hook event |

Each shipped guard documents what it matches, and what it deliberately does not,
in its own docstring — which travels into the repository with the file.

Related skills: `writing-docs` (where the failure message should point),
`bootstrap-repo-harness` (installing the dispatcher and `ci.sh`).
