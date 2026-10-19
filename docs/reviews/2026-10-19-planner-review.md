# Independent planner and Decision Lab checkpoint

Review date: 19 October 2026. Repository base: `20f0ca8519b1ef0424f30855691f65cab0dda154`; planning and UI additions were uncommitted and changing during this review. This report does not attribute them to that base commit or certify a GPU deployment. Initial inspected engine SHA256: `8fd99522d793afe0963e4cf139c1011e751590a7d6a58780fdce549cb9a08080`. Follow-up fixes are distinguished below.

**Verdict: the new planner is a useful decision-support experiment, with substantially better causal structure than the original scenario buttons. Its demonstrated value is explaining constrained synthetic tradeoffs, not optimizing a real park.** Keep the current modular design. Finish reproducible evidence, robustness communication and independent policy evaluation before broadening the scene or adding more agents.

## Evidence inspected

- Read `backend/planning/{engine,contracts,api}.py`, `frontend/planning.js`, planning tests and the FOX research document.
- Inspected actual HTTP operator report `runtime/operator-recon/planner03/summary.json`: 19:42:16–19:42:30 UTC; ten named checks passed, zero reported failures. These cover established workflows plus planning counterfactuals, degraded input and cleanup. The runtime directory is local evidence, not a permanent public artifact.
- Independently ran isolated pure-model probes, a 288-case routing grid, and the then-current planning suite: **32 passed**, one dependency deprecation warning, 0.69 seconds. The suite had grown from 30 after the heat-condition fix.
- Did not mutate the shared HTTP service, perform a new GPU run, or claim that a few seconds of tests constitute the requested eight-hour experiment.

The report confirms HTTP contracts and synthetic invariants. It is not a usability study, held-out real-day validation, or proof of return on investment.

## What now has practical value

The forecast starts from accepted canonical observations rather than silently comparing an unrelated simulator base. Each alternative uses the same initial state and demand factors. Queues conserve service visits; staff and delivery effects are delayed; a finite assumed reserve is checked; cost appears before staff benefit; maintenance dispatch does not magically restore the ride. Those distinctions make the question “what must be true for this response to help?” understandable.

The Decision Lab shows the baseline, alternatives, costs, unserved demand, constraints, timestamps, assumptions and model limitations. It is a separate consumer of a bounded planning API. The pure engine avoids storage and renderer coupling. This is a sensible extension rather than a reason to rewrite the application.

Three concrete value limitations remain visible instead of being hidden: extra care staff may cost money without improving an observed queue; stock replenishment and service capacity are separate constraints; a dispatched work order is not repaired equipment. Retain those cases in the demo and evaluation.

## P1 discovered and corrected during review: observed heat was ignored by the shedding guard

The original guard checked only `request.scenario == "heatwave"`. In an isolated actual-state probe, setting observed temperatures to 38°C and requesting a `normal` future with `shed_load` on `POWER_HUB` returned `feasible:true` and shortlisted shedding. The same issue applied when evaluating a power fault during already hot conditions. The decision depended on the future scenario label rather than existing conditions.

The builder changed the guard to consider relevant observed temperatures as well as the proposed heatwave, returning the hot asset evidence and threshold. The independently rerun 32-test suite includes normal and power-fault requests against hot observations. This closes the reproduced synthetic guard defect in local source. The illustrative threshold still does not establish a thermal or heat-safety model; fresh deployed acceptance must name the fixed revision.

## P1 evidence gap: a frozen response is not yet a saved experiment

The API returns a plan, but there is no durable branch repository or input bundle in this slice. `expected_state_revision` depends on the bounded in-memory revision cache; the response includes a revision identifier and output, not all original observations. The browser retains its result until reload, without durable retrieval. That is a valid **frozen comparison**, but not reproducibility after restart or model evolution.

Next acceptance: persist or export a content-addressed experiment containing full canonical input, quality/timestamps, exact request and candidates, output, model/configuration/source identity and hashes. Reopen it after live state changes and process restart without querying current observations. Historical reevaluation must be a separate operation from prospective freshness checks; an old experiment should remain inspectable without authorizing current actions. Numerical fixtures alone do not satisfy this operator job.

## P2: central-case shortlisting can conceal sensitivity regret

The API explicitly calls its low/central/high cases sensitivity assumptions, not confidence intervals. However, shortlisting uses only central summaries. A reviewer needs paired alternative-minus-baseline changes in each case, not merely independent min/max ranges.

