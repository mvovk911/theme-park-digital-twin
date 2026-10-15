"""Source boundary: adapters supply events; they do not update application assets."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import copy
from .catalog import ConnectorSpec, get_path


@dataclass(frozen=True)
class SourceBatch:
    events: list[dict]
    cursor: str | None


class SourceAdapter(Protocol):
    adapter_id: str
    synthetic: bool
    transport: str

    def snapshot(self, context: dict) -> SourceBatch:
        """Return a complete current source sample and resumable source cursor."""
        ...

    def poll(self, after: str | None, context: dict) -> SourceBatch:
        """Return available source events after the supplied opaque source cursor."""
        ...


class SyntheticDomainAdapter:
    """One isolated, replaceable in-process adapter instance per domain.

    The source context is the deterministic park simulator. No industrial or
    enterprise protocol server is implemented or contacted by this adapter.
    """
    synthetic = True
    transport = "in_process_simulation"

    def __init__(self, spec: ConnectorSpec):
        self.spec = spec
        self.adapter_id = f"synthetic.{spec.id}.v1"

    def snapshot(self, context: dict):
        assets = {asset["id"]: asset for asset in context["assets"]}
        tick = str(context["tick"])
        events = []
        for mapping in self.spec.mappings:
            # A malformed/missing source field is represented as a rejected event
            # instead of being silently replaced by zero or a default value.
            try:
                value = copy.deepcopy(get_path(assets[mapping.asset_id], mapping.metric))
            except KeyError:
                value = None
            events.append({"event_id": f"{tick}:{mapping.source_asset_id}:{mapping.metric}",
                           "source_asset_id": mapping.source_asset_id, "metric": mapping.metric,
                           "value": value, "unit": mapping.unit,
                           "source_timestamp": context["timestamp"]})
        return SourceBatch(events, tick)

    def poll(self, after, context):
        if after == str(context["tick"]):
            return SourceBatch([], after)
        return self.snapshot(context)
