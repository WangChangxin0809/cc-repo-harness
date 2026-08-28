# 0003 — The extractor is regexes, and the report says so

Date: 2026-08-28
Status: accepted

## Context

`build.py` contained this:

```python
def try_tree_sitter():
    try:
        import tree_sitter_languages  # noqa: F401
        return "tree-sitter"
    except ImportError:
        return "regex"
```

The import was discarded. Symbol extraction ran through the per-language
regexes in `LANGS` either way. The only thing the package's presence changed was
a string — which was then written into the `Extractor` row of
`docs/generated/index-report.md`, and printed on the build's summary line.

That report is headed **Index negative control**, and its own second paragraph
says: *"This records what the graph cannot see. It is a finding, not a
disclaimer."* It is the file an agent is told to read specifically to calibrate
how much an absence in the graph is worth. On any machine where the package
happened to be installed, it opened by misdescribing how the graph had been
produced.

A negative control that is wrong in its first row is worse than no negative
control, because it is read as evidence. And the failure was silent in the
direction that flatters: it claimed the *better* extractor, so nobody would ever
investigate a result that seemed too good.

`README.md` carried the matching claim in prose — that installing
`tree-sitter-languages` "upgrades the index's symbol extraction". It did not.

Two facts settled what to do about it rather than how to build the missing
feature:

- `tree_sitter_languages` publishes no distribution for Python 3.12 or later.
  `pip install tree_sitter_languages` on 3.13 returns `from versions: none`.
  The README was instructing readers to install a package that cannot be
  installed on the repository's own declared ceiling version.
- `index/benchmark.py` already reports that the graph loses to `frequency` — a
  baseline that returns the most-churned files, ignores the seed entirely, and
  costs nothing — on both corpora it is run against. Whatever the index needs,
  there is no evidence that a better symbol extractor is the top of the list.

## Decision

Delete the probe. `EXTRACTOR = "regex"`, unconditionally, and the report says
`regex` because that is what ran. `README.md` states there are no optional
dependencies, and says plainly that the earlier claim was false.

`index/selftest.py` gains a case asserting the reported value, not merely that
the key exists. A label decoupled from the code that produces it drifts back the
first time someone adds an extractor and forgets the report; the assertion is
what makes that a red build instead of a quiet regression to the same bug.

A parser-backed extractor is still worth having. The path is
`tree-sitter-language-pack`, which is maintained and does ship current wheels.
The bar for adding it is `index/benchmark.py`: it has to beat the regexes on the
pinned corpora, and the number goes in this record when it does.

## Consequences

**The report's `Extractor` row is now a constant.** It stays because removing it
would leave a reader with no statement of provenance at all, and because a
constant that is checked is the cheapest possible place to notice the day it
stops being constant.

**Nobody has to install anything.** The zero-dependency claim in the README is
now true without a footnote, and CI proves it by running on 3.9 and 3.13 with an
empty environment.

**The graph is no better or worse than it was.** This changes no behaviour. It
changes what the repository says about its own behaviour, which is the part that
was broken.

## Rejected

- **Implementing the extractor now, so the claim becomes true.** That is a
  feature, decided on evidence, not a fix for a false statement. Shipping it
  under the pressure of an existing wrong sentence in the README is how the
  wrong sentence gets to choose the roadmap.
- **Keeping the probe and fixing only the README.** The report would still print
  `tree-sitter` on some machines. The lie was in two places and the code was the
  worse of them.
- **Dropping the `Extractor` row entirely.** It is the honest half of the
  mechanism. The row was never the problem; the value was.
