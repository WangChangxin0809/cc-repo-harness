# A3 · The improvement loop

Scaffold twenty repositories nobody here wrote, let an agent close what the
checks report, and re-measure — with the repository's own test suite as the
score and the gates as nothing but the work order.

`eval/improve.py` is the loop. `.github/workflows/corpus-improve.yml` is where it
runs, dispatched by hand, budgeted at 350 minutes because a job may run six
hours and the work is twenty repositories deep rather than wide.

## Consulted

- **A1's own result**, which is what moved this to a runner. Two repositories
  green on the machine it was written on, and fourteen `could-not-run` that read
  `cargo is not on PATH`, `bun: not found`, node 20 against a repository wanting
  22, gcc 14 against a Makefile wanting 15. Eleven languages need eleven
  toolchains, and a laptop is a preference rather than an environment.
- **The corpus survey**: moment 1 filled 20/20, moments 2, 3 and 5 empty 20/20.
  Every repository already has the file this plugin discusses most and that
  `scaffold.py` will never write. That is what the agent is walking into.
- **`nim-agent.yml`**, for the provider → proxy → agent chain, already proven end
  to end on a runner. This workflow reuses its shape and adds toolchains, a
  corpus and a loop.
- **Research**: none. The open question here is what an agent does with a
  scaffolded stranger's repository, and nobody has published that because the
  scaffold is ours.

## The decisions already made, and why

**The gates generate the task and do not score it.** `scaffold.py` writes the
files `check_docs_index.py` looks for, so scoring with our own gates would be a
restatement wearing a number. What they are good for is the opposite: their
output is a list of specific, located complaints, which is exactly the shape a
work order needs. Having produced it they have no further say. The score is the
repository's own suite, written by somebody with no stake in this plugin.

**Harm is reported before anything else.** A repository whose tests were green
and are now red has been damaged, and no number of satisfied gates makes that a
good trade. It is the one result that would stop the plugin being offered to
anyone at all, so it is measured last and printed first.

**Two cheats are verified rather than trusted.** The gates run from our copy at
every stage, so an agent that deletes one cannot stop it running — only stop it
being in the repository. And every edit under `scripts/gates/`, `scripts/guards/`
or `ci.sh` is reported separately, because satisfying a check by removing it is
the outcome that looks most like success from a distance.

**Improvement, not conformity.** An earlier attempt softened
`check_community_health` because 17/20 lacked a requirements section and 18/20
lacked a pointer to CONTRIBUTING, reasoning that a check firing on nine tenths
of its subjects describes a house style. That reasoning does not survive
contact: a majority lacking something can simply mean the majority is deficient,
and a README with no statement of what it needs to run is worse for its reader
whether one repository does that or seventeen. The gate keeps its judgement. The
gap gets closed rather than excused, and closing it is what the agent is for.

## What has to be decided when the first run lands

**What counts as an improvement.** Gates-red going down is the obvious number
and it is the one the gates are least entitled to. A run where every gate goes
green and the repository's own suite breaks is a worse outcome than one where
nothing moves. The reporting order encodes that; the reading of it still has to.

**What to do about a diff nobody would accept.** The artefact keeps the working
copies precisely because a summary of a diff is somebody's opinion of it. If the
agent's changes are the kind a maintainer would reject on sight, the gates going
green means the gates are satisfiable without improving anything, and that is a
finding about the gates.

**Whether a weak model is the right instrument.** nemotron-3-super was chosen for
being fast and free, not for being good, and most people running Claude Code as
a harness are not running Claude behind it. If it cannot complete the task at
all, that is a fact about the model and not about the harness — and telling
those apart needs a second backend, which is phase D.

## What would make this step fail

Not "the agent did badly" — that is a result. This step fails if the run cannot
distinguish *the harness did nothing* from *the model could not do the task*,
which is why the chain is probed link by link before the loop starts and why
each repository's agent exit code and transcript tail are recorded next to its
gate counts.
