---
name: find-skill
description: Find a Claude Code skill or plugin somebody else has already written, and judge whether to install it. Use when about to write a skill for something that sounds common, when asked whether a tool integration exists, when looking for a marketplace or a plugin by capability rather than by name, or before adding a skill that would duplicate one already installed.
---

# Finding somebody else's skill

The cheapest skill is the one you did not write. There are 291 plugins in the
official marketplace alone, already on this machine, and the question "does this
exist" is answerable in one grep before it is answerable in an afternoon.

- **Covers**: where to look, in which order, and how to decide.
- **Does not cover**: writing one — that is `writing-checks` for anything that
  can pass or fail, and `writing-docs` for anything that explains.

## Look here first, because it is local and exact

Every configured marketplace is already cloned. Its manifest is one JSON file
with a name, a description, an author and a category per plugin, so this is a
grep and not a network call:

```bash
claude plugin marketplace list      # which ones this machine has
```

```bash
python3 - <<'PY'
import glob, json
for m in glob.glob("~/.claude/plugins/marketplaces/*/.claude-plugin/marketplace.json"):
    for p in json.load(open(m))["plugins"]:
        blob = f"{p['name']} {p.get('description', '')}".lower()
        if "YOUR TERM" in blob:
            print(f"{p['name']:<34} {p.get('description', '')[:80]}")
PY
```

Expand `~` yourself — `glob` does not. Search the *description*, not the name:
plugin names are chosen for branding and the capability is in the sentence.

The official marketplace is `anthropics/claude-plugins-official`. If it is not
in the list:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
```

## Then the wider ecosystem

```bash
gh search repos "claude code skills" --limit 20 --json fullName,description,stargazersCount
gh search repos "awesome claude skills" --limit 10 --json fullName,description
```

Curated lists are worth more than individual hits here, because a skill that
nobody has listed is usually a skill nobody has used.

**`gh search code --filename SKILL.md` is not a substitute.** It returns nothing
useful without the right token scope, and it returns *nothing* rather than an
error when it fails — so it looks like "no such skill exists" when it means "the
search did not run". If you use it, confirm it can find something you know is
there before you trust an empty result.

## Judging one before installing it

A skill is instructions an agent will follow, and a plugin is code that runs on
this machine. Both deserve the same reading as any dependency.

```bash
claude plugin details <name>       # component inventory and projected token cost
claude plugin validate <path>      # the manifest, by the first-party checker
```

Four questions, in this order:

1. **What does it cost every turn?** Claude Code keeps every installed skill's
   `name` and `description` in context in *every repository on this machine*,
   whether or not that repository has anything for it to do. Twenty skills at
   eighty tokens is 1,600 tokens gone before anyone types. `claude plugin
   details` projects this; the bodies are free, the frontmatter is not.
2. **Does it change what a repository does?** A plugin that installs hooks or
   writes files makes your repository behave differently for every teammate who
   has not installed it. That is a bug in the plugin, and it becomes your bug.
3. **Read the hooks.** `hooks/` and any `PreToolUse` wiring is code that runs
   before your tool calls, from a repository you have not read.
4. **Is it maintained?** Last commit, open issues, whether the manifest version
   matches the tags.

If two candidates overlap, prefer the one whose description names the *trigger*
rather than the capability — that is the half Claude Code actually matches on,
and a skill that never activates is a skill you are paying for and not using.

## When nothing fits

Say so plainly and write the thing. Half a match is worse than none: it
activates on the trigger you needed, does something adjacent, and the failure
looks like the agent ignoring you.

Related: `writing-checks` (anything that can pass or fail belongs in a gate or a
guard, not a skill), `github-surface` (if what you are looking for is CI).
