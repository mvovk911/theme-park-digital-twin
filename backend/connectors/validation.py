"""Validation at the accepted-event boundary; invalid values never enter the store."""
from __future__ import annotations
from datetime import datetime, timezone
import math
from .catalog import METRICS

EVENT_FIELDS = {"event_id", "source_asset_id", "metric", "value", "unit", "source_timestamp"}


class EventError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def parse_timestamp(value):
    if not isinstance(value, str):
        raise EventError("invalid_timestamp", "source_timestamp must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EventError("invalid_timestamp", "source_timestamp must be an ISO 8601 timestamp with timezone")
    if parsed.tzinfo is None:
        raise EventError("invalid_timestamp", "Naive source timestamps are not accepted")
    return parsed.astimezone(timezone.utc)


def validate_event(event, mapping_index, known_assets, now):
    if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
        raise EventError("invalid_event_shape", "Event fields must match the version 1 contract")
    if not isinstance(event["event_id"], str) or not 1 <= len(event["event_id"]) <= 256:
        raise EventError("invalid_event_id", "event_id must contain 1–256 characters")
    if not isinstance(event["source_asset_id"], str) or not isinstance(event["metric"], str):
        raise EventError("unknown_mapping", "Source asset and metric must identify a declared mapping")
    mapping = mapping_index.get((event["source_asset_id"], event["metric"]))
    if mapping is None:
        raise EventError("unknown_mapping", "Source asset and metric do not identify a declared mapping")
    if event["unit"] != mapping.unit:
        raise EventError("unit_mismatch", f"Expected canonical unit {mapping.unit}")
    definition = METRICS[mapping.metric]
    value = event["value"]
    if definition.kind in {"number", "integer"}:
        try:
            finite_number = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        except OverflowError:
            finite_number = False
        if not finite_number:
            raise EventError("invalid_type", "Expected a finite numeric value")
        if definition.kind == "integer" and not isinstance(value, int):
            raise EventError("invalid_type", "Expected an integer value")
        if definition.minimum is not None and value < definition.minimum:
            raise EventError("out_of_range", "Value is below the declared minimum")
        if definition.maximum is not None and value > definition.maximum:
            raise EventError("out_of_range", "Value exceeds the declared maximum")
    elif definition.kind in {"string", "scene_path"}:
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            raise EventError("invalid_type", "Expected a nonempty string of at most 2048 characters")
        if definition.choices and value not in definition.choices:
            raise EventError("invalid_enum", "Value is not in the declared enumeration")
        if definition.kind == "scene_path" and value != f"/World/Park/{mapping.asset_id}":
            raise EventError("invalid_scene_path", "Scene path must match the canonical asset identity")
    elif definition.kind in {"strings", "assets"}:
        if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in value):
            raise EventError("invalid_type", "Expected a bounded list of strings")
        if definition.kind == "assets" and not set(value) <= known_assets:
            raise EventError("unknown_dependency", "Dependency does not exist in the asset registry")
    timestamp = parse_timestamp(event["source_timestamp"])
    if (timestamp - now).total_seconds() > 5:
        raise EventError("future_timestamp", "Source timestamp exceeds the five-second clock-skew allowance")
    return mapping, timestamp
