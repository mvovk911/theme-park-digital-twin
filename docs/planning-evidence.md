# Saved planning comparisons

A saved comparison contains the complete frozen observation snapshot, normalized planning request, explicit evaluation time, model source fingerprint and numerical result. It remains usable after the 64-revision live cache expires or the gateway restarts. Saving or opening a comparison never changes live park state or the recorded-view cursor.

The current numerical model is `aster-fluid-planner` version `1.1.0`. This version normalizes default numeric request values before hashing so an exported/reimported request retains its plan identity. Exact source fingerprints distinguish changes within the same semantic model version as well.

This is historical evidence, not execution authority. A content hash detects changes and recomputation establishes internal consistency. Neither authenticates the observations' origin: a caller can construct synthetic observations and a consistent bundle. The API states `origin_authenticated: false` and `execution_authority: false` even when verification succeeds.

## API workflow

1. `POST /api/planning/simulate` returns the normal comparison plus `evidence_bundle`. This does not save anything. Keep that exact bundle to preserve the comparison currently displayed; do not recompute from the latest live state when the user clicks Save.
2. `POST /api/planning/evidence` with the raw bundle as its JSON body verifies and stores it. `already_saved: true` acknowledges an identical saved bundle without another row.
3. `GET /api/planning/evidence?limit=100&offset=0` lists saved summaries, total count and retention usage.
4. `GET /api/planning/evidence/{bundle_id}` returns the exact saved bundle for reopening or downloading. There is no separate export endpoint.
5. `POST /api/planning/evidence/verify` with a bundle reproduces the historical result without saving it or consulting live data.

All evidence endpoints work while live or recorded view is selected. Prospective `/simulate` still requires live view. Opening saved evidence should show a historical-comparison label and retain its original parameters, timestamp and model identity. Verification of an old snapshot uses its saved evaluation time, not today's source freshness. That permits historical reproduction; it does not make an old decision valid for action today.

```json
{
  "bundle_id": "<SHA256 of canonical payload>",
  "payload": {
    "schema_version": "aster.planning.evidence.v1",
    "model_source_sha256": "<fingerprint of contracts.py and engine.py>",
    "evaluation_as_of": "2026-10-19T20:00:00.000000+00:00",
    "snapshot": {"accepted_state_revision": "...", "assets": []},
    "request": {"scenario": "food_rush", "horizon_minutes": 60},
    "result": {"plan_id": "...", "branches": []}
  }
}
```

The abbreviated example is explanatory and cannot pass verification. Use the complete server-generated bundle. Canonical serialization sorts object keys, uses compact separators and ASCII escapes, and rejects nonfinite numbers. Integral floats normalize to integers (`1.0` becomes `1`) and negative zero to zero. Integers outside JavaScript's safe range, ±(2^53−1), are rejected, including integral floats outside that range. Finite nonintegral floats retain their binary64 value. This bounded JSON profile permits ordinary browser `JSON.parse`/`JSON.stringify` transport without changing a bundle's meaning or hash; it is not a claim of RFC 8785 compliance. Hash checking and recomputed-result comparison use the same normalization. The browser must not regenerate a hash to conceal changed content.

The bundle identifier is the SHA256 of the canonical payload. The numerical model fingerprint includes exact `contracts.py` and `engine.py` bytes loaded at process startup. Restart after editing source; deployed immutable release directories preserve reproducibility.

Verification validates the envelope schema and bounds, checks its hash and known model fingerprint, parses a timezone-aware evaluation time, validates the planning request, then runs the pure model against the enclosed snapshot. The reproduced result must match the saved result under canonical serialization. It never resolves the original revision through the live cache.

A different model fingerprint returns `409 evidence_model_mismatch`; the stored bundle remains downloadable. Reproduction with a former model requires that exact source version in an isolated environment. The service does not silently migrate forecasts or rewrite saved conclusions when model code changes.

## Persistence and bounds

`PARK_PLANNING_DB` sets an independent SQLite database path. By default, `planning.db` is placed beside the live park database; an in-memory park defaults to an independent in-memory evidence store. The installer wraps the existing application lifespan and closes its connection on shutdown. It does not add tables to the park or replay databases, and refuses an existing database with foreign tables.

Retention is explicit: at most 256 bundles and 64 MiB of serialized bundle payload, with a 1 MiB limit per bundle. The total is logical JSON payload size; SQLite indexes, journal and filesystem overhead are additional. There is no automatic expiry or eviction. A full store returns `409 evidence_store_full` while preserving existing evidence. Export/archive and deliberate operator-managed storage maintenance are required before more evidence can be accepted. No deletion API is provided in this slice.

The HTTP reader bounds the body while streaming, rejects duplicate JSON keys and nonfinite constants, and validates asset/history sizes before recomputation. Imported data is untrusted historical input and has no mechanism to run code, select a live scenario or issue a park action. Files under `backend/data/` remain excluded from Git; publish selected exported synthetic bundles as explicit review artifacts rather than committing a running database.

## Checks

`tests/test_planning_evidence.py` verifies deterministic reproduction, tamper detection even after rehashing, unknown model/schema rejection, duplicate saves, capacity handling without eviction, foreign-database protection, HTTP input bounds, cache-independent save, and restart/export/reverification. The existing planning tests check live-state isolation and scenario behavior. These establish software contracts, not forecast calibration or real-world operating value.

## Browser acceptance evidence

Eleven durable browser tests passed, including browser JSON round-tripping against
the real evidence verifier. Ten additional checks against an isolated running
service covered save, download/verify, reopen after reload, import, tamper rejection,
historical inspection during replay, source-quality abstention and mobile layout.
The [actual local-service report and screenshots](images/fox-cycle-20261019/evidence-library/report.json)
are separate from the earlier actual GPU evidence. They do not claim a new GPU
rendering acceptance for the evidence-library release.
