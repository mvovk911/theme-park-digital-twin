# Connecting spatial design to operational planning: decision and proposed contract

Research/design review, 19 October 2026. Local HEAD at inspection: `ea556a74079555244f9109c20d8d050c3f9e9b7a`; the inspected working-tree planner SHA-256 is `98a94b9f5cd38fa1b43e844b07d36092caa65166ad5b9437dc12a98fd6c06df1`. This document proposes future contracts; it adds no simulator, API, scene or operational behavior.

**Decision: defer numerical spatial/planning coupling beyond this eight-hour cycle.** Finish the already useful dining-design comparison and retain the planner's explicit spatial limitations. The smallest defensible bridge is a separately labelled spatial-evidence check with an explicit origin and receiving boundary. A successful route query cannot certify the existing forecast or authorize guest guidance. A next numerical prototype needs a conserved in-transit cohort ledger, measured origins, and real queue-admission mappings before it can estimate service consequences.

The operator question to resolve first is: **“At which observable point can staff or signs influence these guests, and should they be offered destination B rather than A over the next 30–60 minutes?”** “Which queue has the longest wait?” does not answer where those guests are, what they intend to do, or whether B can admit them. For the current design panel, retain the narrower question: “Does this new dining connection create modeled access from the entrance, and what remains unresolved?”

## What the current code actually means

`backend/planning/engine.py::_run()` initializes queue stocks approximately as posted/modelled queue minutes multiplied by service rate. It derives ordinary incoming demand as 90% of the current service rate, then applies scenario assumptions. These are synthetic estimates, not observed counts or an origin–destination demand matrix.

The optional `reroute_guests` effect begins after a five-minute action delay. Each subsequent five-minute interval selects the most backlogged **other destination queue** by `queue / rate`, then diverts a compliance fraction of that destination's **incoming flow** to the named shorter-wait target. It does not move people already in that queue. The selected source queue is therefore **not a spatial origin**. Mapping it to `coaster_gate`, `food_entrance`, or an asset centroid would falsely claim that incoming people are standing there.

There is also a separate closure rule: existing coaster queue stock is redistributed immediately, 60% to the wheel and 40% to food; later coaster arrivals receive the same split. Adding a route check only to the optional reroute action would leave this instant movement in baseline branches. A coupled model must replace both transport assumptions consistently, preserve the previous model for reproducibility, and compare policies inside the same new model.

The spatial API has different, deliberately limited semantics:

- A query uses a named authored origin, not a measured cohort location. The current UI's default park entrance is an explicit design question, not evidence that all guests start there.
- `RIDE_WHEEL` ends at its public approach before queue rails. It does not reach a verified queue-admission or boarding interface.
- Baseline food and coaster gate connections are absent. The dining variant reaches a plaza landing, not restaurant ordering/service queues.
- The baseline graph is partial. “No route in this graph” means unsupported by this authored model, not proof that a real park has no route.
- Widths and step-free labels are authored assumptions. The dining footprint audit proves nonintersection with inspected synthetic bounds; it supplies neither pedestrian capacity nor field-certified accessibility.

The independent [policy review](../reviews/2026-10-19-evidence-and-policy-review.md) found that extra interventions often cost more without additional service or waiting benefit in its chosen grid. A walking-delay feature should not become another assumed source of improvement. The [spatial review](../reviews/2026-10-19-direct-incident-spatial-review.md) appropriately separates geometric access from operational guidance and rejects percentage time savings against an unreachable baseline.

## What primary sources support

