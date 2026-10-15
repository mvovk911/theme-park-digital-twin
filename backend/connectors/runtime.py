"""Polling, accepted-event ingestion, provenance and health for domain connectors."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import threading
from .adapters import SyntheticDomainAdapter
from .catalog import default_catalog, validate_catalog
from .store import EventStore
from .validation import EventError, parse_timestamp, validate_event


def now_utc():
    return datetime.now(timezone.utc)


class ConnectorRuntime:
    def __init__(self, known_assets, specs=None, adapters=None, clock=now_utc, capacity=2048):
        self.lock = threading.RLock()
        self.clock = clock
        self.known_assets = set(known_assets)
        specs = default_catalog() if specs is None else specs
        validate_catalog(specs, self.known_assets)
        self.specs = {spec.id: spec for spec in specs}
        self.adapters = {spec.id: SyntheticDomainAdapter(spec) for spec in specs}
        if adapters:
            if not set(adapters) <= set(self.specs):
                raise ValueError("Adapter has no connector specification")
            self.adapters.update(adapters)
        self.stores = {spec.id: EventStore(capacity) for spec in specs}
        self.mapping_indexes = {spec.id: {(m.source_asset_id, m.metric): m for m in spec.mappings} for spec in specs}
        self.modes = {spec.id: "live" for spec in specs}
        self.source_cursors = {spec.id: None for spec in specs}
        self.counters = {spec.id: {"accepted": 0, "rejected": 0, "duplicates": 0, "poll_failures": 0} for spec in specs}
        self.errors = {spec.id: None for spec in specs}
        self.last_attempts = {spec.id: None for spec in specs}
        self.last_context_tick = None

    def require_source(self, source_id):
        if source_id not in self.specs:
            raise KeyError(source_id)

    def refresh(self, context):
        """Poll every live adapter; a source cursor avoids repeated simulator ticks."""
        with self.lock:
            if self.last_context_tick is not None and context["tick"] < self.last_context_tick:
                return
            self.last_context_tick = context["tick"]
            for source_id, adapter in self.adapters.items():
                if self.modes[source_id] != "live":
                    continue
                self.last_attempts[source_id] = self.clock().isoformat(timespec="milliseconds")
                try:
                    cursor = self.source_cursors[source_id]
                    batch = adapter.snapshot(context) if cursor is None else adapter.poll(cursor, context)
                    if len(batch.events) > 1000:
                        raise ValueError("Adapter batch exceeds 1000 events")
                    if batch.events:
                        self._ingest(source_id, batch.events)
                    self.source_cursors[source_id] = batch.cursor
                except Exception:
                    # Never put provider exceptions (which can include credentials)
                    # into public health payloads or observation provenance.
                    self.counters[source_id]["poll_failures"] += 1
                    self.errors[source_id] = {"code": "adapter_poll_failed", "message": "Source adapter poll failed"}

    def _ingest(self, source_id, events, transport=None):
        adapter = self.adapters[source_id]
        result = {"source_id": source_id, "accepted": 0, "rejected": 0, "duplicates": 0, "errors": []}
        now = self.clock()
        for index, event in enumerate(events):
            try:
                mapping, timestamp = validate_event(event, self.mapping_indexes[source_id], self.known_assets, now)
                provenance = {"adapter": adapter.adapter_id, "synthetic": adapter.synthetic,
                              "transport": transport or adapter.transport, "source_field": mapping.metric,
                              "planned_protocol": self.specs[source_id].planned_protocol}
                accepted = self.stores[source_id].accept(source_id, event, mapping, timestamp, now, provenance)
                result["duplicates" if accepted is None else "accepted"] += 1
            except EventError as exc:
                result["rejected"] += 1
                result["errors"].append({"index": index, "code": exc.code, "message": exc.message})
        for field in ("accepted", "rejected", "duplicates"):
            self.counters[source_id][field] += result[field]
        if result["rejected"]:
            self.errors[source_id] = {"code": "rejected_events", "message": f"{result['rejected']} events rejected in last batch"}
        elif result["accepted"]:
            self.errors[source_id] = None
        result["latest_cursor"] = self.stores[source_id].poll(limit=1)["latest_cursor"]
        result["latest_decision_cursor"] = self.stores[source_id].poll_decisions(limit=1)["latest_decision_cursor"]
        return result

    def ingest_demo(self, source_id, events):
        with self.lock:
            self.require_source(source_id)
            if not self.adapters[source_id].synthetic:
                raise EventError("not_synthetic", "Demo ingestion is disabled for a non-synthetic adapter")
            if self.modes[source_id] != "paused":
                raise EventError("source_not_paused", "Pause this synthetic connector before injecting demo events")
            if not isinstance(events, list) or not 1 <= len(events) <= 500:
                raise EventError("invalid_batch_size", "Provide between 1 and 500 events")
            return self._ingest(source_id, events, transport="synthetic_http_ingest")

    def set_simulation_mode(self, source_id, mode):
        with self.lock:
            self.require_source(source_id)
            if not self.adapters[source_id].synthetic:
                raise EventError("not_synthetic", "Simulation controls are disabled for a non-synthetic adapter")
            if mode not in {"live", "paused", "offline"}:
                raise EventError("invalid_mode", "Mode must be live, paused or offline")
            self.modes[source_id] = mode
            return self.health(source_id)

    def quality(self, source_id, observation, now=None):
        now = self.clock() if now is None else now
        elapsed = (now - parse_timestamp(observation["source_timestamp"])).total_seconds()
        age = max(0.0, elapsed)
        threshold = self.specs[source_id].stale_after_seconds
        reasons = []
        if elapsed < 0:
            reasons.append("source_clock_ahead")
        if age > threshold:
            reasons.append("source_timestamp_stale")
        if self.modes[source_id] == "offline":
            reasons.append("source_offline")
        if self.errors[source_id]:
            reasons.append(self.errors[source_id]["code"])
        status = "stale" if age > threshold else "uncertain" if reasons else "good"
        return {"status": status, "age_seconds": round(age, 3), "stale_after_seconds": threshold, "reasons": reasons}

    def observations(self, source_id=None, asset_id=None, limit=1000):
        with self.lock:
            if source_id is not None:
                self.require_source(source_id)
            if asset_id is not None and asset_id not in self.known_assets:
                raise KeyError(asset_id)
            now = self.clock()
            result = []
            for ident, store in self.stores.items():
                if source_id is not None and ident != source_id:
                    continue
                for observation in store.latest.values():
                    if asset_id is not None and observation["asset_id"] != asset_id:
                        continue
                    record = copy.deepcopy(observation)
                    record["quality"] = self.quality(ident, record, now)
                    result.append(record)
            result.sort(key=lambda o: (o["source_id"], o["asset_id"], o["metric"]))
            return {"schema_version": "1.0", "observations": result[:limit], "total": len(result), "truncated": len(result) > limit}

    def source_snapshot(self, source_id):
        """Copy source values and their accepted-event cursor atomically."""
        with self.lock:
            self.require_source(source_id)
            observations = self.observations(source_id=source_id)
            health = self.health(source_id)
            return {**observations, "health": health, "cursor": health["latest_cursor"]}

    def health(self, source_id):
        with self.lock:
            self.require_source(source_id)
            store = self.stores[source_id]
            qualities = [self.quality(source_id, observation) for observation in store.latest.values()]
            missing = len(self.specs[source_id].mappings) - len(store.latest)
            stale = sum(q["status"] == "stale" for q in qualities)
            uncertain = sum(q["status"] == "uncertain" for q in qualities)
            mode = self.modes[source_id]
            if mode == "offline":
                status = "offline"
            elif self.errors[source_id] and self.errors[source_id]["code"] == "adapter_poll_failed":
                status = "error"
            elif not qualities:
                status = "unknown"
            elif stale:
                status = "stale"
            elif self.errors[source_id] or missing or uncertain:
                status = "degraded"
            elif mode == "paused":
                status = "paused"
            else:
                status = "healthy"
            return {"source_id": source_id, "status": status, "mode": mode,
                    "synthetic": self.adapters[source_id].synthetic,
                    "last_source_timestamp": max((o["source_timestamp"] for o in store.latest.values()), default=None),
                    "last_ingested_at": max((o["ingested_at"] for o in store.latest.values()), default=None),
                    "last_poll_attempt_at": self.last_attempts[source_id], "last_error": copy.deepcopy(self.errors[source_id]),
                    "freshness": {"max_age_seconds": max((q["age_seconds"] for q in qualities), default=None),
                                  "stale_after_seconds": self.specs[source_id].stale_after_seconds,
                                  "stale_metrics": stale, "missing_metrics": missing, "uncertain_metrics": uncertain},
                    "counters": dict(self.counters[source_id]), "latest_cursor": f"{store.epoch}:{store.sequence}"}

    def catalog(self, source_id=None):
        with self.lock:
            if source_id is not None:
                self.require_source(source_id)
            result = []
            for ident, spec in self.specs.items():
                if source_id is not None and source_id != ident:
                    continue
                adapter = self.adapters[ident]
                result.append({"id": ident, "name": spec.name, "schema_version": "1.0",
                               "synthetic": adapter.synthetic, "adapter": adapter.adapter_id,
                               "transport": adapter.transport, "planned_protocol": spec.planned_protocol,
                               "asset_ids": list(spec.asset_ids), "stale_after_seconds": spec.stale_after_seconds,
                               "capabilities": {"snapshot": True, "event_poll": True, "historical_replay": False,
                                                "demo_ingest": adapter.synthetic, "simulation_controls": adapter.synthetic,
                                                "physical_control": False},
                               "mappings": [m.as_dict() for m in spec.mappings], "health": self.health(ident)})
            return result[0] if source_id is not None else {"schema_version": "1.0", "connectors": result}

    def events(self, source_id, after=None, limit=100):
        with self.lock:
            self.require_source(source_id)
            result = self.stores[source_id].poll(after, limit)
            for observation in result["events"]:
                observation["quality"] = self.quality(source_id, observation)
            return {"schema_version": "1.0", "source_id": source_id, **result}

    def decisions(self, source_id, after=None, limit=100):
        with self.lock:
            self.require_source(source_id)
            result = self.stores[source_id].poll_decisions(after, limit)
            for decision in result["decisions"]:
                observation = decision["observation"]
                observation["quality"] = self.quality(source_id, observation)
            return {"schema_version": "1.0", "source_id": source_id, **result}
