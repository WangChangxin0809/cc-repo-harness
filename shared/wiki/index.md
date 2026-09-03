# .claude/wiki — what keeps going wrong here, and what was done about it

Written by the plugin's `/learn`, from the session transcripts on the machines
that ran it. **Not for agents.** An agent that reads its own failure catalogue
does worse, not better (WikiSkill, arXiv 2608.27454, table 3: 63.7 → 60.9), so
nothing routes here and `docs/index.md` does not mention this directory. Open a
pattern only when you are writing the guard, gate or rule it asks for.

- `patterns/` — one file per recurring mistake: what triggers it, how often,
  why nothing caught it, and the cheapest thing that would.
- `logs.md` — one entry per `/learn` run.
- `impact.md` — every proposal that came out of a pattern, kept or not.

| Pattern | Count | Route | Status |
|---|---|---|---|
