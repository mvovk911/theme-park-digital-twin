# FOX run evidence analysis

Analysis captured at 2026-10-19T21:02:35.909470+00:00.

**Verified eight-hour completion for both tracks: no.**

| Track | Producer complete | Elapsed seconds | UTC span | Full cycles / samples | Failures |
|---|---:|---:|---:|---:|---:|
| fixed_api | False | 4501.278 | None | 15 | 0 |
| gpu_observer | False | 4321.336 | None | 145 | 1 |

These are recorded checks and observation samples, **not continuous uptime**. Expected negative-test HTTP responses are not automatically failures; recorded failed checks and transport failures remain visible. No failure is reclassified as a deployment artifact without additional evidence.

## fixed_api

Source commits: d3dca3d20612d3d09ed1acb680683a990cbd51ba.
Paused wall time: 0.0 seconds. Health request latency: {"count": 1, "min": 69.43, "median": 69.43, "p95": 69.43, "p99": 69.43, "max": 69.43, "mean": 69.43, "percentile_method": "linear interpolation between sorted observations"}.
Frame age: {"count": 0, "min": null, "median": null, "p95": null, "p99": null, "max": null, "mean": null, "percentile_method": "linear interpolation between sorted observations"}.
Journal records: 2538; check/sample types: {"startup": {"pass": 1}, "compare_read_only": {"pass": 15}, "interventions": {"pass": 15}, "retries_and_errors": {"pass": 15}, "source_failures": {"pass": 15}, "source_model_conflict": {"pass": 15}, "replay_guards": {"pass": 15}, "planning_counterfactuals": {"pass": 15}, "planning_degraded_input": {"pass": 15}, "planning_assumption_stress": {"pass": 15}, "cleanup": {"pass": 15}}.
Source verification transitions: 1; transport errors: 0.

- Journal UTC timestamps decrease; concurrent logging or clock movement needs review.

- Incomplete or inconsistent evidence: no verified eight-hour completion claim is permitted.

## gpu_observer

Source commits: 20f0ca8519b1ef0424f30855691f65cab0dda154, d3dca3d20612d3d09ed1acb680683a990cbd51ba, 64c8bfa28b81030b61d3dd7b1589cf5e7902d4a4, afa84a17d6cc282ed2aa4003743d62770644ea48.
Paused wall time: 0 seconds. Health request latency: {"count": 144, "min": 1.76, "median": 2.06, "p95": 21.14, "p99": 40.1493, "max": 42.43, "mean": 3.994167, "percentile_method": "linear interpolation between sorted observations"}.
Frame age: {"count": 144, "min": 0.003, "median": 0.04, "p95": 0.079, "p99": 0.10698, "max": 0.14, "mean": 0.043049, "percentile_method": "linear interpolation between sorted observations"}.
Journal records: 434; check/sample types: {"observation": {"pass": 144, "fail": 1}}.
Source verification transitions: 4; transport errors: 1.

- Journal UTC timestamps decrease; concurrent logging or clock movement needs review.

- GPU observer spans multiple deployments; this is not a single-release soak.

- Incomplete or inconsistent evidence: no verified eight-hour completion claim is permitted.

- Failed record 2026-10-19T19:49:33.123754+00:00, 4: URLError: <urlopen error [Errno 111] Connection refused>

## Resource observations

49 rows, 2026/10/19 20:10:40.015 through 2026/10/19 20:58:40.229; observed span 2880.2139999866486 seconds.

| CSV column | Min | Max | First | Last | Endpoint change/hour |
|---|---:|---:|---:|---:|---:|
|  memory.used [MiB] | 1.0 | 3848.0 | 2935.0 | 2919.0 | -19.998514 |
|  memory.total [MiB] | 49140.0 | 49140.0 | 49140.0 | 49140.0 | 0.0 |
|  utilization.gpu [%] | 0.0 | 11.0 | 5.0 | 5.0 | 0.0 |
|  utilization.memory [%] | 0.0 | 4.0 | 2.0 | 2.0 | 0.0 |
|  power.draw [W] | 90.44 | 108.37 | 98.15 | 105.53 | 9.224315 |
|  temperature.gpu | 35.0 | 36.0 | 36.0 | 36.0 | 0.0 |

Resource sampling began later than the API/GPU experiment (reported start 20:10:39 UTC); this file does not establish full eight-hour resource coverage.
NVIDIA CSV timestamps without timezone are interpreted as UTC based on this experiment context; this is an explicit assumption, not timezone evidence in the CSV.
Measurements may include the static renderer and other processes. Endpoint trends are descriptive, not memory-leak certification or workload attribution.
Numeric columns retain CSV units/names; numeric IDs or counters must not be interpreted as utilization. No interpolation across missing samples.

Exact input SHA256, sizes, capture times, failed-sample sequences, unobserved intervals, source identities and reconciliation details are in `analysis.json`. Files are captured individually, not as an atomic cross-file snapshot. A live writer can therefore produce a temporary count mismatch; it is reported, never silently corrected.

The final `aster.review-run.v1` file is emitted only when both producers report completion, both monotonic elapsed and actual timezone-aware start/finish spans are at least 28,800 seconds, and the ledgers reconcile. Failed checks can remain in a completed run.
