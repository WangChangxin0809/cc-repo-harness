# 0048 — The assessment's agents live under `agents/assess/`, and the second pass does not re-run the suite

Date: 2026-09-02
Status: accepted

## Context

The assessment needed an agent at five points: two briefs in dimension 1,
one in 2, two in 4, the blind promise tester, and then the reading. One
agent — `repo-assessor` — did all of it in one context, and `commands/
assess.md` told a person's own session to do the same. That agent had to
know five module names, where each brief sat in the JSON, and which of six
flags each answer fed. It then scored a page it had just spent its context
answering, with all five dimensions in view.

And every flag re-ran the instrument. Putting one reading on the page meant
running the repository's suite again, minutes per answer, so the answers
were rarely fed back at all.

## Decision

**One reader, parameterised by dimension**, at `agents/assess/reader.md`.
It takes a run, a dimension and a phase. In the `answer` phase it runs
`briefs.py`, which writes every brief that dimension left as a file naming
the flag its answer feeds; the reader needs no module name. In the `read`
phase it gets `review.py --brief --dimension N` and writes a score, a
reason and `moves_if` for that dimension's sub-items only -> 0046

**The blind promise tester moves beside it**, as `assess-promise-tester`.
Its tool list is unchanged; the blind is the tool list -> 0040

**`factsheet.py --from RUN.json`** reads a run back and applies the answer
flags to it. Nothing is re-measured; the second pass takes a second. The
run's JSON was already the record; this makes it the input.

**`repo-assessor` orchestrates.** It runs the instrument, spawns three
readers to answer, one promise tester if asked, the second pass, ten readers
to read, and the grade. It holds numbers and produces none.

**The manifest lists every agent file.** A listed `agents` path replaces
the default directory rather than adding to it, and the first-party
validator takes files only. So all four are named, and
`check_plugin_structure.py` now turns red on a manifest that lists some
agents and drops others, or names one that is not there.

## Consequences

Each agent description is always-on for every session on the machine. The
two new ones are under a hundred tokens each, and the reader replaces
nothing that was there; the standing cost of the plugin rises by that much,
which 0024's ledger has to carry.

Ten reader spawns per assessment where there were none. They read the
repository and never run it, so the cost is context, not minutes, and it is
the step that decides what the page says.
