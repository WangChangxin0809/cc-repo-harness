# CI, benchmarks and automation

**Status:** implementation complete; final hosted verification in progress. **Baseline:** `eb19d49d34975cb6dce849f2d8798ad09ae2a2d8`.

This work strengthens the existing fast PR / broad postmerge design. It adds
reproducible memory benchmarks, trustworthy native plugin-eval evidence, and
release verification tied to the exact commit being published.

| Read | Purpose |
|---|---|
| [Architecture](architecture.zh-CN.md) | Decisions, boundaries and workflow layers |
| [Implementation plan](implementation.md) | Independently testable work and acceptance |
| [Research](research.md) | Upstream sources and actual repository findings |
| [Validation](validation.md) | Commands, witnessed defects and observed results |

The repository's own tooling lives outside `shared/`. No new model-backed job
runs automatically or receives secrets on a pull request. Timing reports are
observations, while deterministic correctness and evidence completeness gate.
