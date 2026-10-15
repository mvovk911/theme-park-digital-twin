# Recorded park inspection

The live accepted read model and the selected historical view are distinct. The
simulator and connectors keep advancing while an operator inspects a recorded
snapshot. Returning to live reads the latest state; replay never writes a past
value back into the live simulator.

## Data and versions

`ReplayStore` in `backend/replay_store.py` stores complete accepted operational
snapshots as compressed JSON in a separate SQLite database. Each record contains
asset values, KPI values, source health/provenance, scenario/tick/time, recent
audit, scene hash and a configuration hash. Work-order detail is captured through
the simulator's public workflow snapshot only when its tick matches the data.
Historical detail/history reads the chosen record; it does not fetch today's
work orders or queue history and display them under an old timestamp.

The default recording interval is two seconds, plus immediate capture after
successful operator/connector mutations. The default retention is 7,200 records;
action captures count toward that bound, so the time span varies. Identical full
captures are deduplicated. Retention is checked on every new record. A currently
selected record remains immutable even if later retention removes its row from
the timeline. Restarting the service opens in live mode while preserving history.

The database defaults to `backend/data/replay.db`; override `PARK_REPLAY_DB` for a
different location. It is runtime data and excluded from Git. The store owns its
connection and lock; the API adapter owns the cursor/read-only workflow. It does
not evaluate scenario rules or own connector ingestion.

## View API

- `GET /api/timeline?limit=300`: ordered snapshot summaries, versions, pose
  availability, current cursor, retention and recording errors.
- `GET /api/view/state`: complete displayed state plus a `view` metadata object.
- `POST /api/view` with `{"mode":"replay","snapshot_id":42}` selects history;
  `{"mode":"live"}` returns to current observations.
- `GET /api/view/assets/{id}` and `/api/view/assets/{id}/history?limit=90` use the
  same selected view, with history clipped at that record.

The prototype has one shared view/camera. While replay is selected, scenario
changes, actions, connector simulation-mode changes and live-model scenario
comparison return HTTP 409. These requests are serialized with view changes so a
second viewer cannot race a cursor change into an accepted operator write.
Validated source events at `POST /api/connectors/{source}/ingest` remain permitted:
acquisition updates only live state and new recordings, never the selected historical
payload. The source must already be paused for an independent synthetic producer
to own it; that mode cannot be changed while replay is selected. Both in-process
and HTTP source production continue. Camera controls and native picks remain available.

## Rendered pose and freshness

The renderer reads `/api/view/state`. Historical view freezes ride animation.
A presentation pose is recorded only when GPU status identifies the same live
source tick and scene hash. Otherwise the snapshot explicitly has no recorded
pose; the application must state that pose is unavailable rather than invent
historical motion. Recordings from a different scene version retain accurate
recorded data, but cannot claim matching current geometry/pose.

The renderer publishes JPEG bytes together with frame number, original rendered
UTC time, source timestamp/tick, scene hash, view mode and snapshot ID. Gateway
responses preserve this metadata in `X-Frame-*`, `X-Source-*`, `X-View-*` and related
headers. Repeated downloads of a cached image retain its original identity/time.
Frame age and source age are separate: a new camera render can still show stale
source data. Missing/stale authoritative ride-status samples freeze that ride's
presentation motion and expose the reason; they do not control physical rides.

## Validation scope

CPU checks cover durable exact values across restart/config changes, bounded
retention, immutable selected snapshots, historical history/work orders,
read-only API guards, live advancement during replay, cursor validation and no
invented pose. Separate command/frame tests cover expiry, failure and provenance.
Actual GPU/browser replay passed on `2e2b16b`; native lifecycle and actual HTTP
producer/replay/restart checks also passed on final `19cee1e`. See the
[revision-bound evidence](validation.md). CPU fixtures remain separate from real
SDK evidence; neither run establishes exhaustive GPU resource leak coverage.

## Accepted-state and frame association

Simulator tick alone is not an accepted-state identity: external synthetic events
can change an asset within the same tick. Canonical snapshots therefore carry
`accepted_state_revision`, a SHA256 content identity over asset values,
provenance, quality status/reasons and source modes. Increasing age counters alone
do not change it; a stale-quality transition does. This identifies a particular
accepted projection, not a durable event-stream offset or physical observation.

Recorded motion is attached only when the renderer reports the same scene, tick
and nonempty accepted-state revision. JPEG responses carry that revision plus an
immutable camera/projection context. Overlay coordinates never borrow a newer
camera from `/status`. The UI suppresses annotations for missing context or
mismatched revisions. These contracts have CPU/API checks and actual GPU/browser
evidence. A small immutable revision cache keeps annotations tied to the displayed
image while the inspector remains latest; [frontend semantics](frontend.md).

Versioned UI picks carry the displayed camera token, accepted-state revision and
view identity. The render owner checks these before issuing the native pick and
returns conflict if they changed. This selects an asset in the current geometry;
it does not reconstruct the historical pixel coverage of an animated ride. Direct
legacy pick requests without a token remain unversioned for compatibility.

Matching pose samples must also have a timezone-qualified render time no more than
five seconds old and not in the future. Missing, malformed, naive or older frame
times leave the record without motion. Captured motion retains its original frame
number, render time, accepted-state revision and scene hash under `provenance`.
It is the last matching rendered pose, not an interpolated pose at the snapshot's
wall-clock capture time. Status copies state and cached frame under one publication
lock; pose/status/quality are also part of immutable frame metadata.
