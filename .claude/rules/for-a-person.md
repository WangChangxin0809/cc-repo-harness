---
paths:
  - "README.md"
  - "guide/**/*.md"
---

# These two are read by a person, once, and then closed

Everything else here is written for an agent, which reads every word it is
given and never gets bored. A person skims, decides, and leaves. So the test
for a line in `README.md` or `guide/` is not *is this true* — most of what
should be cut is true — it is **does the reader still need this to make the
next decision.**

Each file serves exactly one:

| | the reader is deciding |
|---|---|
| `README.md` | whether to install this, and what it will do to their repository |
| `guide/` | whether to believe a row on the page in front of them |

## Write it this way

- **Say each thing once, in the place it belongs.** `README.md` currently
  describes what a repository ends up with in three separate sections. Three
  passes over one subject reads as thoroughness while writing it and as
  padding while reading it.
- **Let a section be leavable.** Nobody reads `guide/` end to end; they open
  the section for the row that confused them. Each one stands alone, answers
  its question, and stops.
- **Keep one example.** The first teaches. The second is the first again with
  different nouns.
- **State the number and drop the argument for it.** *"precision 0.88, recall
  0.21"* is the whole of what a reader needs; the paragraph defending the
  method belongs in the decision record.

## Where the cut material goes

Length is rarely the problem — location is. Almost nothing here should be
deleted outright:

- reasoning, evidence, what was rejected → `docs/decisions/`
- how to do a thing, for whoever does it next → `shared/skills/`
- what a script does and why → that script's module docstring, where the
  person changing it is already looking

Moving a paragraph costs one link. Leaving it here costs every reader who was
looking for something else.
