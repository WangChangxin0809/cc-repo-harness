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
the prompt and inject a short ranked list. It must never decide anything, and
nothing may depend on it firing. See the `repo-index` skill, including the
measured latencies — full ranking is too slow here on a large repository, and
the one-hop mode exists for exactly this moment.

## 4 · Reading a subtree — nested `CLAUDE.md`

No wiring at all: a `CLAUDE.md` in any directory loads when files under it enter
context.

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

## 6 · After an action — `PostToolUse`

```json
{"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command",
 "command": "python3 scripts/context/after_edit.py"}]}
```

Receives the call and its result. The action already happened, so this is
delivery, not judgment — a hook here should always exit 0.

The unique thing it knows is what the agent *actually did*, rather than what it
said it would do. Two things are worth saying: that a document governs the path
just edited, and what is adjacent to it in the repo graph. If neither applies,
print nothing; a hook that speaks after every edit stops being read.

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
