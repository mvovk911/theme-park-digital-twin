# Evidence, media and final-run tooling review

Reviewed 19 October 2026. Independent reviewer; no application edits, live service requests, GPU operations or Git mutations. The deployed application evidence identifies `afa84a17d6cc282ed2aa4003743d62770644ea48`. The published interim deck pins its references to `c6d15163b4773bb23796ac6f6ce77131d4d69440`. Tooling was reviewed from the shared working tree at the hashes below; these scopes must not be combined into a single release qualification.

**Recommendation: retain the application feature freeze. Fix the final evidence-summary boundary before publishing a completed eight-hour result. No wholesale rewrite is justified.** The direct incident and dining comparison now explain two specific user tasks. The remaining value question needs operator and field evidence, not more scene detail.

## Evidence inspected

- Six-check [actual GPU incident report](../images/fox-cycle-20261019/gpu-incident-afa84a1/report.json), including current-incident creation, explicit execution, receipt recovery, lost-response retry, mobile fit and the existing saved-comparison path.
- Seven-check [actual GPU spatial report](../images/fox-cycle-20261019/gpu-spatial-afa84a1/report.json), including image-byte identities, exact query export, closure and step-free negative controls, and query-only POSTs.
- Capture, editor and deck source; the five-page deck's editorial copy; rendered page 4 visually inspected for legibility and qualification of policy results.
- `runtime/fox-cycle-20261019/video-take01/capture-manifest.json`. The editor's pure `validate_capture` accepted its 88.001-second content interval, matching initial/final verified release and scene, empty browser-error lists, and successful live/normal cleanup. Raw video was not present beside this local manifest during review. This establishes metadata consistency only; full decode, actual pixel/timing inspection and published-video acceptance remain separate work.
- Offline analyzer, both producers' scheduling code, tests and interim ledger analysis. All six existing analyzer tests passed. Two additional temporary adversarial fixtures reproduced the final-gate findings below without changing repository code or live runs.
- [Spatial/planning coupling research](../research/spatial-planning-coupling.md). Its proposed conservation, transit timing, origin/admission semantics and negative controls are sound boundaries for a later pilot; no implemented coupling is claimed here.

| Reviewed file | SHA256 |
|---|---|
| `operators/analyze_fox_run.py` | `10708cd203ebf5e932d44ea4c9abe49354a57f6064dabda0e7ee1e463732dfcc` |
| `tests/operator_run_analysis_test.py` | `ab1df8199983bd2aa8a0682e3c3757399cc3073b5203f4800a58ddfd838090e7` |
| `scripts/capture_fox_update.py` | `1eb0541739b3837ad844f56e31662d31fd0b2deadcdddd5e42cbabe82250f0f7` |
| `scripts/build_fox_review_deck.py` | `10a90cbd141394c8daf03ef640617973b104253807435de989f1e5d9e4669155` |
| `docs/research/spatial-planning-coupling.md` | `aa19f4dceb0f4162e9a0c89db9472785d8369cc89643812f97ff340c5e44002e` |

## Findings before final reporting

### P1 — Elapsed completion is promoted without carrying observation coverage

The reviewed analyzer deliberately requires only one complete API cycle and one GPU observation, together with reconciled producer counts and an eight-hour clock. Its detailed report discloses gaps, but `final_contract` discards the gaps, pause history and identity-verification details relevant to coverage. The deck then prints `8H RUN COMPLETE` without those qualifications on its summary panel.

Reproduction: the existing test fixture with one GPU observation at `00:00:00`, a producer finish at `08:00:00`, and 28,800 elapsed seconds returns `verified_eight_hour_complete: true`. Its own analysis reports 28,800 trailing unobserved seconds. Changing that observation's timestamp to `not-a-time` still returns true; leading/trailing coverage becomes null and only a warning remains. A valid Git-shaped hash also does not itself establish `verified_manifest` source verification.

This is not a claim that the actual run has these defects. It demonstrates that the final evidence contract cannot currently distinguish them. The interim deck is correctly marked interim and is not invalidated by this finding.

Minimum correction:

