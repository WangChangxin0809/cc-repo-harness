---
paths:
  - ".claude/settings.json"
  - "scripts/context/session_brief.py"
---

# We wire to `shared/` for payload, `scripts/` for templates

This is hard rule 5. A scaffolded repository gets *copies* of payload under
`scripts/`; we are where those copies come from, so hooks in
`.claude/settings.json` point at the source in `shared/`, not at a copy of
themselves.

The one exception is `session_brief.py`: it is generated per repository
rather than copied, so the hook that runs it points at
`scripts/context/session_brief.py` — our own instance of the generated file,
not a stale duplicate.

-> docs/index.md
