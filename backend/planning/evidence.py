"""Immutable historical planning evidence; integrity is not command authority."""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from .contracts import PlanningRequest
from .engine import simulate

SCHEMA = "aster.planning.evidence.v1"
MAX_BUNDLE_BYTES = 1024 * 1024
MAX_BUNDLES = 256
MAX_STORED_BYTES = 64 * 1024 * 1024
MAX_SAFE_INTEGER = 2 ** 53 - 1
# Compute once when these Python modules are loaded. Deployments must restart
# after source changes; immutable release directories preserve this identity.
MODEL_SOURCE_SHA256 = hashlib.sha256(b"\0".join(
    name.encode() + b"\0" + Path(__file__).with_name(name).read_bytes()
    for name in ("contracts.py", "engine.py")
)).hexdigest()


class EvidenceError(ValueError):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def _normalize_numbers(value):
    """Preserve meaning across ordinary browser JSON.parse/stringify transport.

    This is our bounded JSON profile, not a claim of RFC8785 compliance. JSON
    numbers carry no int/float type. JS drops .0 and normalizes negative zero;
    reject integers that cannot be represented safely by its binary64 Number.
    Nonintegral finite floats retain their IEEE754 value across JSON transport.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Nonfinite evidence numbers are not accepted")
            if not value.is_integer():
                return value
        integer = int(value)
        if abs(integer) > MAX_SAFE_INTEGER:
            raise ValueError("Evidence integers must fit JavaScript's safe integer range")
        return integer
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Evidence object keys must be strings")
        return {key: _normalize_numbers(item) for key, item in value.items()}
    raise ValueError("Evidence must contain JSON values only")


def canonical_bytes(value):
    return json.dumps(_normalize_numbers(value), sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def make_bundle(snapshot, request, result, as_of):
    payload = {"schema_version": SCHEMA, "model_source_sha256": MODEL_SOURCE_SHA256,
               "evaluation_as_of": as_of.isoformat(), "snapshot": snapshot,
               "request": request.model_dump(), "result": result}
    payload = json.loads(canonical_bytes(payload))  # Independent, no recursive response alias.
    bundle = {"bundle_id": digest(payload), "payload": payload}
    if len(canonical_bytes(bundle)) > MAX_BUNDLE_BYTES:
        raise EvidenceError("evidence_too_large", "Evidence bundle exceeds the 1 MiB limit", 413)
    return bundle


def verify_bundle(bundle):
    """Recompute supplied historical data, never fetch or mutate a live source.

    A caller can construct synthetic data and a valid digest. Verification proves
    internal consistency/reproduction, not that observations came from this park.
    """
    try:
        if len(canonical_bytes(bundle)) > MAX_BUNDLE_BYTES:
            raise EvidenceError("evidence_too_large", "Evidence bundle exceeds the 1 MiB limit", 413)
        if not isinstance(bundle, dict) or set(bundle) != {"bundle_id", "payload"}:
            raise ValueError("Envelope must contain exactly bundle_id and payload")
        payload = bundle["payload"]
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "model_source_sha256", "evaluation_as_of", "snapshot", "request", "result"}:
            raise ValueError("Evidence payload fields do not match the supported schema")
        if payload["schema_version"] != SCHEMA:
            raise EvidenceError("unsupported_evidence_schema", "Unsupported historical evidence schema", 409)
        if bundle["bundle_id"] != digest(payload):
            raise EvidenceError("evidence_hash_mismatch", "Bundle contents do not match their SHA256 identifier")
        if payload["model_source_sha256"] != MODEL_SOURCE_SHA256:
            raise EvidenceError("evidence_model_mismatch", "This running model cannot reproduce a bundle from another model source", 409)
        as_of = datetime.fromisoformat(payload["evaluation_as_of"].replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            raise ValueError("evaluation_as_of must include a timezone")
        snapshot = payload["snapshot"]
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("assets"), list) or not 1 <= len(snapshot["assets"]) <= 64:
            raise ValueError("Evidence needs 1–64 canonical assets")
        if len({a["id"] for a in snapshot["assets"]}) != len(snapshot["assets"]):
            raise ValueError("Duplicate asset identifiers are not accepted")
        if not isinstance(snapshot.get("recent_actions", []), list) or len(snapshot.get("recent_actions", [])) > 12:
            raise ValueError("Evidence action history is limited to 12 events")
        for asset in snapshot["assets"]:
            if len(asset.get("data_quality", {}).get("fields", {})) > 128:
                raise ValueError("Asset quality metadata exceeds its field bound")
        request = PlanningRequest.model_validate(payload["request"])
        if request.expected_state_revision and request.expected_state_revision.lower() != snapshot.get("accepted_state_revision", "").lower():
            raise ValueError("Request revision does not match the enclosed snapshot")
        reproduced = simulate(snapshot, request, as_of=as_of)
        if canonical_bytes(reproduced) != canonical_bytes(payload["result"]):
            raise EvidenceError("evidence_reproduction_mismatch", "Saved result does not match recomputation from the enclosed inputs")
    except EvidenceError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        raise EvidenceError("invalid_evidence", f"Invalid historical evidence: {exc}") from exc
    return {"verified": True, "bundle_id": bundle["bundle_id"], "model_source_sha256": MODEL_SOURCE_SHA256,
            "scope": "historical_reproduction", "execution_authority": False,
            "origin_authenticated": False,
            "meaning": "Hashes and numerical reproduction match; this does not authenticate source observations or authorize execution."}


class EvidenceStore:
    """Separate SQLite file with immutable rows, explicit caps and no eviction."""
    def __init__(self, path, max_bundles=MAX_BUNDLES, max_bytes=MAX_STORED_BYTES):
        if type(max_bundles) is not int or not 1 <= max_bundles <= MAX_BUNDLES or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_STORED_BYTES:
            raise ValueError("Evidence retention limits exceed supported bounds")
        self.max_bundles, self.max_bytes = max_bundles, max_bytes
        self.lock = threading.RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {"planning_evidence"}:
            self.db.close()
            raise ValueError("Planning evidence refuses a database containing other application tables")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS planning_evidence(bundle_id TEXT PRIMARY KEY, payload TEXT NOT NULL, bytes INTEGER NOT NULL, stored_at TEXT NOT NULL)")
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    def save(self, bundle):
        try:
            encoded = canonical_bytes(bundle)
            frozen = json.loads(encoded)
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            raise EvidenceError("invalid_evidence", f"Invalid historical evidence: {exc}") from exc
        verification = verify_bundle(frozen)
        ident = frozen["bundle_id"]
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                existing = self.db.execute("SELECT stored_at FROM planning_evidence WHERE bundle_id=?", (ident,)).fetchone()
                if existing:
                    self.db.rollback()
                    return {**verification, "saved": True, "already_saved": True, "stored_at": existing["stored_at"]}
                count, size = self.db.execute("SELECT COUNT(*), COALESCE(SUM(bytes),0) FROM planning_evidence").fetchone()
                if count >= self.max_bundles or size + len(encoded) > self.max_bytes:
                    raise EvidenceError("evidence_store_full", "Evidence retention cap reached; existing evidence is preserved without eviction", 409)
                now = datetime.now(timezone.utc).isoformat()
                self.db.execute("INSERT INTO planning_evidence VALUES (?,?,?,?)", (ident, encoded.decode(), len(encoded), now))
                self.db.commit()
                return {**verification, "saved": True, "already_saved": False, "stored_at": now}
            except BaseException:
                self.db.rollback()
                raise

    def get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT payload FROM planning_evidence WHERE bundle_id=?", (ident,)).fetchone()
        if row is None:
            raise EvidenceError("evidence_not_found", "No saved evidence with that identifier", 404)
        return json.loads(row["payload"])

    def list(self, limit=100, offset=0):
        with self.lock:
            rows = self.db.execute("SELECT bundle_id,payload,bytes,stored_at FROM planning_evidence ORDER BY stored_at DESC,bundle_id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            count, size = self.db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM planning_evidence").fetchone()
        items = []
        for row in rows:
            payload = json.loads(row["payload"])["payload"]
            items.append({"bundle_id": row["bundle_id"], "stored_at": row["stored_at"], "bytes": row["bytes"],
                          "evaluation_as_of": payload["evaluation_as_of"], "scenario": payload["request"]["scenario"],
                          "horizon_minutes": payload["request"]["horizon_minutes"], "plan_id": payload["result"]["plan_id"],
                          "model_source_sha256": payload["model_source_sha256"]})
        return {"items": items, "total": count, "stored_payload_bytes": size, "limit": limit, "offset": offset,
                "retention": {"max_bundles": self.max_bundles, "max_payload_bytes": self.max_bytes, "automatic_eviction": False},
                "scope": "historical_evidence", "execution_authority": False}