1. Keep **producer elapsed completion**, **ledger reconciliation**, **observation schedule coverage**, **source verification** and **check outcomes** separate. Recorded failures may belong to a completed experiment and must remain visible.
2. Required check/observation timestamps must be parseable and timezone-aware for finalization. Invalid times cannot become absent coverage silently. Finalization must also reject inputs marked changed during their individual read; recapture stable completed files instead of repairing counters.
3. Carry requested interval, cycle/sample count, all leading/inter-sample/trailing gaps, pauses, identity verification and coverage classification into the final contract and deck. Do not display a generic completion badge that loses these limits.
4. Derive a coverage diagnostic from the producer's schedule rather than selecting a percentage that the current run happens to pass. Both producers schedule the next start at `max(previous start + configured interval, previous work completion)`. The API ledger retains each check's start and duration, so the final cleanup end can establish cycle completion and the startup check can explain initial delay. The GPU observation does not retain its complete duration; do not invent it from a successful frame age or a later sample. Label any allowance based on known request timeout limits as a conservative bound, not measured execution time.
5. Report lateness beyond this due time using a fixed, documented allowance tied to timestamp precision and the producer's polling/sleep implementation. Retain actual gap durations regardless of classification. An explicit pause covers health-only checks, never functional interventions. If duration evidence is insufficient, classify coverage as uncertain rather than silently passing it.

Root accepted this finding and assigned analyzer and deck corrections. They were pending at the reviewed hashes. Final acceptance should include both the single-observation and invalid-time counterexamples, stable-file gating, paused coverage, a genuinely slow recorded API cycle, and the updated consumer's preservation of warnings. Do not rewrite this baseline as though those fixes already passed.

### P2 — A small shared evidence contract would prevent tooling drift

The analyzer accepts a two-second start/finish-versus-elapsed discrepancy; the deck consumer independently accepts five seconds. They also duplicate commit, duration and completion validation. The analyzer's JSON is the useful boundary; extracting a small dependency-free, versioned schema/validator after the correction would reduce drift. The deck should validate that contract and render its classifications, without independently redefining experiment success.

This is a bounded refactor, not grounds for rebuilding the project. Capture, editing, analysis and deck production have different dependencies and effects, and their current separation is valuable. Keep the media toolchain outside the application environment. Do not import the backend or renderer into the offline analyzer. The four tools total approximately 1,461 lines at this checkpoint; size alone is not evidence of an uncontrollable system.

The recorder and editor appropriately preserve the raw take, caption timings, unchanged application geometry, cleanup evidence and hashes. Caption timing is based on monotonic page creation and is only approximate relative to encoded frames; final visual inspection must still verify that each explanatory caption accompanies the demonstrated result. A metadata gate is not a substitute for that check.

## End-user value and claims

The strongest current operator story is **identify a closed ride, inspect current source evidence, request one work order, and verify the exact accepted order while the ride remains closed**. The four-versus-seven scripted-step comparison is accurately labeled; it does not establish faster human incident handling. The next useful measurement is alert-to-verified-order time and incorrect/duplicate-order rate against the operator's current tool, including stale source data and ambiguous execution responses.

The spatial story answers **whether this authored dining connection resolves this authored route gap**. The baseline is unreachable, the candidate is 40.852 m, and closure or the unresolved entrance threshold can remove access. These are useful design-review controls. They do not establish a percentage walking-time saving, certified accessibility, crowd capacity or additional food service throughput. Native before/after closeups improve communication because the actual design change can be inspected; adding visual detail alone would not strengthen these claims.

The deck retains the adverse policy findings: 216 identical schedules, 108 extra-staff choices, 52 of those without a waiting benefit, and 92 grid cases where baseline dominates the planner choice. It also shows the subgroup and whole-grid costs and explains missing minimum-coverage, donor-loss and replenishment-cost constraints. These are counts in a synthetic test grid, not outcome probabilities, staffing advice or measured ROI. This is useful evidence against expanding planner autonomy now.

The FOX framing remains architectural inspiration. Current media explicitly says FOX, NemoClaw and OpenShell are not installed; the fixed API exercise is a deterministic client, not an LLM operating the park. No additional claim about current FOX product availability was independently researched in this tooling-only review.

## Next experiment and release decision

Finish the existing eight-hour collection and publish reconciled evidence with the coverage corrections above. Complete actual video decode and visual acceptance before calling the new presentation accepted. These are the only necessary changes identified before final evaluation; the application can remain frozen.

