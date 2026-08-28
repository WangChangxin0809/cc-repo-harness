# Contributing

Thanks for looking. This file answers what you cannot find out by reading the
code — the code will tell you how things work, not what this project wants.

## What this is looking for right now

- **Welcome**: new guards and gates, language support in `shared/scripts/index/`,
  and corrections to anything here that turns out to be wrong in practice. The
  last one is the most valuable: much of this plugin is an argument about what
  fails silently, and a counterexample is worth more than an addition.
- **Ask first**: a sixth or seventh skill. The plugin caps its own always-on
  cost and enforces that cap on the repositories it sets up; adding a skill
  spends that budget on everyone, forever. Bring the trigger it would answer
  and why an existing skill cannot hold it.
- **Will be declined**: anything that only works while this plugin is installed.
  The acceptance test is that you can install it, run the bootstrap, delete the
  plugin, and the repository still teaches a fresh agent how to work in it.
  Machinery that lives here rather than in the target repository fails that.

## Before you open a pull request

```bash
python3 shared/scripts/guards/selftest.py
python3 shared/scripts/gates/selftest.py --verbose
```

Both must pass. They build throwaway repositories, plant a defect each check
must catch, and assert the check turns red **and names the defect** — then that
it turns green without it.

If you added a check, it needs a case in the matching `selftest.py`, with at
least one input it must block and one it must let through. The second is not
optional: a check with only blocking cases can quietly become a wall that
matches everything, and people then find a phrasing that slips past it.

Then prove it the hard way, once, by hand:

```bash
cp <your check> /tmp/x.bak
# make it silently return "clean" — not raise. A crash is the easy case.
python3 shared/scripts/gates/selftest.py     # must name exactly your case
cp /tmp/x.bak <your check>
```

Restore with `cp`, never `git checkout --` — that discards unrelated uncommitted
work in the same file and does not restore untracked files at all.

## What review looks for

- **Failure output that carries the remedy.** A check's stderr is the only prose
  in a repository guaranteed to be read at the moment it is relevant, by someone
  who has already made the mistake. It should say what was found, what to do,
  and which document explains why.
- **Silence on success.** Output on every green run trains everyone to skim, and
  then the one run that printed something goes unread.
- **Exit 2 where the check could not judge.** Missing tool, unparseable config,
  no baseline — never reported as a pass. Exit 2 is also a shared observable, so
  the selftest should assert the reason, not only the code.
- **Measurements with the commit they were taken on.** A number in a comment
  that nobody can re-measure is a number that has already expired. If you quote
  a timing, say what produced it.

## Filing an issue

Include the repository shape the problem appeared in — roughly how many tracked
files, which languages — and the exact output. For an index problem, attach
`docs/generated/index-report.md`: it records what the graph could not see, which
is usually where the answer is.

## Security

Not here, and not in the issue tracker: see [SECURITY.md](SECURITY.md).

## A note on prose

Much of this repository is documentation that argues for something. If you
change an argument, change the thing it justifies too — a rule whose reasoning
has been edited out survives as folklore, and folklore gets routed around.
