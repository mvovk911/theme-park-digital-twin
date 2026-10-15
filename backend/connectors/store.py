"""Bounded in-memory accepted-event store with explicit duplicate/order semantics."""
from __future__ import annotations
from collections import OrderedDict, deque
import copy
import hashlib
import json
import uuid
from .validation import EventError, parse_timestamp


class EventStore:
    """Runtime calls this under its lock. Cursors are scoped to this store epoch.

    Retains at most capacity events per source, latest values per configured
    metric, and capacity*2 deduplication keys. Restart requires a fresh snapshot.
    """
    def __init__(self, capacity=2048):
        if capacity < 1:
            raise ValueError("Event capacity must be positive")
        self.capacity = capacity
        self.epoch = uuid.uuid4().hex[:12]
        self.events = deque(maxlen=capacity)
        self.dedup = OrderedDict()
        self.latest = {}
        self.sequence = 0

    def accept(self, source_id, event, mapping, timestamp, ingested_at, provenance):
        fingerprint = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
        previous = self.dedup.get(event["event_id"])
        if previous is not None:
            if previous != fingerprint:
                raise EventError("duplicate_event_conflict", "event_id was already accepted with different content")
            return None
        key = (mapping.source_asset_id, mapping.metric)
        latest = self.latest.get(key)
        if latest and timestamp < parse_timestamp(latest["source_timestamp"]):
            raise EventError("out_of_order", "Source timestamp precedes the last accepted value for this metric")
        self.sequence += 1
        observation = {"schema_version": "1.0", "observation_id": hashlib.sha256(f"{source_id}:{event['event_id']}".encode()).hexdigest()[:24],
                       "event_id": event["event_id"], "source_id": source_id, "source_asset_id": mapping.source_asset_id,
                       "asset_id": mapping.asset_id, "metric": mapping.metric, "value": copy.deepcopy(event["value"]),
                       "unit": mapping.unit, "source_timestamp": timestamp.isoformat(timespec="microseconds"),
                       "ingested_at": ingested_at.isoformat(timespec="milliseconds"), "sequence": self.sequence,
                       "provenance": copy.deepcopy(provenance), "authoritative": mapping.authoritative}
        self.latest[key] = observation
        self.events.append(observation)
        self.dedup[event["event_id"]] = fingerprint
        while len(self.dedup) > self.capacity * 2:
            self.dedup.popitem(last=False)
        return observation

    def poll(self, after=None, limit=100):
        minimum = self.events[0]["sequence"] - 1 if self.events else self.sequence
        if after is None:
            sequence = minimum
        else:
            try:
                epoch, raw_sequence = after.split(":", 1)
                sequence = int(raw_sequence)
            except (ValueError, AttributeError):
                raise EventError("invalid_cursor", "Use a cursor returned by this connector")
            if epoch != self.epoch:
                raise EventError("cursor_expired", "Connector restarted; request a fresh snapshot/cursor")
            if sequence < minimum:
                raise EventError("cursor_expired", "Cursor is older than retained events; request a fresh snapshot")
            if sequence < 0 or sequence > self.sequence:
                raise EventError("invalid_cursor", "Cursor is outside the available event range")
        selected = [e for e in self.events if e["sequence"] > sequence][:limit]
        end = selected[-1]["sequence"] if selected else sequence
        return {"events": copy.deepcopy(selected), "next_cursor": f"{self.epoch}:{end}",
                "latest_cursor": f"{self.epoch}:{self.sequence}", "has_more": end < self.sequence,
                "retention_events": self.capacity}
