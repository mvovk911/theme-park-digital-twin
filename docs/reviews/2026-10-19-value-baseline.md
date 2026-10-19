# Independent value baseline — FOX-inspired park operations

Review date: 19 October 2026. Source baseline: `db86ca1e102dcffe266b0507d0918f9082aeca7b`. Reviewer inspected the README, previous reviews, connector/action contracts, roadmap, domain definitions, pure scenario rules, `ParkSimulator.compare()` and action implementation. This is a source/research review, not a fresh GPU acceptance run. Assumed user: regional theme-park operations manager. No operator interviews or real park data have been supplied.

**Recommendation: build one defensible decision loop before expanding the scene.** The application is a credible synthetic operations demonstration with useful provenance and retry contracts. It does not establish that its recommendations improve park operations. The next increment should be a saved, time-forward staffing/queue experiment initialized from canonical accepted observations, with finite resources, independent baselines, adverse cases and a reviewable action proposal.

## FOX and external evidence

Manufacturing FOX describes a coordinating manager above specialized agents, factory APIs and an operational visualization. This maps to a park duty manager coordinating attractions, guest flow, maintenance, workforce and utilities. An agent can investigate an incident, ask simulation tools to compare options, explain evidence and submit a bounded workflow request. The announcement's projected business improvements are vendor/customer projections, not evidence for park ROI. [NVIDIA FOX announcement](https://blogs.nvidia.com/blog/factory-operations-fox-blueprint-ai-brain/).

