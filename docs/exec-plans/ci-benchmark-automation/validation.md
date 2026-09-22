# Validation record

Baseline main CI and postmerge both succeeded for `eb19d49` on GitHub. Local
Windows has known full-suite portability failures recorded in the shared-memory
delivery, so this work uses targeted local evidence plus fresh Linux GitHub CI.

## Release and terminal CI evidence

The following targeted commands passed on Python 3.12 / Windows:

```bash
python3 .github/scripts/selftest_ci_evidence.py
python3 .github/scripts/selftest_release_evidence.py
python3 .github/scripts/check_ci_results.py --self-test
python3 .github/scripts/release_tag.py --self-test --verbose
```

They cover 7 new fan-in tests, 12 release-evidence tests, 5 existing fan-in
selftests and 4 tagger tests. Missing/invalid selectors and unexpected failures
produced 13 failing subcases before the fix; duplicate run evidence was also
witnessed red before rejection was implemented.

The real read-only GitHub API check then passed for `eb19d49`, recognizing CI
run `35756286004` and postmerge run `35756286093`. This verifies API integration
without publishing a release. It does not claim the new workflow has published.

## Diagram and repository checks

Archify 2.16.0 showcase validation passed 9/9 checks with no warnings. Browser
viewport/theme checks passed; the exact exported SVG was inspected in light and
dark mode. The SVG SHA-256 at generation was
`78a08bbcb46b38b22e2456c1631b038e3d0fbb9dd5d7090a7426b953f6bc8f74`.
Receipts and images are reproducible using the documented renderer command.

The local workflow runner selftest classifies all current runnable steps, with
none unreadable. Template, file-size, machine-path and documented-command checks
passed after the new documentation was staged. The Windows docs-index gate
still reports its pre-existing `docs\\index.md` self-routing false positive;
its full Linux result is verified in GitHub CI.

## Offline memory benchmark

The final protocol's 21 default selftests passed. Defect witnesses cover wrong
or omitted records, leaked markers, empty positive delivery, nonempty negative
delivery, corrupted record content, byte budget, missing provenance, fabricated
timing/phase/median, missing samples and incompatible evidence fingerprints.

Two sequential real-Git measurements on Windows / Python 3.12 used the same
final harness with `--repeats 1`: clean main and the implementation worktree.
Both deliberately contained the **same unchanged memory runtime** at `eb19d49`.
Each measured 12/12 cases passing, three expected retrieval matches, no false
inclusions/exclusions, no forbidden-content leaks and no byte violations.
The comparator returned 0. This is a control comparison, not a speed improvement.

First-call timing was about 5.507s and 1.525s across the two runs of identical
code. That difference illustrates why shared-machine wall time is reported,
not enforced as a deterministic threshold. Hosted comparison runs use three
samples per case and keep cold/warm phases separate in the comparison table.
These are synthetic engineering cases, not measured gains in model task success.

## Independent review

Release/fan-in review approved the exact-SHA and permission flow with no P1/P2
findings; its 19 new tests also passed on Python 3.11. Benchmark integration
review found the nonempty-negative-output false pass described above; the final
scorer rejects it and corrupted accepted content. Native-eval review separately
checks the pinned binary's actual grader serialization and two-arm behavior.

## Native plugin evaluation evidence

All 16 native-eval/input/inventory tests passed locally, as did explicit suite
validation. Tests use synthetic records shaped from the pinned 2.1.273 binary;
no paid result or model benefit is claimed. Bad-data tests were witnessed red
before fixes, including missing arms, invalid aggregates, hard safety failures,
partial/aborted runs, changed input files and repeated trace paths.

Independent review found that native WITHOUT omits WITH-only Skill graders.
The fixture and validator now reflect this actual behavior. The reviewer
checked the extracted native filtering function with a no-model grading stub,
then verified a legal native-shaped WITHOUT report passes and copied traces
are unjudged. Final native-eval review approved both fixes.

The final local `scripts/check.py --job surface` ran 17 steps: all new checks
passed, with the one pre-existing Windows docs-index false positive described
above. `scripts/check.py --job hygiene` passed all three tools (actionlint,
zizmor and Ruff). `git diff --cached --check` passed; the generated Archify SVG
retains native CSS spacing under the same narrow per-file attribute as diagram 07.

The full local runner was also started before pushing; its unchanged Windows
gates reproduce the known docs-index baseline failures. Hosted Linux CI is the
authoritative full-suite verification for this change. Final hosted results
are recorded below when complete.
