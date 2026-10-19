# Independent review: saved evidence and policy stress

Review date: 19 October 2026. Scope: historical planning evidence implementation and the independently authored food-service policy stress experiment. Shared eight-hour service on port 18120 was not accessed or changed. This review used files, isolated application tests, and temporary databases.

**Verdict: saved comparisons close the previous reproducibility gap, and the policy experiment establishes an important negative result: the current waiting-first selection often purchases no additional benefit.** The experiment does not establish real park value or justify automatic intervention. No blocking persistence or arithmetic defect was found in this review.

## Evidence integrity and restart

Inspected implementation fingerprints:

| File | SHA256 |
|---|---|
| `backend/planning/evidence.py` | `b54f546fb0351b645ca46d805f87e562969c8ccca92eb9a9d34f5cb37a84d8c5` |
| `backend/planning/api.py` | `19f5d531d28287a350f36eae74e0b254cc2f567e0e5fb3e7666c45d8554ed7d1` |
| `operators/policy_stress.py` | `78812e12b12a9b37f73af4916c241ae26ad4f2e3aff43378b21adc56f47ae02a` |

The bundle now contains full frozen observations, normalized request, evaluation time, numerical result and exact model-source fingerprint. Saving verifies both the content digest and reproduction, uses a separate SQLite database, deduplicates identical bundles, and preserves existing records when explicit retention limits are reached. Historical verification uses the saved evaluation time, so expired live-cache entries do not prevent review. Source/model mismatch is explicit rather than silently rewriting old conclusions.

Independently ran all ten evidence tests: **10 passed**, one dependency deprecation warning, 1.82 seconds. They cover altered/rehashed results, unsupported identity, separate databases, retention, replay isolation, malformed input and reopen behavior. Additionally performed a genuine two-interpreter check: one Python process generated and saved a bundle; after it exited, a fresh process opened the database, retrieved the identical bundle and verified reproduction. The bundle identifier remained `61ffa28f18f2d7162fb64c00ca1210d574081b70ae6be2490fcb361ece08e119`. Temporary test data was discarded afterward.

This proves the tested local persistence/reproduction path, not a deployed GPU acceptance run. The SHA256 mechanism provides internal consistency, not authenticity: callers can construct synthetic observations and valid hashes. The API correctly returns `origin_authenticated:false` and `execution_authority:false`. A later execution service must obtain trusted current evidence and authorization independently. A saved plan must never become a bearer credential for commands.

### Browser serialization finding after the initial review

The original persistence checks above exercised Python JSON transport. They did **not** establish that a browser could round-trip a bundle. Actual browser testing subsequently found that JavaScript changes integral JSON numbers such as `1.0` to `1`, breaking the original byte-level hash and save workflow. This was a real integration blocker missed by the Python-only scope; the earlier no-blocker finding must be read with that limitation.

The builder's fix adds a bounded canonical numeric profile: integral floats normalize to integers, negative zero to zero, booleans remain booleans, nonfinite values and integers outside JavaScript's safe range are rejected. The code explicitly does not claim RFC 8785 compliance. Independently reran the revised evidence suite together with weather checks: **30 passed**, including an actual Node.js `JSON.parse`/`JSON.stringify` round-trip and numeric edge cases. That verifies the serialization regression locally; the frontend agent's new actual-browser save/reopen evidence remains separately required. Changes to this canonical profile should be versioned before supporting historical bundles created under multiple profiles.

The source fingerprint is computed at import time from model source files. Immutable release directories and process restarts remain necessary when changing code. Keep the exact historical source release available alongside exported experiments; a fingerprint alone cannot execute an older model. The bounded store has no automatic eviction, so the UI should expose storage-full errors and export instructions clearly.

## Independent policy accounting

Reviewed protocol `docs/experiments/food-service-policy-stress.md`, script, and `runtime/policy-stress/run01`. The run records gateway release `d3dca3d20612d3d09ed1acb680683a990cbd51ba`; it must not be represented as the newer evidence-persistence deployment. Protocol SHA256 recomputes correctly as `482a02cd9c50d69c6ddbc9358dc8f9b18597d8a8ebea3cfe3c780c0a8a1460a0`. Input selection is written before outcome evaluation in the script. Local file ordering alone is not external timestamp attestation, but the code follows its predeclaration protocol.

