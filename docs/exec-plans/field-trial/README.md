# Field trial

**Find out whether this harness changes what an agent does in a repository
nobody here wrote — judged by that repository, not by us.**

Everything this plugin claims has been argued from inside. The gates were
written here, the fixtures were built here by people who knew what the gates
expected, and the one benchmark that exists lost to a most-churned baseline.
This plan is the arrangement where the repository gets to answer.

## The trap at the centre

**Our own gates cannot be the grader.** `scaffold.py` writes the files
`check_docs_index.py` looks for. Scaffolding satisfies our checks by
construction, so "scaffolded repositories score higher on our checks" is not a
finding, it is a restatement. Any measurement built that way would be a
tautology wearing a number, and it would be a comfortable one — which is why it
has to be named before anything is built rather than after.

The escape is that the corpus repositories carry their own graders. Measured
across the twenty:

| | count |
|---|---|
| carry test files | 16 / 20 |
| declare a runnable test command | 10 / 20 |
| have CI | 14 / 20 |

A repository's own test suite was written by somebody with no stake in this
plugin, before this plugin existed. That is the property we cannot manufacture
and cannot fake, and it is why this plan does not need to borrow SWE-bench's
repositories to borrow its idea.

## Why the corpus is the right population

SWE-bench's subjects are large, mature Python projects — Django, sympy,
scikit-learn. Scaffolding Django is not what this plugin is for and never was.
The population this plugin addresses is *small repositories built mainly by
coding agents that have to survive becoming large ones*, which is exactly what
`eval/corpus.json` selected for: eleven languages, 22 KB to 4.8 MB, ≥ 50% of
the last hundred commits carrying the Claude Code trailer.

So SWE-bench is borrowed as a **construction**, not as a dataset. Its instances
are built from (issue, code change, tests that the change makes pass). The same
construction runs over any repository with history: find a commit that changed
both code and tests, revert the code half, keep the tests, and ask an agent to
make them pass. Zero authoring cost, a grader nobody here wrote, and tasks that
are real because they already happened.

## What would end this

**If the twenty repositories cannot be made green untouched, there is no
instrument.** A repository whose tests are already failing cannot tell you
anything about an "after" state; red stays red and the number means nothing.
The corpus size for effect measurement is not twenty, it is however many reach
green, and that figure is unknown. It could be three.

**If the scaffolded and unscaffolded arms score alike on the repositories' own
tests**, then the harness does not change task outcomes. What survives that is
the same thing that survives the other plan's abort branch: the trust gate, and
the teaching. Neither claims to move a test suite, and neither would be
refuted.

## Why this order

The falsifier is first here rather than second, because it is also the cheapest
step and the instrument for everything after it. A1 needs no model, no API
budget, and no agent — it runs test suites.

**Phase A's second step is "do no harm", not "does it help".** The harness's
first obligation to a stranger's repository is not to improve it. A repository
that goes from green to red because we scaffolded it is a defect of a different
order than one we failed to help, and it is nearly free to detect once A1
exists. The corpus run already found four gates that fail on repositories' own
content on day one; that is a rudeness finding, and this is the harm version of
the same question.

**Phase B is not measurement and is still upstream of it.** An "after" arm does
not exist until scaffolding is something a maintainer would actually accept.
Telling 19 of 20 repositories that their community health is wrong, on the first
minute of contact, over conventions they never agreed to, is not an intervention
whose effect is worth measuring — it is one that would be uninstalled before it
had an effect.

## How this folder works

Same rules as [collaboration-harness](../collaboration-harness/README.md), and
for the same reasons stated there: **this file owns state, step files own
substance and never restate status**; a step earns a file when it has decisions
to record; a step file is written when the step is entered, not upfront; and
every step file carries `## Consulted`, which may say "none, because" but may
not be absent.

## Steps

**A · An instrument that can tell before from after**

- [ ] doing   [A1 · How many of the twenty are green untouched](steps/A1-green-untouched.md)
- [ ] todo    History, which the corpus does not currently have. `eval/fetch.py`
              clones `--depth 1` because nobody needed the history and 30 MB was
              the point. Task generation needs it. Deepening the fetch is a
              small change and a large download, so it waits until A1 says how
              many repositories are worth downloading.
- [ ] todo    Do no harm: scaffold every green repository, re-run its own tests,
              and assert nothing went red. A harness that breaks a stranger's
              build has a defect of a different order from one that fails to
              help. Cheap once A1 exists, and it is the one result that would
              stop the plugin being offered to anyone at all.

**B · Something a maintainer would accept**

