"""Actual HTTP acceptance for synthetic acquisition, replay and durable actions.

Changes shared synthetic state; run exclusively against a coordinated gateway.
No GPU/rendering claim is made. The restart is performed separately by the operator.
Initial: python tests/live_workflow_acceptance.py --url http://127.0.0.1:8100 --output /tmp/workflow-initial.json
After restart: add --verify-restart /tmp/workflow-initial.json --output /tmp/workflow-restart.json
Existing evidence files are never overwritten.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulators.producer import SyntheticProducer, publish_batch, require_paused_sources
from backend.connectors.catalog import default_catalog


SCOPE = "Actual HTTP synthetic workflow acceptance; not physical systems or GPU rendering validation"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class API:
    def __init__(self, url):
        self.client = httpx.Client(base_url=url, timeout=httpx.Timeout(8, connect=3), trust_env=False, follow_redirects=False)

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        require(response.status_code == 200, f"GET {path}: HTTP {response.status_code}")
        return response.json()

    def post(self, path, payload, status=200):
        response = self.client.post(path, json=payload)
        require(response.status_code == status, f"POST {path}: HTTP {response.status_code}, expected {status}")
        return response.json()

    def audit(self):
        return self.get("/api/audit", limit=1000)["events"]


def frozen_view(state):
    return {key: state[key] for key in ("assets", "kpis", "accepted_state_revision", "scenario", "tick", "timestamp")}


def baseline(api):
    state = api.get("/api/state")
    catalog = api.get("/api/connectors")["connectors"]
    require(state.get("synthetic") is True, "Gateway is not explicitly synthetic")
    require(all(source.get("synthetic") is True for source in catalog), "Catalog includes a non-synthetic source")
    return {"scenario": state["scenario"], "source_modes": {source["id"]: source["health"]["mode"] for source in catalog},
            "initial_view": api.get("/api/view/state")["view"]}


def restore(api, original, report):
    """Best-effort independent cleanup; never hide the first acceptance failure."""
    results = []
    if original is None:
        report["cleanup"] = [{"operation": "no_mutations_started", "ok": True}]
        return True
    api.client.timeout = httpx.Timeout(3, connect=2)
    operations = [("view_live", lambda: api.post("/api/view", {"mode": "live"}))]
    if original:
        def scenario():
            current = api.get("/api/state")["scenario"]
            if current != original["scenario"]:
                api.post("/api/scenarios", {"scenario": original["scenario"]})
            return {"scenario": original["scenario"], "changed": current != original["scenario"]}
        operations.append(("scenario", scenario))
        for source, mode in original["source_modes"].items():
            operations.append((f"source:{source}", lambda source=source, mode=mode:
                               api.post(f"/api/connectors/{source}/simulation", {"mode": mode})))
    for name, operation in operations:
        try:
            value = operation()
            results.append({"operation": name, "ok": True, "mode": value.get("mode", value.get("view", {}).get("mode"))})
        except Exception as exc:
            results.append({"operation": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    report["cleanup"] = results
    return all(result["ok"] for result in results)


def producer_replay_acceptance(api, report):
    sources = [spec.id for spec in default_catalog()]
    remote_sources = {source["id"] for source in api.get("/api/connectors")["connectors"]}
    require(len(sources) == 10 and remote_sources == set(sources), "Expected exactly the ten local catalog sources")
    for source in sources:
        api.post(f"/api/connectors/{source}/simulation", {"mode": "paused"})
    require_paused_sources(api.client, sources)
    timeline = api.get("/api/timeline", limit=100)
    require(not timeline["recording_error"] and timeline["snapshots"], "No healthy recorded snapshot is available")
    selected_id = timeline["snapshots"][-1]["id"]
    selected = api.post("/api/view", {"mode": "replay", "snapshot_id": selected_id})
    frozen = frozen_view(selected)
    before_latest = timeline["snapshots"][-1]["id"]
    report["acquisition_during_replay"] = evidence = {
        "execution": "Ten independent producer instances, unique sessions, concurrent HTTP threads; not subprocess isolation",
        "profile": "heatwave", "selected_snapshot_id": selected_id,
        "selected_before": frozen, "selected_before_sha256": digest(frozen),
        "timeline_latest_before": before_latest, "batches": [], "sources": {},
    }
    producers = {source: SyntheticProducer([source], "heatwave") for source in sources}
    require(len({producer.session_id for producer in producers.values()}) == 10, "Producer sessions are not independent")
    latest_batches = {}
    for tick in (1, 2):
        def send(source):
            batch = producers[source].batches(tick)[source]
            result = publish_batch(api.client, source, batch, retries=1)
            require(result["accepted"] + result["duplicates"] == len(batch["events"]), f"Incomplete source batch: {source}")
            require(result["health"]["mode"] == "paused", f"Source mode changed: {source}")
            return source, batch, result
        with ThreadPoolExecutor(max_workers=10) as pool:
            for source, batch, result in pool.map(send, sources):
                latest_batches[source] = batch
                evidence["batches"].append({"source_id": source, "sample": tick, "session_id": producers[source].session_id,
                                            "event_ids": [event["event_id"] for event in batch["events"]],
                                            "source_timestamp": batch["events"][0]["source_timestamp"],
                                            "accepted": result["accepted"], "duplicates": result["duplicates"],
                                            "rejected": result["rejected"], "latest_cursor": result["latest_cursor"]})
        current = api.get("/api/view/state")
        require(current["view"]["mode"] == "replay" and current["view"]["snapshot_id"] == selected_id, "Selected replay view changed")
        require(frozen_view(current) == frozen, "Selected replay assets/KPIs/revision changed during acquisition")
    for source, batch in latest_batches.items():
        snapshot = api.get(f"/api/connectors/{source}/snapshot")
        expected = {event["event_id"] for event in batch["events"]}
        observed = {observation["event_id"] for observation in snapshot["observations"]}
        require(observed == expected, f"Latest accepted observations differ for {source}")
        require(all(o["provenance"]["synthetic"] and o["provenance"]["transport"] == "synthetic_http_ingest" for o in snapshot["observations"]), f"Incorrect HTTP provenance for {source}")
        evidence["sources"][source] = {"cursor": snapshot["cursor"], "observations_sha256": digest(snapshot["observations"]),
                                        "event_ids": sorted(observed), "health": snapshot["health"]}
    timeline = api.get("/api/timeline", limit=100)
    require(not timeline["recording_error"], "Recorder reported an acquisition error")
    new_records = [row for row in timeline["snapshots"] if row["id"] > before_latest]
    require(len(new_records) >= 20, "Expected at least one newer recording for each of twenty accepted source batches")
    after = api.get("/api/view/state")
    require(frozen_view(after) == frozen, "Selected replay changed after source verification")
    evidence.update(selected_after_sha256=digest(frozen_view(after)), new_recordings=new_records,
                    timeline_latest_after=timeline["snapshots"][-1]["id"], passed=True)
    api.post("/api/view", {"mode": "live"})


def action_acceptance(api, report):
    # Avoid closing existing work orders merely to arrange a clean test target.
    target = None
    for asset_id in ("RIDE_COASTER", "RIDE_WHEEL", "POWER_HUB", "WATER_PLANT", "RESTROOMS"):
        asset = api.get(f"/api/assets/{asset_id}")
        if not any(order["status"] == "open" for order in asset["work_orders"]):
            target = asset_id
            break
    require(target is not None, "No eligible asset without an open work order; refusing to reset existing workflows")
    before_audit = api.audit()
    before_orders = asset["work_orders"]
    request = {"action": "dispatch_maintenance", "asset_id": target, "request_id": f"http-acceptance:{uuid.uuid4().hex}"}
    report["action"] = evidence = {"request": request, "audit_before": before_audit, "work_orders_before": before_orders}
    first = api.post("/api/actions", request)
    ack = first["result"]
    evidence["acknowledgement"] = ack
    require(first["idempotency"] == {"request_id": request["request_id"], "replayed": False}, "First unique action was not a new acknowledgement")
    require(ack["synthetic"] is True and ack["physical_effect"] is False and ack["lifecycle"] == "work_order_open", "Acknowledgement does not describe a synthetic open work order")
    after_first_audit = api.audit()
    after_first_orders = api.get(f"/api/assets/{target}")["work_orders"]
    new_audit = [row for row in after_first_audit if row["id"] not in {row["id"] for row in before_audit}]
    new_orders = [row for row in after_first_orders if row["id"] not in {row["id"] for row in before_orders}]
    require([row["id"] for row in new_audit] == [ack["id"]], "Dispatch did not create exactly one audit row (or shared state changed concurrently)")
    require([row["id"] for row in new_orders] == [ack["work_order_id"]], "Dispatch did not create exactly one work order")
    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda _: api.post("/api/actions", request), range(6)))
    require(all(reply["result"] == ack and reply["idempotency"]["replayed"] is True for reply in replies), "Concurrent retries changed the original acknowledgement")
    conflict = api.post("/api/actions", {**request, "action": "add_staff"}, status=409)
    require(conflict["detail"]["code"] == "request_id_conflict", "Expected explicit request-ID collision")
    require(api.audit() == after_first_audit, "Retries/collision wrote new audit rows")
    require(api.get(f"/api/assets/{target}")["work_orders"] == after_first_orders, "Retries/collision changed work orders")
    evidence.update(concurrent_retries=6, all_retry_acknowledgements_equal=True,
                    conflict=conflict, audit_after=after_first_audit,
                    work_orders_after=after_first_orders, passed=True)


def verify_restart(api, previous, report):
    require(previous.get("phase") == "initial" and previous.get("passed") is True, "Restart input must be a successful initial acceptance report")
    request = previous["action"]["request"]
    ack = previous["action"]["acknowledgement"]
    require(request.get("action") == "dispatch_maintenance" and
            request.get("request_id") == ack.get("request_id") and
            request.get("asset_id") == ack.get("asset_id") and
            ack.get("action") == "dispatch_maintenance" and ack.get("synthetic") is True and
            ack.get("physical_effect") is False,
            "Initial evidence does not contain a matching synthetic dispatch request/acknowledgement")
    identity = report["source_identity"]
    original_identity = previous["source_identity"]
    require(identity.get("checked_at") and original_identity.get("checked_at") and
            identity.get("commit") and identity.get("tree"), "Startup/release identity is incomplete")
    require(identity.get("checked_at") != original_identity.get("checked_at"), "Startup source identity timestamp did not change; restart has not been demonstrated")
    require(identity.get("commit") == original_identity.get("commit") and identity.get("tree") == original_identity.get("tree"), "Source release changed between initial and restart phases")
    api.post("/api/view", {"mode": "live"})
    before_audit = api.audit()
    before_orders = api.get(f"/api/assets/{request['asset_id']}")["work_orders"]
    before_scenario = api.get("/api/state")["scenario"]
    require(any(row["id"] == ack["id"] for row in before_audit), "Original acknowledgement audit is unavailable in bounded audit response")
    require(any(order["id"] == ack["work_order_id"] for order in before_orders), "Original work order is unavailable")
    reply = api.post("/api/actions", request)
    require(reply["result"] == ack, "Restart retry did not return the exact original acknowledgement")
    require(reply["idempotency"] == {"request_id": request["request_id"], "replayed": True}, "Restart retry was applied as a new action")
    after_audit = api.audit()
    after_orders = api.get(f"/api/assets/{request['asset_id']}")["work_orders"]
    require(after_audit == before_audit, "Restart retry changed audit")
    require(after_orders == before_orders, "Restart retry changed work orders")
    require(api.get("/api/state")["scenario"] == before_scenario, "Restart retry changed scenario")
    report["restart_verification"] = {"request": request, "acknowledgement": reply["result"],
                                       "idempotency": reply["idempotency"], "audit_before": before_audit,
                                       "audit_after": after_audit, "work_orders_before": before_orders,
                                       "work_orders_after": after_orders, "startup_before": original_identity["checked_at"],
                                       "startup_after": identity["checked_at"], "passed": True,
                                       "scope": "Source startup timestamp changed and durable HTTP receipt survived; no OS process attestation"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-restart", type=Path, metavar="INITIAL_REPORT")
    args = parser.parse_args()
    try:
        parsed = urlsplit(args.url)
        parsed.port
    except ValueError:
        parser.error("--url must be a valid HTTP(S) origin")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        parser.error("--url must be an HTTP(S) origin without credentials, path or query")
    args.url = args.url.rstrip("/")
    if args.output.exists():
        parser.error("--output already exists; preserve prior evidence and choose a new path")
    if args.verify_restart and not args.verify_restart.is_file():
        parser.error("--verify-restart must name an existing initial report")
    return args


def main():
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the evidence destination before any shared-state mutation.
    with args.output.open("x", encoding="utf-8") as output:
        report = {"schema_version": "1.0", "scope": SCOPE, "synthetic": True,
                  "phase": "restart" if args.verify_restart else "initial", "url": args.url,
                  "started_at": utc_now(), "passed": False}
        api = API(args.url)
        original = None
        started = time.monotonic()
        try:
            health = api.get("/api/health")
            require(health.get("synthetic") is True, "Health is not explicitly synthetic")
            report["source_identity"] = health["source_identity"]
            original = baseline(api)
            report["baseline"] = original
            api.post("/api/view", {"mode": "live"})
            if args.verify_restart:
                raw = args.verify_restart.read_bytes()
                report["initial_evidence"] = {"path": str(args.verify_restart), "sha256": hashlib.sha256(raw).hexdigest()}
                previous = json.loads(raw)
                require(previous.get("url") == args.url, "Initial report targets a different gateway origin")
                verify_restart(api, previous, report)
            else:
                producer_replay_acceptance(api, report)
                action_acceptance(api, report)
            report["passed"] = True
        except Exception as exc:
            report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            if not restore(api, original, report):
                report["passed"] = False
            api.client.close()
            report.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - started, 3))
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
    print(json.dumps({"passed": report["passed"], "phase": report["phase"], "output": str(args.output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
