# FOX run evidence analysis

Analysis captured at 2026-10-19T21:50:29.832826+00:00.

**Verified eight-hour completion for both tracks: no.**

| Track | Producer complete | Elapsed seconds | UTC span | Full cycles / samples | Failures |
|---|---:|---:|---:|---:|---:|
| fixed_api | False | 7273.226 | None | 25 | 0 |
| gpu_observer | False | 7272.243 | None | 243 | 1 |

These are recorded checks and observation samples, **not continuous uptime**. Expected negative-test HTTP responses are not automatically failures; recorded failed checks and transport failures remain visible. No failure is reclassified as a deployment artifact without additional evidence.

## fixed_api

Source commits: d3dca3d20612d3d09ed1acb680683a990cbd51ba.
Elapsed/reconciled complete: False; scheduled coverage adequate: True. Unobserved schedule seconds: 2.297854; largest uncovered interval: 0.366679 seconds.
Paused wall time: 0.0 seconds. Health request latency: {"count": 1, "min": 69.43, "median": 69.43, "p95": 69.43, "p99": 69.43, "max": 69.43, "mean": 69.43, "percentile_method": "linear interpolation between sorted observations"}.
Frame age: {"count": 0, "min": null, "median": null, "p95": null, "p99": null, "max": null, "mean": null, "percentile_method": "linear interpolation between sorted observations"}.
Journal records: 4220; check/sample types: {"startup": {"pass": 1}, "compare_read_only": {"pass": 25}, "interventions": {"pass": 25}, "retries_and_errors": {"pass": 25}, "source_failures": {"pass": 25}, "source_model_conflict": {"pass": 25}, "replay_guards": {"pass": 25}, "planning_counterfactuals": {"pass": 25}, "planning_degraded_input": {"pass": 25}, "planning_assumption_stress": {"pass": 25}, "cleanup": {"pass": 25}}.
Source verification transitions: 1; transport errors: 0.

Source verification: {"verified_count": 1, "unverified_count": 0, "unknown_count": 0, "count_unit": "source_identity_transitions", "all_observed_identities_verified": true}.

- Mixed journal timestamps are not monotonic: check.utc records check start, while HTTP utc records request completion. This alone does not establish clock movement or reordered observations.

- Incomplete or inconsistent evidence: no verified eight-hour completion claim is permitted.

## gpu_observer

Source commits: 20f0ca8519b1ef0424f30855691f65cab0dda154, d3dca3d20612d3d09ed1acb680683a990cbd51ba, 64c8bfa28b81030b61d3dd7b1589cf5e7902d4a4, afa84a17d6cc282ed2aa4003743d62770644ea48.
Elapsed/reconciled complete: False; scheduled coverage adequate: True. Unobserved schedule seconds: 2.178543; largest uncovered interval: 0.010451 seconds.
Paused wall time: 0 seconds. Health request latency: {"count": 242, "min": 1.75, "median": 2.07, "p95": 17.125, "p99": 40.1791, "max": 71.62, "mean": 3.971942, "percentile_method": "linear interpolation between sorted observations"}.
Frame age: {"count": 242, "min": 0.002, "median": 0.0425, "p95": 0.079, "p99": 0.10726, "max": 0.141, "mean": 0.04326, "percentile_method": "linear interpolation between sorted observations"}.
Journal records: 728; check/sample types: {"observation": {"pass": 242, "fail": 1}}.
Source verification transitions: 4; transport errors: 1.

Source verification: {"verified_count": 4, "unverified_count": 0, "unknown_count": 0, "count_unit": "source_identity_transitions", "all_observed_identities_verified": true}.

- Mixed journal timestamps are not monotonic: check.utc records check start, while HTTP utc records request completion. This alone does not establish clock movement or reordered observations.

- GPU observer spans multiple deployments; this is not a single-release soak.

- Incomplete or inconsistent evidence: no verified eight-hour completion claim is permitted.

- Failed record 2026-10-19T19:49:33.123754+00:00, 4: URLError: <urlopen error [Errno 111] Connection refused>

## Resource observations

99 rows, 2026/10/19 20:10:40.015 through 2026/10/19 21:48:40.274; observed span 5880.258999824524 seconds.

| CSV column | Min | Max | First | Last | Endpoint change/hour |
|---|---:|---:|---:|---:|---:|
|  memory.used [MiB] | 1.0 | 3848.0 | 2935.0 | 2919.0 | -9.795487 |
|  memory.total [MiB] | 49140.0 | 49140.0 | 49140.0 | 49140.0 | 0.0 |
|  utilization.gpu [%] | 0.0 | 11.0 | 5.0 | 5.0 | 0.0 |
|  utilization.memory [%] | 0.0 | 4.0 | 2.0 | 2.0 | 0.0 |
|  power.draw [W] | 90.44 | 110.49 | 98.15 | 106.4 | 5.050798 |
|  temperature.gpu | 35.0 | 37.0 | 36.0 | 35.0 | -0.612218 |

Resource sampling began later than the API/GPU experiment (reported start 20:10:39 UTC); this file does not establish full eight-hour resource coverage.
NVIDIA CSV timestamps without timezone are interpreted as UTC based on this experiment context; this is an explicit assumption, not timezone evidence in the CSV.
Measurements may include the static renderer and other processes. Endpoint trends are descriptive, not memory-leak certification or workload attribution.
Numeric columns retain CSV units/names; numeric IDs or counters must not be interpreted as utilization. No interpolation across missing samples.

Exact input SHA256, sizes, capture times, failed-sample sequences, unobserved intervals, source identities and reconciliation details are in `analysis.json`. Files are captured individually, not as an atomic cross-file snapshot. A live writer can therefore produce a temporary count mismatch; it is reported, never silently corrected.

The final `aster.review-run.v2` file is emitted only when both producers report completion, both monotonic elapsed and actual timezone-aware start/finish spans are at least 28,800 seconds, and the ledgers reconcile. Failed checks can remain in a completed run.