There are three initial-observation variants, four arrival profiles, three staff effects, three staff delays and three supply delays: **324 cases and 972 policy outcomes**. I independently recalculated every outcome from recorded initial values and the declared one-minute recurrence, without importing planner or evaluator code. Waiting, completed visits, backlog, remaining stock and labor matched exactly. Recorded visit and stock conservation residuals were below `9e-13`.

Timing is consistent with the declared model: delivery occurs at the beginning of its designated minute; staff alter capacity from their arrival minute; labor starts at minute zero and costs EUR56 for two people over one hour. Trapezoidal queue integration is a discrete approximation. It is not the observed waiting time of identified visitors.

## What the results actually say

The planner and simple rule select identical schedules in **216 of 324 cases**. All incremental differences occur in the **108 low-stock, already-covered-staff cases**, where the rule orders stock and the waiting-first planner selection orders stock plus two staff.

| Comparison | Across all 324 cases | Only 108 cases with different choices |
|---|---:|---:|
| Mean additional completed service visits | +1.701 | +5.102 |
| Mean accumulated waiting change | −28.883 guest-min | −86.648 guest-min |
| Mean additional labor cost | +EUR18.667 | +EUR56.000 |

In the 108 different-choice cases, extra staff improve accumulated waiting in 56 cases and completed visits in 42. They provide no waiting gain in 52 and no completed-visit gain in 66. The extra EUR56 applies to all 108. These are counts over a deliberately chosen grid, not probabilities of operational success.

Across the full grid, the planner-selected schedule is strictly dominated on waiting/service/labor by another tested schedule in **140 cases**, versus 88 for the simple rule. Doing nothing strictly dominates the planner in **92 cases**, versus 64 for the rule. Both non-baseline policies have 72 cases of an equally effective extra command, counted separately from strict dominance. These counts were independently recomputed from raw records.

The all-case averages are arithmetically correct but dilute the choice that actually differs. Show both columns and the subgroup counts. Do not present EUR18.67 as the cost of a specific intervention, or 1.70 service visits as its expected real yield. No valuation of service visits, queue burden or staffing opportunity cost has been supplied, so the experiment cannot conclude whether the tradeoff is worthwhile.

## Why zero service regret is not a strong validation result

The stress evaluator is independently implemented and withholds demand timing and non-nominal effects from selection. That is useful. Its structure nevertheless permits staff effects only at 0%, +5% or +15%; there is no donor depletion, setup loss, physical-space interference or qualification failure. More capacity cannot intrinsically make service worse. Replenishment has no purchase, waste or delivery-disruption cost. Under that candidate set, a waiting-first selector can achieve zero service regret while wasting labor.

The simple rule reacts to an observed staffing gap, but the evaluator does not impose a minimum-coverage constraint or directly reduce service for that gap. Therefore “do nothing dominates” is a result under the declared service/labor model, not permission to leave a real operational staffing requirement unmet. Conversely, a staff qualification is an assumed reserve capability, not verified roster evidence.

The early/canceled/late demand variants retain a substantial initial backlog—34 minutes times 290 visits/hour, about 164.3 service visits. A “canceled rush” does not mean an empty queue. Keep that distinction visible when illustrating why staff might still help after arrivals decline.

The three fixture variants, grid levels and equal weighting are design choices. Do not derive confidence intervals, ROI or forecast error claims from their frequency. Component-wise hindsight optima can belong to different schedules; the report correctly avoids summing their regrets into a fictional business score.

## Next useful slice

1. Add a review policy that explicitly asks whether the extra service/wait benefit merits the additional staff, with a user-supplied threshold or a clearly stated abstention when no threshold exists. Preserve the present waiting-first policy as a baseline.
2. Test operational feasibility separately from efficiency: qualified reserve, real minimum coverage, travel and whether moving people harms another service. Do not retrofit those assumptions into run01; publish a new protocol/run.
3. Add at least one adverse intervention mechanism grounded in the intended operation, such as setup disruption or a donor queue, rather than only nonnegative capacity effects. Publish inconclusive results.
4. In the UI, show a saved experiment's age/model identity, paired sensitivity harm, and the difference between a review option and a justified action. Capture actual save/reopen and adverse-case screens from the committed release.

The evidence feature now serves a clear operator job: revisiting exactly what was known and predicted. The stress experiment serves another: exposing unnecessary intervention. Those are concrete advances. They do not establish that more agents, more GPU hours or more detailed geometry would improve the decision.
