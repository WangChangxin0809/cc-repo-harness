# eval/ — twenty repositories nobody here has seen

- **Covers**: the corpus, how it was selected, and the two scripts that fetch
  and run it.
- **Does not cover**: whether the harness *helps*. Nothing here measures that.
  This answers the question that comes first — whether the harness survives
  contact with repositories it was not written against.

```bash
python3 eval/fetch.py           # clone the corpus at its pinned commits
python3 eval/run_corpus.py      # probe, scaffold, then every gate, one by one
```

## Why a corpus at all

`shared/scripts/CLAUDE.md` opens with a rule:

> Write for a repository you have never seen. No path, name, or convention from
> this repository may be assumed.

Every acceptance case builds its own fixture, so every one was written by
somebody who already knew what the harness expected. The rule was an assertion.
This is the counterexample generator.

The first run found nothing that crashed and four gates that fail on the
repository's own content rather than on our templates — on day one, before the
owner has done anything wrong. That distinction is the whole output.

## How the twenty were chosen

The criterion was *small repositories built mainly by Claude Code*, because that
is the population this plugin is for: small projects that agents built and that
have to survive becoming large ones.

| Step | Left |
|---|---|
| Commits carrying the `Generated with Claude Code` trailer | 3,919,287 |
| Distinct repositories, from that plus a root-`CLAUDE.md` code search | 300 |
| Alive: not a fork, not archived, pushed during 2026 | 297 |
| Small: ≤ 5 MB, with a language GitHub could name | 65 |
| **Kept: ≥ 50% of the last 100 commits carry the trailer** | **20** |

Eleven languages, 22 KB to 4.8 MB. Three were kept for being extreme rather than
typical: `gum-org` at 22 KB and six commits, `Konda` at 4.8 MB, and
`asml-po-tracker`, whose default branch is an agent-generated name.

The one property no synthetic fixture has: **all twenty already carry a
`CLAUDE.md` somebody else wrote**, and `scaffold.py` skips files that exist. What
the harness does to a repository that already has the file it cares most about
was untested until this corpus existed.

## Pinned, never vendored

`corpus.json` names each repository and an exact commit. `fetch.py` clones them
into `eval/.work/`, which `.gitignore` covers. Three reasons, and the first is
not a preference:

1. **Nine of the twenty carry no licence at all**, which makes redistributing
   them not ours to do; two more are GPL-3.0.
2. Our own gates would judge them. `check_docs_index.py` wants every file under
   `docs/` routed, and `before_write.py` and `drift.py` scan every tracked
   markdown file. Vendoring would mean adding exclusions to checks that **ship
   to strangers**, to make our own repository convenient.
3. A frozen copy stops being an unseen repository within a few months, which is
   the entire property being bought.

SWE-bench ships instance IDs and commit SHAs for the same reason.

## Reading a run

`results/latest.json` holds the full record; the terminal summary is the part
worth reading. Four outcomes, and they are not ranked by severity:

| Outcome | What it means |
|---|---|
| **crash** | Non-zero that is not 1 or 2, or a traceback. The harness broke. |
| **exit 2** | It could not judge. On a real repository this is often correct, and always worth reading. |
| **judged-the-repo** | Red about the repository's own content rather than our templates. **This is the column the corpus exists to produce.** |
| red for placeholders | Expected, and not reported. A fresh scaffold is supposed to be red that way. |

The third row is the interesting one because it is the failure that is hardest
to see from inside: a check that is correct in the abstract and rude in
practice, telling somebody their working repository is wrong about a convention
they never agreed to.
