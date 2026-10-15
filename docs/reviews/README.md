# Independent project reviews

| Review | Baseline | Purpose |
|---|---|---|
| [Digital-twin benchmark](2026-10-15-digital-twin-benchmark.md) | `930acd3` | Compare capability and evidence against recent public digital-twin implementations |
| [Architecture review](2026-10-15-architecture-review.md) | `930acd3` plus identified WIP | Assess complexity, uncontrolled coupling, targeted refactoring and the value of rebuilding |

## Recurring milestone review

Request another independent review after a meaningful integrated milestone,
approximately every 60–90 minutes during sustained development, or sooner after
changing state ownership, an API contract, scene identity or deployment behavior.
A review is triggered by completed work, not the clock alone.

Each follow-up must identify its exact commit/worktree, inspect the changes and
verification evidence, check the previous ranked findings, and record:

- What became simpler, what became more coupled and which state owns each value.
- Whether to keep, refactor, replace a component, or rebuild—and the measured reason.
- Regressions or unverified claims, with concrete file/API references.
- A small ranked next-step list and acceptance evidence.

Keep past reviews as dated snapshots. Do not rewrite an old review to make later
work appear to have passed it. Link review conclusions and verified milestones
from the [progress page](../progress.md) and [development log](../development-log.md).
Completed code/assets and their checks should be committed in coherent increments;
unpublished commits must be distinguished from the public repository state.
