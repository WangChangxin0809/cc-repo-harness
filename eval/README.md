# eval/ — twenty repositories nobody here has seen

- **Covers**: the corpus, how it was selected, the scripts that fetch and run
  it, and the backend that will drive it.
- **Does not cover**: whether the harness *helps*. Nothing here measures that.
  This answers the question that comes first — whether the harness survives
  contact with repositories it was not written against.

```bash
python3 eval/fetch.py           # clone the corpus at its pinned commits
python3 eval/run_corpus.py      # probe, scaffold, then every gate, one by one
python3 eval/nim_smoke.py       # does the provider return a tool call?
python3 eval/nim_smoke.py --compare        # which candidates do it reliably
python3 eval/anthropic_smoke.py --base-url http://127.0.0.1:8788
```

## A backend that is not Claude

The corpus needs a model to drive it, and it should not be Claude — most people
running Claude Code as a harness are not running Claude behind it, so measuring
only Claude measures the wrong population. An OpenAI-shaped provider plus a
translating proxy gets us one cheaply.

That is a chain — **provider → proxy → agent** — and every link fails with the
same symptom at the far end: the agent does little and explains less. So each
link has its own probe and its own CI step, and a red run names the link:

| | asks | fails when |
|---|---|---|
| `nim_smoke.py` | does the provider return an OpenAI tool call? | the model answers in prose |
| `anthropic_smoke.py` | does the proxy turn that into an Anthropic `tool_use`? | the translation drops the tool |
| `.github/workflows/nim-agent.yml` step 3 | does the agent read a file it was not handed? | anything above, plus the agent |

The third is a task, not an assertion: the agent is dropped in a directory
holding `needle.txt` and told to copy its contents into `answer.txt`. A
summarise-this task would be passed by a model that ignored every tool. This one
has a single observable outcome whose answer is nowhere in the prompt.

Both workflows are `workflow_dispatch` only. They spend somebody's API quota.

### Two things measured the hard way

**One probe is not a measurement of tool calling.** `gpt-oss-120b` called the
tool correctly on one machine and answered in prose on a runner minutes later,
on the same prompt — and it was the fastest candidate, so a single sample would
have promoted the one model that could not be relied on. `--compare` takes three
samples and reports `flaky` as a verdict distinct from both pass and prose.

**Silence has more than one cause, and only one of them is a verdict.** These
scripts return 2 rather than 1 when a network will not carry the question, when
a model accepts a request and never answers, or when a free tier spends every
retry throttling. Scoring any of those as failure sends you debugging a key that
was fine.

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