SUMO distinguishes pedestrian network connectivity from movement behavior. Its documentation describes non-interacting, striping and JuPedSim modes; explicit demand can come from origin–destination inputs or counts. The JuPedSim coupling documentation currently warns that only the largest connected component is retained when multiple components exist. For this project, importing the disconnected food plaza without checking the generated network could silently discard the area being evaluated. Exported geometry and demand must therefore be audited, not trusted because a model starts. [SUMO pedestrian documentation](https://sumo.dlr.de/docs/Simulation/Pedestrians.html).

JuPedSim separates journeys, stages and transitions. Queue stages hold agents at defined waiting positions and require a signal to release a number of agents; reaching a waypoint alone is different from completing a queue stage. This supports an explicit service-model handoff rather than treating “reached the wheel approach” as “served by the wheel.” Its geometry documentation requires a connected walkable polygon and represents obstacles as exclusions. [JuPedSim routing](https://www.jupedsim.org/stable/concepts/routing.html), [geometry](https://www.jupedsim.org/stable/concepts/geometry.html).

Disney's ParkSim uses activity-driven visitor movement calibrated with theme-park GPS tracks. Its reported validation concerns wireless-network metrics, so it does not validate our staffing or queue forecasts. Disney's later Trending Paths work compares movement patterns against references; visual similarity alone is not the evaluation. [ParkSim](https://la.disneyresearch.com/publication/a-simple-framework-to-simulate-the-mobility-and-activity-of-theme-park-visitors/), [Trending Paths](https://studios.disneyresearch.com/2016/02/26/trending-paths-a-metric-for-evaluating-crowd-simulation/).

Recent primary project research is particularly relevant. Mohcine Chraibi's September 2026 calibration notes show that fitting bottleneck observables can leave materially different parameter sets, and that transfer to different gate/entrance experiments can fail. Held-out widths within one experiment are weaker evidence than a separate experimental setting. We should use those results as a reason to validate our intended decision and conditions, not borrow their parameters or success tolerances. [Calibration study](https://pedestriandynamics.org/notes/dakota-calibration/), [transfer validation](https://pedestriandynamics.org/notes/dakota-validation/).

These sources establish available modeling mechanisms and evaluation lessons. The incremental architecture below is our engineering proposal, not a claim that those projects validated Aster Park.

## Three increments, in order of evidence needed

| Option | User question and output | Required data and limits | Recommendation |
|---|---|---|---|
| 1. Spatial evidence check | “Can this explicitly named origin reach the intended receiving boundary in this design?” Return route identity, scope and blockers beside an unchanged plan. | Origin selected by operator or tied to an observation; endpoint mapping; graph/layer identity; closure assumptions. A public approach can pass a design check while remaining insufficient for a service forecast. | Smallest defensible bridge. Current spatial panel already supplies most of the value. Do not add an automatic forecast-validity badge or change forecast totals this cycle. |
| 2. Cohort travel and queue admission | “Does the intervention still help after travel, delay, refusal and receiving-service constraints?” Return travel/queue/holding burden, service visits and unresolved demand. | Measured release counts at one decision point, route travel distributions, destination admission mappings, independent service observations, compliance evidence, closure semantics. | Preferred next numerical pilot. Implement as a separately versioned pure model with event-time transport and five-minute reports, after data/mapping acceptance. |
| 3. Local pedestrian–service simulation | “Does a specific junction, queue inlet or dining layout create interaction/spillback that the cohort model misses?” Return trajectories and measured local flow/density/travel diagnostics coupled to service admissions. | Surveyed walkable geometry and obstacles, measured behavior/route choice, arrivals and queue release events, appropriate calibration and external validation. JuPedSim for a local area; SUMO where multimodal/network interaction is needed. | Defer. Start with one local bottleneck, not an entire park. No reason to install another simulator merely to animate a result already answered by the graph. |

Option 1 should return statuses such as `context_missing`, `unsupported_in_authored_graph`, `approach_only`, or `route_supported_in_authored_graph`. None means `forecast_validated`, `safe`, or `execute`. An unknown origin or incomplete admission mapping should remain explicit rather than selecting a convenient default.

## Proposed input/output and provenance for option 2

This is a **future model contract**, not a new endpoint request supported today:

```json
{
  "schema": "spatial_queue_experiment/v1",
  "model_id": "cohort_transport_queue/v1",
  "canonical_snapshot_revision": "<frozen accepted observation revision>",
  "spatial_identity": {
    "graph_sha256": "<exact selected graph>",
    "baseline_scene_sha256": "<exact USDC>",
    "variant_layer_sha256": "<exact layer or null>",
    "entrance_mapping_sha256": "<reviewed queue admission map>"
  },
  "demand_boundary": "observed_decision_point_releases",
  "origin_node": "<reviewed observation location>",
  "origin_observation_id": "<count/source/time provenance>",
  "destination_queue_ids": ["<A>", "<B>"],
  "cohort_release_series_sha256": "<same source visits in every policy>",
  "service_schedule_sha256": "<independent capacity/admission evidence>",
  "closure_schedule_sha256": "<event times and affected scope>",
  "travel_distribution_sha256": "<measured or explicitly synthetic distribution>",
  "choice_model_sha256": "<eligibility/compliance/refusal assumptions>",
  "time_unit": "seconds",
  "report_interval_seconds": 300,
  "execution_authority": "none"
}
```

Also retain normalized inputs, observation/ingestion times, quality and missingness, forecast issue time/horizon, origin and destination coordinate transforms, model/source/package versions, calibration-data manifest, split-day IDs, and random seed manifest when sampling. Bind saved output to those exact inputs. Static design identity and live observation revision are different clocks and must remain distinct.

The receiving map must explicitly connect a graph endpoint to a service queue's **admission boundary**, with any remaining approach/queue-entry travel and eligibility rules. A semantic asset ID alone is insufficient. The existing wheel approach and food plaza landing do not satisfy that requirement. An absent connection is an unsupported case; it is not zero extra travel.

Outputs should contain per-policy trajectories for queued, in-transit, holding and completed service visits; admitted/rejected demand; walking, waiting and holding minutes; remaining demand at the horizon; service/labor costs already represented; per-step and final conservation residuals; feasibility/unsupported reasons; and sensitivity results. Report physical elapsed time from release to service separately from queue time. Do not assign a monetary value or combine objectives without an operator-provided tradeoff.

### Conservation and time semantics

Use **service visits**, not “unique guests,” unless there is a separately validated whole-park person model. A visitor may make several service visits. For a one-visit pilot, maintain:

`initial outstanding visits + cumulative new released visits = queued + in transit + held/unassigned + completed service visits + explicit abandoned/exited visits`.

A transport departure removes visits from exactly one source state and adds the same amount to an in-transit cohort. Arrival transfers that amount into a verified receiving boundary; it does not increment external demand again. Refusal retains the original intended flow. Unsupported/unreachable demand stays held or leaves under an explicit measured abandonment rule; it is never dropped to improve the score. Record initial queue and in-transit stocks separately.

Keep an event clock in seconds. Five-minute output buckets can remain for UI continuity, but a modeled 34-second walk must not be silently rounded to zero or five minutes. Between events, integrate queue/holding/service and transit duration. At time `t`, first settle the preceding half-open interval, then apply closures effective at `t`, then process arriving cohorts, releases and route choices for the next interval. A cohort finishing travel at a closed destination is held, not served or teleported elsewhere. Publish tie-breaking rules for all simultaneous events.

The intervention's existing five-minute activation delay and actual travel delay are different quantities. Count both only where their meanings require it. Avoid adding a full origin-to-destination walk to arrivals already measured at a queue-admission gate: either forecast releases upstream and transport them, or use downstream arrivals as an exogenous boundary, never both for the same visits.

All policies receive the same external release series and initial stocks. Recalculate destination arrivals from those releases and each policy's choice/travel model. Preserve in-transit and held visits at the horizon. Otherwise a long walk can falsely “improve” queues by postponing demand beyond the report window. Report `walking_guest_minutes`, `queue_guest_minutes`, `holding_guest_minutes` and terminal unresolved visits separately; do not optimize queue minutes alone.

### Closure semantics

- **Path edge closed before departure:** find a supported alternate route or retain demand at the known decision point. Do not traverse excluded edges. A known scheduled closure must be considered at the predicted edge-entry time, not just at forecast start.
- **Closure affecting an in-flight path:** the smallest pilot should mark that branch unsupported and retain its accounting state for diagnosis. It must not invent a safe holding point, rewind guests to the origin, or pretend the closure had no effect. Modeling occupancy and clearance on a closing edge requires a later spatial state model and an operator-agreed rule.
- **Queue admission closed:** no new admission after its effective time; already waiting visits remain accounted for. Releasing them to another service needs an explicit observed origin, eligibility and transport transition.
- **Service closed:** capacity is zero during the closed interval. Closing service does not automatically empty its queue or prove that all guests choose another attraction.
- **Reopening:** requires an input event with provenance. A maintenance acknowledgement or elapsed simulated repair time cannot create a real reopening event.

These are proposed experiment rules, not real crowd-control procedures. Any actual guidance remains outside this model's authority.

## Negative controls and evaluation gates

| Control | Required result |
|---|---|
| Unknown origin; named destination only | Refuse coupled forecast or report unsupported; never use a queue centroid as an invented origin. |
| Route ends at public approach, queue admission unmapped | Geometric result may remain available; no service-arrival claim. |
| Zero compliance | Policy matches the same model's no-intervention arrivals, costs and outcomes except an explicitly modeled communication cost. |
| Same inputs, changed scenario label | Transport follows inputs, not the label. |
| Zero distance on a fully mapped synthetic fixture | Recover the declared no-travel cohort model, not necessarily the old five-minute approximation. |
| Slower walking or long detour | Transit burden rises; unresolved end-of-horizon demand remains visible. A smaller queue alone is not success. |
| Same visits supplied at upstream release and downstream admission | Reject incompatible demand boundaries or explicitly reconcile them; never count the same visits twice. |
| Horizon ends before a traveling cohort arrives | Retain all visits in transit and in terminal unresolved demand; do not report them as served or absent. |
| Closed connector; wrong graph/layer hash | Unreachable or identity failure; no fallback across grass. |
| Baseline unreachable, design reachable | Report changed feasibility and absolute design distance. No percentage or finite “time saved” against the absent baseline route. |
| Increased path width with all observed inputs fixed | No capacity or throughput bonus is introduced by width alone. |
| Destination service unavailable or stock depleted | Show held/queued demand and reduced service, not a guaranteed benefit from reaching it. |
| Intervention late, unnecessary or harmful | Do nothing can win. Include refusal, additional walking, donor/service constraints and costs when supported. |
| Closure while a cohort is in transit | Explicit unsupported branch or a separately validated occupancy policy; never silently lose or relocate visits. |
| Model fit versus withheld days | Report both; no fitting to test-day outcomes or treating simulator agreement as field validation. |

Compare no intervention, the published simple rule, and the proposed policy using common released demand and paired seeds where stochastic. Publish every tested case, including failures. The next model must earn its complexity by changing a real decision more reliably than a route check plus a simple queue rule; a more detailed animation is not that evidence.

## Minimal anonymous export for one real-park pilot

Limit the pilot to **one observed decision point, two candidate destinations, and one 30–60 minute peak window**. Ask for a provisional 12 operating days: six fit days, two development days, and four untouched holdout days selected before fitting, with ordinary/peak and weekday/weekend coverage where those conditions are in scope. This is a practical starting proposal, not a statistically sufficient sample size. Extend collection if relevant conditions or intervention examples are missing; narrower evidence supports narrower claims.

| Export | Minimal fields and granularity | Why it is necessary |
|---|---|---|
| `manifest.json` | Local-coordinate system, units, timezone/relative-day convention, clock synchronization/error, measurement method, missingness rules, file hashes, preassigned day split | Prevent unit/time drift and test leakage. |
| `layout.geojson` + `entrances.csv` | Reviewed decision-point footprint, usable links/obstacles, queue-admission boundaries, existing restrictions and validity dates | Connect observed counts to actual origins and receiving services. Include survey uncertainty; no capacity inferred from width. |
| `decision_counts.csv` | Anonymous day ID, interval start/end, origin zone, eligible visit count, intended A/B/unknown counts when measured, completeness flag; start with one-minute bins | Establish demand upstream of routing. Unknown intent remains unknown, not inferred from queue size. |
| `queue_service.csv` | Day/time, queue ID, counted queue stock, admissions, completed service visits, operational status, open service positions, stockout intervals, measurement quality | Estimate actual arrivals and service independently. Posted wait is a separate field, not a substitute for queue counts or service completions. |
| `travel_histograms.csv` | Origin/destination boundary pair, observation window, duration-bin edges/counts, sample count, measurement method and uncertainty | Estimate travel-time distributions without exporting person tracks. Five-second duration bins can preserve short walks even when count windows are one minute. |
| `closures_and_events.csv` | Effective start/end, affected edge/admission/service, reason category, known-at time, planned/unplanned, show-release times | Keep forecast knowledge separate from future events revealed only afterward. |
| `guidance_trials.csv` if compliance is to be estimated | Anonymous time window, offered destination/message category, exposure count, eligible count, accepted/refused/unknown counts, observed downstream totals and assignment method | Estimate routing response. Without prior intervention evidence, compliance remains an uncertainty assumption and causal guidance benefit cannot be validated. |

Export aggregate counts and duration histograms; no names, ticket IDs, face/video data, device IDs, or persistent visitor trajectories are required for this first pilot. The park can compute aggregates locally. Small or incomplete cells should be flagged or combined, with the transformation documented; do not fill suppressed counts with zero. This design reduces person-level data needs but is not a claim that every possible aggregate export is automatically anonymous.

Fit demand/service/travel components separately where observations support them. Freeze preprocessing, parameter choices, decision thresholds and software before holdout evaluation. Use whole days as splits, not randomly shuffled five-minute rows from the same peak. Count-window timing assumptions must be disclosed and tested—uniform, front-loaded and back-loaded arrivals can differ on a short walk.

On holdout days, evaluate queue-stock error, cumulative admissions/completions, travel-duration distribution error, unresolved-visit accounting and the rank/tradeoff of policy choices where outcomes are observable. Compare with persistence and a simple calibrated queue model. Do not validate an unobserved counterfactual intervention using the same model that proposed it. Forecast accuracy can be evaluated observationally; causal guidance value needs an appropriately designed, separately authorized field trial or suitable intervention evidence. Let the operator set practical tolerances before fitting rather than importing a percentage from another experiment.

## Next decision after this cycle

Do not change the aggregate engine merely because the spatial API now exists. Complete the matched native images, explicit reachability/closure/accessibility UI and immutable release evidence. Present the origin/admission and data questions to the park operator. If those inputs are available and the decision matters, implement option 2 as an isolated, versioned pilot and commission an independent review before coupling it to any recommendation workflow. If they are unavailable, keep option 1 as a useful design check and retain the present forecast limitation visibly.
