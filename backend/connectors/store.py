"""Bounded accepted-event storage and an independent ingestion decision journal."""
from __future__ import annotations
from collections import OrderedDict, deque
import copy
import hashlib
import json
import uuid
from .validation import EventError, parse_timestamp


def _window(records, after, limit, epoch, latest, sequence_field):
    minimum = records[0][sequence_field] - 1 if records else latest
    if after is None:
        sequence = minimum
    else:
        try:
            cursor_epoch, raw_sequence = after.split(":", 1)
            sequence = int(raw_sequence)
        except (ValueError, AttributeError):
            raise EventError("invalid_cursor", "Use a cursor returned by this connector stream")
        if cursor_epoch != epoch:
            if cursor_epoch.split(".", 1)[0] == epoch.split(".", 1)[0]:
                raise EventError("invalid_cursor", "Accepted-event and decision cursors are not interchangeable")
            raise EventError("cursor_expired", "Connector restarted; request a fresh snapshot/cursor")
        if sequence < minimum:
            raise EventError("cursor_expired", "Cursor is older than this stream's retained entries")
        if sequence < 0 or sequence > latest:
            raise EventError("invalid_cursor", "Cursor is outside the available stream range")
    selected = [e for e in records if e[sequence_field] > sequence][:limit]
    end = selected[-1][sequence_field] if selected else sequence
    return copy.deepcopy(selected), f"{epoch}:{end}", f"{epoch}:{latest}", end < latest


class EventStore:
    """Runtime calls under its lock; accepted events and decisions have separate cursors.

    Retains capacity accepted events and capacity decisions per source, latest
    values per metric, and capacity*2 accepted-event deduplication keys.
    """
    def __init__(self, capacity=2048):
        if capacity < 1:
            raise ValueError("Event capacity must be positive")
        self.capacity = capacity
        self.epoch = uuid.uuid4().hex[:12]
        self.events = deque(maxlen=capacity)
        self.decisions = deque(maxlen=capacity)
        self.dedup = OrderedDict()
        self.latest = {}
        self.sequence = 0
        self.decision_sequence = 0

    def _decision(self, observation, applied, reason):
        self.decision_sequence += 1
        self.decisions.append({"decision_sequence": self.decision_sequence, "applied": applied,
                               "reason": reason, "decided_at": observation["ingested_at"],
                               "observation": copy.deepcopy(observation)})

    def accept(self, source_id, event, mapping, timestamp, ingested_at, provenance):
        observation = {"schema_version": "1.0", "observation_id": hashlib.sha256(f"{source_id}:{event['event_id']}".encode()).hexdigest()[:24],
                       "event_id": event["event_id"], "source_id": source_id, "source_asset_id": mapping.source_asset_id,
                       "asset_id": mapping.asset_id, "metric": mapping.metric, "value": copy.deepcopy(event["value"]),
                       "unit": mapping.unit, "source_timestamp": timestamp.isoformat(timespec="microseconds"),
                       "ingested_at": ingested_at.isoformat(timespec="milliseconds"), "sequence": None,
                       "provenance": copy.deepcopy(provenance), "authoritative": mapping.authoritative}
        fingerprint = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
        previous = self.dedup.get(event["event_id"])
        if previous is not None:
            if previous != fingerprint:
                self._decision(observation, False, "duplicate_event_conflict")
                raise EventError("duplicate_event_conflict", "event_id was already accepted with different content")
            self._decision(observation, False, "duplicate")
            return None
        key = (mapping.source_asset_id, mapping.metric)
        latest = self.latest.get(key)
        if latest and timestamp < parse_timestamp(latest["source_timestamp"]):
            self._decision(observation, False, "out_of_order")
            raise EventError("out_of_order", "Source timestamp precedes the last accepted value for this metric")
        self.sequence += 1
        observation["sequence"] = self.sequence
        self.latest[key] = observation
        self.events.append(observation)
        self.dedup[event["event_id"]] = fingerprint
        while len(self.dedup) > self.capacity * 2:
            self.dedup.popitem(last=False)
        self._decision(observation, True, "accepted")
        return observation

    def poll(self, after=None, limit=100):
        entries, next_cursor, latest_cursor, more = _window(self.events, after, limit, self.epoch, self.sequence, "sequence")
        return {"events": entries, "next_cursor": next_cursor, "latest_cursor": latest_cursor,
                "has_more": more, "retention_events": self.capacity}

    def poll_decisions(self, after=None, limit=100):
        entries, next_cursor, latest_cursor, more = _window(self.decisions, after, limit, self.epoch + ".decisions",
                                                           self.decision_sequence, "decision_sequence")
        return {"decisions": entries, "next_decision_cursor": next_cursor, "latest_decision_cursor": latest_cursor,
                "has_more": more, "retention_decisions": self.capacity}