As checked on this review date, the manufacturing announcement still links an access-notification form. This review did not verify a generally downloadable manufacturing FOX release. Call our build **FOX-inspired**, not installed FOX. [NVIDIA access page](https://www.nvidia.com/en-us/nvidia-factory-operations-blueprint-notify-me/).

A separate publicly documented **AI Factory Operations Agent** blueprint targets datacenter SRE: Kubernetes, Slurm, observability and GPU diagnostics. Its governed tools and evidence gathering are useful references, but it is not manufacturing FOX and supplies no park simulator. [NVIDIA developer example](https://build.nvidia.com/nvidia/operate-ai-factories-with-agents/examplecard).

Disney's ParkSim modeled visitor activities and movement using collected GPS traces for calibration. Its published validation targeted wireless-network-relevant metrics, not staffing or evacuation certification. Subsequent Disney crowd research compares trajectory patterns with reference data. We should similarly validate each model for the decision it supports. [ParkSim](https://la.disneyresearch.com/publication/a-simple-framework-to-simulate-the-mobility-and-activity-of-theme-park-visitors/), [Trending Paths](https://studios.disneyresearch.com/2016/02/26/trending-paths-a-metric-for-evaluating-crowd-simulation/).

The 2026 revision of MAPs evaluates agents making amusement-park business decisions and reports substantial weaknesses relative to expert humans. It supports testing against baselines and uncertainty; its game results cannot establish real park economics. [MAPs version 3](https://arxiv.org/abs/2511.15830v3).

Park operations are more specific than “send everyone to a shorter queue.” Universal's services distinguish virtual return times and attraction-specific accessibility; posted waits vary with demand, weather and downtime. Accessibility, entitlements and uncertainty belong in a future routing model. This prototype does not yet model them. [Official app](https://www.universalorlando.com/web/en/us/landing-page/mobile-app), [Accessibility](https://www.universalorlando.com/web/en/us/plan-your-visit/accessibility-information), [Express information](https://www.universalorlando.com/web/en/us/tickets-packages/express-passes).

## User jobs worth improving

| Job | Decision/output | Measured outcome against baseline | First usable boundary |
|---|---|---|---|
| Respond to ride closure | Choose available qualified team and alternative service | Correct-response time; guest-minutes waiting; served/unserved demand | Evidence bundle and proposed work order, no ride reopening |
| Manage show/lunch surge | Move finite crew, open service position, or do nothing | Waiting, throughput, travel/cost, donor coverage | 30–60 minute comparison with delayed effects |
| Triage utility anomaly | Inspect, investigate a meter conflict, or reduce declared flexible load | False alarms, diagnosis time, net metered energy/volume | Maintenance request; high flow alone is not a confirmed leak |
| Plan tomorrow | Choose staffing/show timing under uncertain attendance/weather | Held-out forecast error, service level, overtime | Offline planning |
| Review intervention | Check whether requested work occurred and outcome followed | Acknowledgement latency, duplicates, observed result, forecast error | Separate requested/accepted/completed/verified states |

ERP remains the stock/financial system of record; workforce owns qualified availability; CMMS owns work execution; ride control owns equipment state. The twin contributes shared identity, dependencies and context. An LLM can coordinate tools; numerical forecasts and command validation need separate contracts.

## Baseline gaps and architecture judgment

Preserve stable asset/prim identity, source freshness, canonical alert evidence, replay, synthetic idempotency and revisioned real OVRTX/browser evidence. Those are meaningful foundations. Historical acceptance does not prove a new deployment.

1. **Forecast inputs differ from observations.** Existing `compare()` evaluates a synthetic base at the same tick, clearing mitigations in its after-case. Connector injections do not enter it. A new branch must save exact canonical input, field quality, assumptions and model version.
2. **Interventions bake in benefit.** Rerouting multiplies several queues by 0.65; added staff multiplies queue by 0.7 and throughput by 1.15. These demonstrate UI effects, not policy value. New benefits must emerge from conserved demand, service capacity and time.
3. **Resources are not constrained.** Staff assignments draw from no finite roster; replenishment and repair are immediate. Actionable plans need availability, qualifications, donor coverage, travel/lead time, stock and execution failure.
4. **The average can reward failure.** Closed attractions disappear from the active-queue mean. Report served/unserved demand and guest-minutes waiting alongside each queue. Do not invent wait percentiles if an aggregate model cannot support them.
5. **Topology limits claims.** Asset dependencies do not establish walkable capacity, accessible routes or net utility balance. Scene work earns priority when it represents a modeled constraint or explains a decision.
6. **No full rewrite is justified.** Keep pure forecast evaluation, immutable branch storage, proposal validation and execution adapters separate. Do not put planning in the renderer loop or policy in both browser and backend.

## Rubric and evidence thresholds

Score 0 = absent, 1 = documented/demo only, 2 = reproducible synthetic evidence, 3 = independently validated field evidence. Scores measure evidence maturity, not economic value. Never average away failed integrity boundaries.

| Dimension | Baseline | Minimum evidence for this cycle |
|---|---|---|
| Named user decision | 1 | Explicit decision, alternatives, horizon and tradeoffs |
| Input integrity | 2 source projection; 0 forecast initialization | Saved canonical revision/hash, source times/quality and model/config version; abstain on missing critical inputs |
| Causal/time model | 1 same-tick heuristic | Time-forward queues, finite resources, delayed effects, equations and conservation checks |
| Policy comparison | 0 independent evaluation | Do-nothing and simple-rule baselines, identical initial state/random samples, retain all results |
| Robustness | 0 | Demand/capacity/delay uncertainty, infeasible and no-benefit cases, appropriate abstention |
| Action integrity | 2 synthetic retry contract | Proposal baseline/preconditions, stale-plan rejection, durable request ID, acknowledgement separate from verified outcome |
| Comprehension | 1 walkthrough, no task study | Actual UI explains choice, alternatives, costs, uncertainty and synthetic scope without raw JSON |
| Maintainability | 2 existing release evidence | Bounded modules, exact revision, reproducible API-only evaluation; GPU optional for numeric correctness |
| Real outcome | 0 | Remains unproved; no synthetic savings or production-readiness claim |

Hard gates: creating/comparing branches must not mutate live state; missing critical inputs must not lead to action; no capability beyond declared synthetic adapters; staffing must be feasible; stale preconditions must not be bypassed; retries must not duplicate effects. Every gate must pass the declared suite. This is not safety certification.

Start stochastic comparisons with at least 30 paired seeds per scenario, publishing seeds and uncertainty ranges; deterministic models should publish a parameter grid. Increase samples if conclusions are unstable. This is an engineering starting point, not a statistical guarantee. Report paired changes and worst tested cases. A consistent-improvement claim requires a predeclared practical threshold and a paired uncertainty interval excluding zero, with constraints satisfied. Otherwise report “no demonstrated advantage.”

For a later operator pilot, agree targets before collecting outcomes. Candidate targets: correct source/incident identification in at least 90% of scripted tasks, and 20% lower median task time than the existing dashboard without more incorrect actions. These are proposed acceptance targets, not results or standards. Forecast tolerances must follow operational decision needs and beat persistence/simple queue baselines on held-out days.

## Negative controls to retain beside successes

| Control | Expected behavior |
|---|---|
| Healthy normal operation, no bottleneck | Do nothing can win; do not manufacture work |
| Close longest-wait attraction | Served demand falls or displaced demand rises; lower active-queue mean alone is not success |
| No spare qualified crew / donor at minimum | Reject or omit intervention; do not create people/skills |
| Crew arrives after demand peak | Little benefit or negative cost-benefit |
| Wrong-unit, stale, missing, contradictory data | Explain affected decision; abstain or explicitly bound uncertainty |
| Change scenario label, keep actual state identical | Result follows inputs/assumptions, not incident name |
| Zero guest routing compliance | Benefit declines; no guaranteed queue multiplier |
| Bottleneck moves downstream | Show new queue and total service impact |
| Accepted action never completes | Keep pending/failed; no repaired-service claim |
| Duplicate/lost response/conflicting retry | One effect or explicit conflict; durable evidence after restart |
| Live state changes after planning | Saved result remains reproducible; execution validates current preconditions |
| Model misspecification | Test chosen plan against perturbed demand/service model, separately from planning assumptions |

Use do-nothing, a published simple dispatch rule (one available qualified crew to the largest eligible backlog), and the existing manual scenario response as baselines. Compare under common inputs. If a deterministic optimizer decides, label it accordingly: an API client calling it does not prove LLM reasoning. If adding an LLM, compare against the rule/optimizer client and record tool failures, unnecessary calls, latency and cost.

## Early proposed design review

Root's proposed canonical-state snapshot, immutable future branch, 15–120 minute horizon, five-minute steps, shared-demand uncertainty, do-nothing alternatives and no automatic execution address the largest structural gaps. Returning `calibrated:false`, `review_required` or `insufficient_data` is appropriate. Rejecting scenario creation in replay avoids accidentally treating historical inspection as current operation. Approval remains conditional on code and evidence.

Five-minute aggregate steps cannot establish sub-minute crowd safety or attraction cycle behavior. Require published discretization limits and delay semantics. Finite staff and a simple-rule baseline are still needed; common demand draws alone do not remove self-serving assumptions. The separate proposed execution boundary should validate current preconditions instead of calling existing actions unconditionally.

## Next checkpoint

Deliver accepted observations → immutable branch → constrained forecast → baseline comparison → proposal → current-state validation → synthetic acknowledgement → follow-up. Preserve rejected and failed cases with screenshots.

At major integrations, or roughly hourly during meaningful changes, record exact commit/deployment, inspected evidence, rubric movement, unresolved findings and next decision. Do not issue an approval simply because an hour passed. Request new independent review after planner integration, API exercise and final GPU/browser acceptance; keep subsequent reports separate.

The final claim should state what was measured, for example: “An API-only client compared three constrained synthetic staffing options and refused stale/infeasible execution.” A claim that the agent optimized park operations requires independent operational evidence beyond this experiment.
