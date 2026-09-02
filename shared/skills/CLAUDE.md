# shared/skills/ — payload, written for a repository you have never seen

The other half of the split root `CLAUDE.md` names: the plugin keeps one
skill, and these five are copied into a target repository's `.claude/skills/`
by `scaffold.py`, at the tier that earns them (0024). They are not discovered
here: Claude Code lists skills only from `.claude/skills/`, `~/.claude/skills/`
and a plugin's `skills/`, and this directory is none of those.

How one reaches a model in *this* repository: line 8 of each `SKILL.md` is a
`Governs:` line naming the paths it is for, and `before_write.py` delivers the
skill the moment one of those paths is about to be written. No listing, no
standing cost, no slash command — read the `SKILL.md` directly when you want
it earlier than that.

- Keep the `Governs:` line on line 8, or within the first ten lines; the
  delivery scans no further.
- Write for a stranger's tree: no path, name or convention of ours may be
  assumed, and an example command must be one their repository can run.
- A skill's description is paid on every turn of every session in the
  repository it lands in. One line; the body is free.
- Adding a skill means adding it to `scaffold.py`'s tier table, or it is a
  directory nobody receives.