Independent grid: four scenarios (`normal`, closure, show surge, food rush), six arrival multipliers (0.25, 0.5, 1, 1.5, 2, 3), three routing destinations, and four destination waits (0, 10, 30, 60 minutes): **288 synthetic cases**. Each used 60 minutes, ±50% demand sensitivity and 100% routing compliance. One shortlisted routing option reduced central accumulated waiting but increased waiting in a sensitivity case:

| Reproduction | Value |
|---|---|
| Starting state | Fresh in-memory canonical default snapshot; coaster wait changed to 10 minutes |
| Requested future | Normal, 60 minutes |
| Arrival multiplier / sensitivity / compliance | 0.25 / ±50% / 100% |
| Candidate | Route arrivals to `RIDE_COASTER` |
| Low demand waiting delta | 0.000 guest-min |
| Central waiting delta | −20.667 guest-min |
| High demand waiting delta | +24.334 guest-min |
| Original shortlist | Includes routing candidate |

This is not an error in conserving demand and not evidence that routing is bad in a real park. It demonstrates why central Pareto status is insufficient for a claim of robust benefit. Add paired sensitivity deltas and a visible adverse-case flag, for example “less waiting centrally; more waiting in high demand.” A robustness policy may require no material deterioration or leave the tradeoff explicitly for the operator. Do not silently drop the adverse run.

The 288-case grid is still inside the planner's own model family. It is not held-out model validation. The case was sent to the builder; any subsequent response should record its own verification.

Follow-up source check: engine SHA256 `7b52a48eb204f07845af9b7d713c922d3fa8ef53c976fa2255a639877ff0c0b7` now supplies paired per-case deltas and `robustness.adverse_sensitivity_case`, explicitly describing shortlisting as central-only. It also returns `preferred_policy:baseline` when no intervention demonstrates modeled benefit. Independently reran four focused heat, delayed-staff and sensitivity checks: all passed (29 other tests deselected). This addresses the API explanation gap locally; actual UI rendering and committed deployment still require their own evidence.

## P2: omitted costs can create a misleading winner

Under default observed loads, a modeled coaster closure can already lower aggregate power below the reduced feeder capacity. The scenario-specific simple rule nevertheless sheds HVAC/EV/food loads. It lowers modeled energy and therefore can appear nondominated even though comfort, charging service and disruption are unquantified. The UI's tradeoff warning is honest; a better simple operating rule would first check the capacity need and otherwise retain dispatch/inspection or do nothing.

Similarly, replenishment assumes available supply and omits procurement/waste cost; leak repair assumes success after 30 minutes without technician/permit/failure modeling. A nondominated result under these omissions is a **review option**, not net value. The wording currently reflects that distinction and should remain explicit.

## Next experiment: independently evaluate policy regret

Do not add an optimizer merely to beat a rule that was designed to be weak. Predeclare a narrow food-service decision, candidate set and primary metrics. Compare do nothing, an independently specified stock/coverage rule, and the selected plan under identical inputs.

Evaluate the selected response using a separate test harness with demand timing and service assumptions not identical to those used to choose it. Include reserve arrival at 10/20/30 minutes, staff capacity effects of 0/5/15%, delayed or unavailable replenishment, and demand falling before the intervention arrives. Publish the full grid, feasibility, service/wait/cost deltas, worst-case regret and no-benefit frequency. These parameter choices are stress tests, not probabilities or measured park behavior.

Avoid a fabricated composite business score. Keep service, waiting, labor and stock use separate unless the user supplies a meaningful valuation. A model that says “benefit depends on staff actually increasing throughput; otherwise the extra cost is wasted” provides more decision value than one that always celebrates an action.

## Maintainability and follow-up gates

No full refactor is justified. The three planning backend modules and isolated frontend consumer have clear responsibilities. The engine remains inspectable. Keep model changes versioned, prevent API/UI policy duplication, and put future experiment persistence outside the pure evaluator. If adding source-specific dependency validation, replace the current broad all-asset freshness gate deliberately; an unrelated stale source currently blocks every plan.

Before the next release, require:

1. Exact committed source identity for the fixed heat guard and subsequent changes.
2. Durable experiment evidence plus restart/reopen verification.
3. Paired sensitivity regret visible to the operator.
4. An independently specified policy stress grid with failed and inconclusive cases retained.
5. Actual GPU/browser evidence of the Decision Lab, including infeasible and insufficient-data states.
6. A separate fenced action proposal contract if execution is added; the original instant live-action effects must not be used as validation of this delayed forecast.

Against the initial rubric, input integrity, temporal model and synthetic comparisons advance toward level 2. Real-world outcome remains level 0. The project is becoming more useful because it can expose when action is unjustified, not because it has more rendered assets or a larger test count.
