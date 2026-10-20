# Independent project reviews

| Review | Baseline | Purpose |
|---|---|---|
| [Closing value and architecture assessment](2026-10-20-final-value-review.md) | Final implemented cycle and prior independent reviews | One-workflow pilot, negative policy evidence, no rewrite justification, unproven operational value |
| [Final eight-hour evidence review](../experiments/run-analysis/final/review.md) | Exact completed CPU/GPU capture hashes | Actual duration, sampled coverage, retained failure, source identities and resource limits |
| [Evidence and tooling review](2026-10-19-evidence-tooling-review.md) | GPU `afa84a17` evidence plus hashed tooling candidate | Media claims, eight-hour elapsed versus observed coverage, final-summary gaps and targeted contract refactor |
| [Direct incident and spatial review](2026-10-19-direct-incident-spatial-review.md) | `64c8bfa` plus identified candidate | Fewer forecast prerequisites, frozen source observations, geometry versus service meaning, complete release boundaries |
| [Workflow and spatial review](2026-10-19-workflow-and-spatial-review.md) | Identified workflow/circulation candidate | Dispatch acknowledgement versus repair, stale readback, practical design gaps |
| [Evidence and policy review](2026-10-19-evidence-and-policy-review.md) | Identified evidence/policy candidate | Numerical reproduction, browser JSON normalization and adverse policy results |
| [Weather preview review](2026-10-19-weather-preview-review.md) | Identified external weather candidate | Real provider provenance, forecast timing and separation from synthetic operations |
| [Planner review](2026-10-19-planner-review.md) | Identified initial planning candidate | Conservation, feasibility, heat constraints and negative controls |
| [FOX value baseline](2026-10-19-value-baseline.md) | Initial 19 October scope | Operational decisions, measurable value and implementation boundaries |
| [Revision 2 maintainability review](2026-10-15-revision2-maintainability-review.md) | `2e2b16b`, `2c763d2`, `19cee1e` | Independent CPU rerun, actual GPU evidence review, source/replay and durable action boundaries |
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
149 CPU/API checks including the deterministic regression. GPU/browser scope was pending at that checkpoint. The revision 2 review above
records subsequent real native/browser evidence separately.

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
