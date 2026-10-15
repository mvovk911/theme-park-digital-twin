"""Presentation-motion policy for accepted source data, independent of GPU APIs."""

from __future__ import annotations


def ride_motion_policy(
    assets: dict, snapshot_fresh: bool, replay: bool = False
) -> dict[str, dict]:
    result = {}
    for ident in ("RIDE_COASTER", "RIDE_WHEEL"):
        asset = assets.get(ident, {})
        quality = (
            asset.get("data_quality", {})
            .get("fields", {})
            .get("status", {})
            .get("status", "unknown")
        )
        if replay:
            reason = "recorded_view"
        elif not snapshot_fresh:
            reason = "snapshot_stale_or_missing"
        elif quality != "good":
            reason = "status_source_" + quality
        elif asset.get("status") not in {"operational", "warning"}:
            reason = "ride_" + asset.get("status", "unknown")
        else:
            reason = "current_operating_status"
        result[ident] = {
            "advance": reason == "current_operating_status",
            "reason": reason,
            "status_quality": quality,
        }
    return result