For the next cycle, predeclare a small counterbalanced operator comparison using matched incidents: existing workflow versus direct incident UI, including duplicate orders, stale observations and lost acknowledgements. Record completion time, requests/clicks, errors, successful recovery and whether the operator correctly distinguishes acceptance from repair. Report each participant/task and failures; do not infer population productivity from a scripted demonstration or a small convenience sample. Obtain real operator workflow and data access before adding more integration surface.

Treat spatial/queue coupling as a separate experiment only after destination admission and upstream release data exist. The research document's proposed cohort conservation and event-time controls are appropriate; attaching the current graph to the current fluid queue forecast without that evidence would introduce a persuasive but unvalidated relationship.

## Addendum — independent verification of the v2 evidence boundary

The original review above remains a record of its exact earlier hashes. Root assigned the reported corrections, and this follow-up independently inspected the resulting analyzer and deck consumer on 19 October 2026.

| Rechecked file | SHA256 |
|---|---|
| `operators/analyze_fox_run.py` | `7833c30d628d603873a876b121c78870b0c4735dde2083884d12b15e06d6719d` |
| `tests/operator_run_analysis_test.py` | `08ea9624905b8e34fe749a1be43b71c580b3d435368ec3175578e25e6a7a9e18` |
| `scripts/build_fox_review_deck.py` | `8dfac4a5aa8feaf116cdb0e52614846400413631b5c843e8b7b3c289dd37649d` |

**The P1 final-summary finding is addressed at these hashes.** The new `aster.review-run.v2` contract separates elapsed/reconciled completion, schedule coverage and source verification. A single initial observation plus an eight-hour clock leaves 28,770 unsupported schedule seconds and cannot finalize. Invalid required timestamps and files flagged as changing during their read block reconciliation. Invalid configured intervals and decreasing required-record timestamps also block completion; diagnostic fallback values are not accepted evidence.

The cadence rule uses configured intervals and recorded CPU execution completion with a declared two-second scheduling allowance. Explicit pause intervals are subtracted from functional schedule windows; matching ten-second health-only observations must support them separately. The GPU's missing total request duration remains an explicit limitation. Tests retain a long CPU cycle and a supported 20-second pause as positive controls, while rejecting the same pause without health observations, including when a preceding long cycle interval would otherwise hide the gap. All gap durations remain visible, even those within the allowance.

The contract retains uncovered intervals, pauses, failures, transport errors, warnings, empty reconciled-error evidence, input capture metadata and all observed identity transitions. Verification requires consistent release-manifest fields; `verified: true` cannot override dirty or mismatching source evidence. The shared consumer validates totals and verification counts against retained details. This is consistency validation of supplied evidence, not independent process attestation or protection against fabricated ledgers.

During this follow-up, the reviewer found a second timing counterexample: two early CPU cycles with `cleanup.duration_seconds = 999999` manufactured adequate coverage, even though cleanup extended past the run finish and overlapped the next cycle. The operator fixed it before this acceptance. Each serial check's recorded end must now precede the next required check and the reported run finish, with a separate **0.002-second duration precision allowance**. The regression rejects both contradictions. Changing those durations to legitimate 90-second checks preserves elapsed reconciliation while correctly rejecting sparse coverage. This closes the identified path by which impossible execution duration could excuse missing observations.

Independent verification performed:

- All **16 focused analyzer tests passed**, including original sparse/invalid-time/changed-read controls, source-verification contradictions, pauses, legitimate slow work and the new impossible-duration regression.
- Imported the **actual deck module** in `/tmp/park-review-tools`, without AST extraction or installing media dependencies into the application environment. A clearly synthetic dense v2 fixture was accepted; missing coverage, inadequate coverage and unverified identity variants were rejected. The fixture was temporary and is not experiment evidence.
- Inspected the revised deck code and copy. It imports the same dependency-free validator, removes the former independent five-second rule, labels final mode `8H SAMPLED REVIEW`, and displays cadence, total/max uncovered time, functional schedule windows, recorded pauses, health-only windows, verification counts and retained failures. Full warnings and interval/identity details remain in the contract/manifest. The existing published interim artifact is not evidence of this final-mode layout or a completed run.

No remaining material blocker was identified in this scoped tooling recheck. Publication of actual final results still requires collecting and reconciling the completed real ledgers; these fixture and code checks do not establish that the eight-hour run has finished. No application changes or GPU operations were needed for these corrections.
