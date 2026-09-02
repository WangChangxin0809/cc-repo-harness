# A workflow skeleton, and what each line is there for

Governs: .github/workflows/

One job that calls the repository's own entry point. Everything specific to the
repository lives in `ci.sh`, not here — see the skill for why judgement written
into YAML cannot be run before pushing, cannot be tested, and dies with the
provider.

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

defaults:
  run:
    shell: bash

jobs:
  harness:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<40-char sha>   # vN
        with:
          persist-credentials: false
      - uses: actions/setup-python@<40-char sha>   # vN
        with:
          python-version: "3.13"

      - name: the checks can still turn red
        run: |
          python3 scripts/guards/selftest.py
          python3 scripts/gates/selftest.py

      - name: the repository is sound
        run: ./ci.sh
```

## Why the selftests run first, and separately

A suite whose checks have quietly lost the ability to fail reports a clean build
forever, and that report is indistinguishable from the report on a repository
that is actually clean. Running them first means a broken *instrument* and a
broken *repository* are two different red squares, and you can tell which you
have without reading a log.

## Getting a SHA

```bash
gh api repos/actions/checkout/git/ref/tags/v5 --jq .object.sha
```

Keep the tag in a trailing comment. The comment is for humans deciding whether
an update is worth taking; the SHA is what actually runs.

## Splitting into more than one job

Split on *what a red square should mean*, not on speed. "The scaffolder broke"
and "a gate broke" deserve two squares because they send you to different files.
Three jobs that all mean "something in the repository is wrong" deserve one.

`fail-fast: false` on any matrix. The whole point of running two Python versions
is learning that one of them fails, and the default cancels the other the moment
the first goes red.

## What does not belong here

- A second copy of the check roster. Call `ci.sh`.
- `continue-on-error` or `|| true`. Exit 2 means *could not judge* and must fail
  the step; a manufactured green is worse than a red.
- Secrets in a workflow that runs on `pull_request` from forks. That trigger
  gives untrusted code a run; `pull_request_target` gives it a token as well.
- `paths:` filters. The change most likely to break a link check or a routing
  table is a docs-only change.
