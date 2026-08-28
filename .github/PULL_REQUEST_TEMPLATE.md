## What this changes

## Why

<!-- Link the issue, or say what went wrong in practice. A change whose reason
     lives only in this description becomes unexplainable once the PR scrolls
     out of view. -->

## How it was verified

<!-- The command, and what its output was. "Tests pass" is not verification:
     which case, and would it have failed before this change? -->

- [ ] `python3 shared/scripts/guards/selftest.py` passes
- [ ] `python3 shared/scripts/gates/selftest.py --verbose` passes
- [ ] If a check was added or changed: it has both a blocking and a
      non-blocking case, and I have watched it fail under a silent injection
- [ ] Any measurement quoted in a comment or doc says what produced it
