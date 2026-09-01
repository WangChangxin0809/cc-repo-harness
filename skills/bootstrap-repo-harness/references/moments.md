# The seven moments, wired

What each mechanism receives, what it can do, and what it costs. Read this when
placing something and the choice of moment is not obvious, or when a hook is
wired and nothing appears to happen.

Everything below goes in `.claude/settings.json` as **one line invoking a
script**. The judgment lives in `scripts/`, where it is reviewable, testable,
and survives this plugin being uninstalled.

## 1 · Every turn — `CLAUDE.md`

Loaded into every turn of every session. No trigger, no condition, no escape.

The cost is the whole design constraint: 100 lines is roughly 1,500 tokens paid
forever, against a repository whose conventions will keep growing. So the file
holds only rules that have **no local trigger and cannot be enforced** — which,
after honest classification, is usually three to six of them.

`AGENTS.md` is the cross-vendor spelling of the same idea. If both exist, make
one a pointer to the other; two copies drift, and the drift is invisible because
each reader only ever sees one.

## 2 · Session start — `SessionStart`

```json
{"matcher": "*", "hooks": [{"type": "command",
 "command": "python3 scripts/context/session_brief.py"}]}
```

stdout is injected as context. Paid once per session, so a few hundred tokens is
affordable — but keep it under ~20 lines, because a brief long enough to skim is
a brief that gets skimmed.

The test for whether something belongs here: **could a file have contained it?**
If yes, it belongs in a file. What is left is genuinely temporal — the branch,
uncommitted work, which gates are currently red, whether another agent session
is writing to this repository right now. That last one is worth the hook on its
own: undetected, concurrent sessions produce edits that appear and vanish
between reads, which is very confusing to debug and very cheap to report.

## 3 · Each prompt — `UserPromptSubmit`

stdout is injected before the model sees the turn. Runs on every prompt, so the
latency is paid every time — measure it before wiring anything that touches the
filesystem broadly.

This is the reflex retrieval slot: seed a query from paths and symbols named in
the prompt and inject a short ranked list. It informs and nothing else: the
turn reaches the same result whether or not it fired. See the `repo-index` skill, including the
measured latencies — full ranking is too slow here on a large repository, and
the one-hop mode exists for exactly this moment.

## 4 · Reading a subtree — nested `CLAUDE.md`

No wiring at all. Two mechanisms, and they load the same way:

- a `CLAUDE.md` in any directory, when files under it enter context;
- `.claude/rules/*.md` with `paths:` frontmatter, when Claude reads a file
  matching the glob. Discovered recursively, so `rules/frontend/*.md` works.

```markdown
---
paths:
  - "src/api/**/*.ts"
---
- Every endpoint validates its input before touching the DB.
```

Prefer a rule over a nested `CLAUDE.md` when the scope is not exactly one
directory, or when several unrelated conventions would otherwise pile into one
file. **A rule with no `paths:` is not scoped at all** — it loads at launch at
the same priority as `.claude/CLAUDE.md`, and is charged as such.

Both load only on *Read*. Neither reaches a file created with `Write`, or one
written through the shell; moment 5 covers that gap.

This is the highest-leverage moment and the most under-used. A rule that is only
true inside `src/billing/` costs every other session nothing, and arrives
unprompted for the sessions that need it. When the root `CLAUDE.md` hits its
cap, this is the first place to look — most of what is there is local.

## 5 · Before an action — `PreToolUse`

```json
{"matcher": "Bash", "hooks": [{"type": "command",
 "command": "python3 scripts/guards/dispatch.py"}]}
```

Receives the proposed tool call as JSON on stdin. **Exit 2 blocks it, and stderr
is fed back to the model as the reason** — so the stderr text is not a log line,
it is an instruction the agent will act on. Give it the remedy and a document
path. See `writing-checks` for the full contract.

`matcher` takes a regex over tool names: `Bash`, `Edit|Write|MultiEdit`, `.*`.

**The same moment also delivers, and that is a separate hook.** `dispatch.py`
can refuse; `before_write.py` only informs — what `.claude/rules/` is scoped to
this path, and what document declares `Governs:` over it:

```json
{"matcher": "Bash|Write|Edit|MultiEdit", "hooks": [{"type": "command",
 "command": "python3 scripts/context/before_write.py"}]}
```

Two processes on purpose. Folded into one, a crash in the informer takes the
guards down with it.

It belongs *before* the write and not after, because creating a file is when a
convention is worth most — there is no existing code to copy the shape from.
It advises rather than prevents: measured, the first write lands wrong and the
agent corrects on the retry, because `PreToolUse` hands its context to the model
together with the result of the call that triggered it. What must not be
violated goes in a guard.

## 6 · After an action — `PostToolUse`

```json
{"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command",
 "command": "python3 scripts/context/<your hook>.py"}]}
```

Receives the call and its result. The action already happened, so this is
delivery, not judgment — a hook here should always exit 0.

**Return `hookSpecificOutput.additionalContext`, never plain stdout.** This is
the single most expensive mistake available in this document. Plain stdout is
context only on `UserPromptSubmit`, `UserPromptExpansion` and `SessionStart`;
on every other event it goes to the debug log. A hook that prints its finding
looks correct in a terminal, exits 0, passes a test that reads its stdout, and
delivers nothing to the model. This harness shipped one for months.

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse",
 "additionalContext": "what you want the agent to know"}}
```

The unique thing this moment knows is what the agent *actually did* rather than
what it said it would. That makes it the right home for **what a change just
affected** — callers of an edited function, a config key read elsewhere, a
document that may have just gone stale. Nothing is wired here by default, on
purpose: such a hook always has something to say, and one that speaks after
every edit stops being read. Give it a reason to stay quiet before you give it
a voice.

Neither this moment nor moment 5 sees a file written by a subprocess. Nothing
in Claude Code does — checkpointing, `/rewind` and path-scoped rules all draw
the same line at the built-in file tools. `git status --porcelain` is the only
thing that answers "what actually changed".

## 7 · On demand — skills and subagents

A skill's `name` and `description` are always loaded; the body only on trigger;
`references/` only when read; `scripts/` never enter context at all. That
gradient is the whole design — put the expensive material as far down it as the
reading trigger allows.

Subagents get their own context window. Delegate when the work involves reading
many files whose contents the main conversation does not need — the twenty files
stay in the subagent's context and only the conclusion comes back.

## Checking that a hook is actually wired

```bash
python3 -c "import json;print(json.load(open('.claude/settings.json'))['hooks'].keys())"
```

Then disconnect one deliberately and confirm the harness's own suite turns red.
A suite that survives a disconnected hook is measuring nothing — and this is the
failure that hides longest, because everything still looks installed.
