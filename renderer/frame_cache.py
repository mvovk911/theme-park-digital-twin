"""Publish image bytes and their immutable provenance as one atomic frame."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import threading
import time
from typing import Callable


def timestamp_age(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
        return max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())
    except (ValueError, TypeError):
        return None


class FrameCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._bytes = b""
        self._metadata: dict = {}
        self._published_at = 0.0

    def publish(self, image: bytes, metadata: dict) -> None:
        if not image:
            raise ValueError("A published frame must contain image bytes")
        with self._lock:
            if self._metadata and metadata["frame"] <= self._metadata["frame"]:
                raise ValueError("Frame numbers must increase within a render process")
            self._bytes = bytes(image)
            self._metadata = copy.deepcopy(metadata)
            self._metadata.setdefault(
                "rendered_at",
                datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            )
            self._published_at = self._clock()

    def read(self) -> tuple[bytes, dict]:
        with self._lock:
            metadata = copy.deepcopy(self._metadata)
            if metadata:
                metadata["frame_age_seconds"] = round(
                    max(0.0, self._clock() - self._published_at), 3
                )
                metadata["source_age_seconds"] = timestamp_age(
                    metadata.get("source_timestamp")
                )
            return self._bytes, metadata


def response_headers(metadata: dict, ready: bool) -> dict[str, str]:
    fields = {
        "X-Frame-Number": metadata.get("frame"),
        "X-Frame-Rendered-At": metadata.get("rendered_at"),
        "X-Frame-Age-Seconds": metadata.get("frame_age_seconds"),
        "X-Source-Tick": metadata.get("source_tick"),
        "X-Source-Timestamp": metadata.get("source_timestamp"),
        "X-Source-Age-Seconds": metadata.get("source_age_seconds"),
        "X-View-Mode": metadata.get("view_mode", "live"),
        "X-View-Snapshot-Id": metadata.get("snapshot_id"),
        "X-Scene-Revision": metadata.get("scene_revision"),
        "X-Pose-Source": metadata.get("pose_source", "live"),
        "X-Renderer-Ready": str(ready).lower(),
    }
    return {
        "Cache-Control": "no-store",
        **{key: str(value) for key, value in fields.items() if value is not None},
    }
