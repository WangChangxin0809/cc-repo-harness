# repo-agent-harness

A Claude Code plugin that lays a repository's foundation and then leaves. The
surprising part: **most of this repository is not the plugin.** It is payload —
files copied into somebody else's repository, which must keep working after
this plugin is uninstalled.

- **Covers**: the three identities below, and the rules no script can enforce.
- **Does not cover**: anything true of one directory only (that directory's own
  `CLAUDE.md`), anything a script can block (`shared/scripts/guards/`), anything
  a script can detect (`shared/scripts/gates/`). Detail added here is paid on
  every turn of every session, forever.

## Three identities, one tree

Every file here is exactly one of these. Knowing which one you are editing is
the first question, because the answer changes who is affected.

| Path | Identity | Who gets it |
|---|---|---|
| `.claude-plugin/` `skills/` `agents/` `hooks/` | the plugin | whoever installs it |
| `shared/scripts/` | **payload** | **copied into strangers' repositories** |
| `CLAUDE.md` `.claude/` `scripts/` `docs/` `eval/` | our own harness | only us |

## Hard rules

1. **Anything under `shared/scripts/` ships to strangers.** Write it for a
   repository you have never seen. Tools only we need go elsewhere.
2. **A check nobody has watched fail is a file, not a check.** A new gate or
   guard is not done until you have planted its defect, watched it go red, and
   left a selftest case behind that does the same. See `writing-checks`.
3. **Exit 2 means COULD NOT JUDGE and is never a pass.** No check may swallow a
   status with `|| true`.
4. **Repository behaviour never lives in the plugin.** If installing or
   uninstalling this plugin changes what a repository *does*, that is a bug: it
   makes the repository behave differently for teammates who have not installed
   it. The plugin holds what protects a person from a repository, and what
   teaches a person. Nothing else.
5. **We wire to `shared/` for payload, `scripts/` for templates.** A scaffolded
   repository gets *copies* of payload under `scripts/`; we are where those
   copies come from, so `.claude/settings.json` points at the source. The one
   hook pointing at `scripts/` is `session_brief.py`, which is generated per
   repository rather than copied — ours is our own instance of it, not a stale
   duplicate -> docs/index.md

## Commands

```bash
python3 shared/scripts/guards/selftest.py     # guards can still turn red
python3 shared/scripts/gates/selftest.py      # gates can still turn red
python3 shared/scripts/context/selftest.py    # hooks still reach the model
python3 shared/scripts/selftest.py            # scaffold reaches green, outlives the plugin
python3 shared/scripts/probe_repo.py --root . # what this repo has and lacks
claude plugin validate . --strict             # the manifest, by the first-party checker
```

There is no `ci.sh` here. `.github/workflows/ci.yml` is the entry point, and it
runs the scripts above one per step.

## Where to look

- Full routing table: docs/index.md
- Why things are shaped this way: docs/decisions/

<!-- Cap: 100 lines, enforced by shared/scripts/gates/check_context_budget.py.
     Hitting the cap is a signal to move a rule one hop out, not to compress it. -->
