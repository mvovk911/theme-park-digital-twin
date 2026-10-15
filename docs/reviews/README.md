# Independent project reviews

| Review | Baseline | Purpose |
|---|---|---|
| [Digital-twin benchmark](2026-10-15-digital-twin-benchmark.md) | `930acd3` | Compare capability and evidence against recent public digital-twin implementations |
| [Integrated checkpoint review](2026-10-15-integrated-checkpoint-review.md) | `29c4091` | Recheck complexity, prior fixes, frame/data consistency and immutable release behavior |
| [Architecture review](2026-10-15-architecture-review.md) | `930acd3` plus identified WIP | Assess complexity, uncontrolled coupling, targeted refactoring and the value of rebuilding |

## Completed follow-up

[Connector acceptance review](2026-10-15-connector-acceptance-review.md) inspected
committed `cf4d621` in isolation, verified 51 checks and found three actionable
projection/acceptance defects. Its report remains unchanged; subsequent fixes and
59-check evidence are recorded in the development log and later commits.

[Coherence closure audit](2026-10-15-coherence-fix-review.md) inspected `cb11424`,
confirmed the original fixes and reproduced a remaining status/pose race. That
specific race was subsequently fixed in `e477a12`; integrated `7b27281` passes
149 CPU/API checks including the deterministic regression. GPU/browser scope is
still pending and is not closed by these tests.

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
