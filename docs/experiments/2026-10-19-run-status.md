# Eight-hour experiment status

This is a running experiment, not a completed eight-hour result.

| Track | Actual start (UTC) | Planned finish (UTC) | Source |
| --- | --- | --- | --- |
| Isolated API exercise | 2026-10-19 19:47:34 | 2026-10-20 03:47:34 | Fixed `d3dca3d20612d3d09ed1acb680683a990cbd51ba` |
| GPU read-only observation | 2026-10-19 19:47:33 | 2026-10-20 03:47:33 | Observer fixed at `d3dca3d`; deployment revisions recorded per sample |

The API exercise uses a separate database and process supervisor. It repeats HTTP
checks every five minutes, including explicit non-benefit cases, degraded inputs,
replay isolation and durable retries. Any paused interval remains part of the wall
clock and is reported separately from mutation cycles.

The GPU observer checks health and exact downloaded JPEG provenance every 30
seconds and saves a frame approximately hourly. It observes the development
renderer across deployments. One connection-refused sample at 19:49:33 UTC
coincided with the deliberate deployment from `20f0ca8` to `d3dca3d`; that failure
remains in the record. This is an observed development-session availability test,
not an uninterrupted-production-uptime claim.

First-cycle API checks passed; subsequent counts remain in the live runtime ledger
until a dated checkpoint or final report is published. Both tools are deterministic
clients, not an LLM agent embedded in the application. Independent coding agents
review their methods and results.

The developer will stop temporary Horde compute after final collection while
preserving the project workspace. Approximately 05:47 CEST is the target finish,
with collection and shutdown following it.