- [ ] todo    The day-one red problem, and it is the finding the corpus was
              built to produce: `check_community_health` fails 19/20,
              `check_context_budget` 13/20 ("total 286 lines, cap is 100"),
              `check_docs_index` 11/20, `check_docs_layout` 11/20 ("14 file(s)
              loose at the top of `docs/`"). Every one of those is correct in
              the abstract and rude on contact. The options are narrow — a
              baseline recorded at scaffold time so gates judge *change* rather
              than *state*, an adopt mode, or fewer gates on by default — and
              the choice has to be argued once and written down, because it
              decides what this plugin is: a check on new work, or a verdict on
              existing work.
- [ ] todo    `check_plugin_structure` abstains 20/20, which is the correct
              answer and a wasted step. It checks a `.claude-plugin/` that
              almost no repository has, and `shared/scripts/CLAUDE.md` already
              calls it "a mistake being carried, not a precedent". The corpus
              turned the judgement into a measurement.
- [ ] todo    `probe_repo.py` reports `gates / guards 0 / 0` on this repository
              and `~0 tokens/turn` of skill cost while `claude plugin details`
              says ~1,312. Already recorded in tech-debt; it becomes blocking
              here, because the probe is what decides a repository's tier and a
              wrong tier installs machinery that rots.

**C · The effect**

- [ ] todo    Task generation, SWE-bench's construction over our corpus: commits
              that changed code and tests together, code half reverted, tests
              kept. What has to be decided is what makes a *usable* instance —
              a commit whose tests fail before and pass after, with the revert
              not spanning half the repository.
- [ ] todo    Paired arms, ± scaffold, same repository, same task, same model.
              Paired rather than two samples, for the reason A1 of the other
              plan already recorded: paired binary outcomes are what McNemar's
              test is for, and independent samples throw away the pairing that
              makes a small corpus say anything.
- [ ] todo    The no-scaffold baseline is recorded before any mechanism changes
              in response to it. A baseline measured afterwards is a number
              chosen to be beaten.

**D · Across models, which is now possible and was not**

- [ ] todo    Re-run the effect measurement on a second and third backend.
              `.github/workflows/nim-agent.yml` proved the path end to end:
              provider returns an OpenAI tool call, cc-switch's proxy turns it
              into an Anthropic `tool_use`, and Claude Code driven by
              nemotron-3-super read a file it was never handed. Most people
              running Claude Code as a harness are not running Claude behind it,
              so a result measured only on Claude is a result about a minority.
- [ ] todo    Report what the harness costs each backend, not only what it
              buys. A 2,359-token standing cost is a different proposition on a
              model with a 200k window than on one with 32k, and Claude Code
              already warns it cannot size an unrecognised model's window —
              which means the corpus runs are currently assuming 200k without
              checking.

## Not doing, and why

| Proposed | Why not |
|---|---|
| Use SWE-bench itself | Its subjects are large mature projects; this plugin is for small ones that agents built. Borrowing the construction costs nothing and keeps the population right. Revisit if the corpus cannot produce enough usable instances. |
| Grade with our own gates | Tautology. `scaffold.py` writes what the gates look for. The gates are still worth *reporting* — as a description of what changed, never as the score. |
| An LLM judge | The repositories carry deterministic graders already. A judge would add cost, variance, and a second thing to validate, to replace a test suite that is free and exact. |
| Vendor the corpus into this repository | Nine of the twenty carry no licence. Already decided and recorded in `eval/README.md`; repeated here only because a plan that needs history will be tempted. |
| Measure convergence between agents here | That is `collaboration-harness` rung 3, and it uses our gates as the grader deliberately, because variance between runs is a different question from task success. Two plans, two metrics, no overlap. |
| Open pull requests against the corpus repositories | Not yet, and the order matters: fork and measure first, contribute when the thing being contributed has evidence behind it. Nine of twenty have no licence, which constrains this separately. |

## Evidence status

| Claim | Status |
|---|---|
| The harness survives contact with unseen repositories | **Established**, weakly: 20/20 scaffolded with no crash. Says nothing about effect |
| Four gates judge a stranger's existing content on day one | **Established**: 19/20, 13/20, 11/20, 11/20, first corpus run |
| The corpus carries usable outside graders | **Partial**: 16/20 have test files, 10/20 declare a command. Whether they *run green* is A1 and is unknown |
| A non-Claude backend can drive the harness | **Established** end to end on a runner, one model, one trivial task |
| Scaffolding does not break a working repository | **Untested.** Phase A |
| Scaffolding changes task outcomes | **Untested**, and it is the whole plan |
