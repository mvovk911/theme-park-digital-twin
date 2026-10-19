"""Read-only Open-Meteo preview. Weather-model output is not a park sensor.

No coordinates, requests or values are injected into the canonical synthetic twin.
The only network destination is the fixed public forecast endpoint. Commercial
deployment requires the provider's appropriate service agreement/configuration.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FIELDS = {
    "temperature_2m": ("temperature_c", "°C", "Cel", -90, 65),
    "apparent_temperature": ("apparent_temperature_c", "°C", "Cel", -110, 90),
    "wind_speed_10m": ("wind_speed_mps", "m/s", "m/s", 0, 150),
    "wind_gusts_10m": ("wind_gust_mps", "m/s", "m/s", 0, 200),
    "precipitation": ("precipitation_mm", "mm", "mm", 0, 1000),
}
MAX_RESPONSE_BYTES = 128 * 1024


class WeatherError(ValueError):
    """An unusable observation; callers should not fill gaps with good values."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WeatherError("Weather provider redirected; preview was not followed")


def coordinates(latitude, longitude):
    for value, low, high in [(latitude, -90, 90), (longitude, -180, 180)]:
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise WeatherError("Coordinates must be finite WGS84 latitude/longitude")
    return round(float(latitude), 5), round(float(longitude), 5)


def query_url(latitude, longitude):
    latitude, longitude = coordinates(latitude, longitude)
    return ENDPOINT + "?" + urlencode({"latitude": latitude, "longitude": longitude,
        "current": ",".join(FIELDS), "hourly": ",".join(FIELDS),
        "forecast_hours": 12, "timezone": "GMT", "timeformat": "unixtime",
        "temperature_unit": "celsius", "wind_speed_unit": "ms", "precipitation_unit": "mm"})


def _time(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise WeatherError("Provider did not return a finite Unix valid time")
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise WeatherError("Provider valid time is outside the supported range") from None


def _fields(values, units, interval_seconds):
    output = {}
    for source, (name, expected, unit, low, high) in FIELDS.items():
        value = values.get(source)
        reason = None
        if units.get(source) != expected:
            reason = "unexpected_unit"
        elif value is None:
            reason = "missing_value"
        elif type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            reason = "invalid_value"
        aggregation = "preceding_window_sum" if source == "precipitation" else "preceding_window_max" if source == "wind_gusts_10m" else "instant"
        output[name] = {"value": None if reason else float(value), "unit": unit,
                        "quality": "unknown" if reason else "available", "reason": reason,
                        "source_field": source, "temporal_aggregation": aggregation,
                        "aggregation_window_seconds": 0 if aggregation == "instant" else interval_seconds}
    return output


def normalize(payload, latitude, longitude, retrieved_at):
    latitude, longitude = coordinates(latitude, longitude)
    if not isinstance(payload, dict) or retrieved_at.tzinfo is None:
        raise WeatherError("Weather payload and retrieval time are invalid")
    current, hourly = payload.get("current"), payload.get("hourly")
    if not isinstance(current, dict) or not isinstance(hourly, dict):
        raise WeatherError("Weather response lacks current/hourly objects")
    if payload.get("utc_offset_seconds") != 0:
        raise WeatherError("Weather response did not honor UTC")
    interval = current.get("interval")
    if type(interval) is not int or not 1 <= interval <= 3600:
        raise WeatherError("Current weather aggregation interval is missing or invalid")
    times = hourly.get("time")
    if not isinstance(times, list) or not 1 <= len(times) <= 12:
        raise WeatherError("Weather forecast must have 1–12 time steps")
    for source in FIELDS:
        if not isinstance(hourly.get(source), list) or len(hourly[source]) != len(times):
            raise WeatherError("Weather forecast arrays have inconsistent lengths")
    if any(type(t) not in (int, float) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise WeatherError("Weather forecast valid times must increase")
    if any(b - a != 3600 for a, b in zip(times, times[1:])):
        raise WeatherError("Hourly weather forecast must use hourly spacing")
    current_time = _time(current.get("time"))
    result = {"adapter": "open_meteo.preview.v1", "external": True, "synthetic": False,
        "mutates_live_state": False, "authoritative_for_park": False,
        "requested_location": {"latitude": latitude, "longitude": longitude},
        "provider_grid": {"latitude": payload.get("latitude"), "longitude": payload.get("longitude"), "elevation_m": payload.get("elevation")},
        "retrieved_at": retrieved_at.isoformat(), "forecast_issued_at": None,
        "current": {"valid_at": current_time, "interval_seconds": interval,
                    "values": _fields(current, payload.get("current_units", {}), interval)},
        "hourly": [{"valid_at": _time(t), "interval_seconds": 3600,
                    "values": _fields({key: hourly[key][i] for key in FIELDS}, payload.get("hourly_units", {}), 3600)} for i, t in enumerate(times)],
        "provenance": {"provider": "Open-Meteo", "source_type": "numerical_weather_model",
            "documentation": "https://open-meteo.com/en/docs", "attribution": "Weather data by Open-Meteo.com, CC BY 4.0",
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()},
        "limits": ["Preview coordinates are not a configured park location.",
            "Current values are weather-model estimates, not a local wind mast or safety sensor.",
            "Retrieval time is not forecast issue time; this response does not expose an issue timestamp.",
            "No ride limits, lightning detection, calibration or command authority are supplied.",
            "The public API is for noncommercial use; production must use an appropriate provider agreement."]}
    return with_age(result, retrieved_at, cached=False)


def with_age(result, now, *, cached):
    result = copy.deepcopy(result)
    observed = datetime.fromisoformat(result["current"]["valid_at"])
    age = (now - observed).total_seconds()
    reasons = []
    if age < -300:
        reasons.append("current_valid_time_in_future")
    if age > 2700:
        reasons.append("current_estimate_older_than_45_minutes")
    if any(value["quality"] != "available" for value in result["current"]["values"].values()):
        reasons.append("current_fields_missing_or_invalid")
    forecast_times = [datetime.fromisoformat(step["valid_at"]) for step in result["hourly"]]
    if forecast_times[-1] <= now:
        reasons.append("hourly_forecast_has_no_future_coverage")
    if forecast_times[0] > now + timedelta(hours=1):
        reasons.append("hourly_forecast_starts_more_than_one_hour_ahead")
    if any(value["quality"] != "available" for step in result["hourly"] for value in step["values"].values()):
        reasons.append("hourly_fields_missing_or_invalid")
    result["forecast_coverage"] = {"from": result["hourly"][0]["valid_at"],
        "through": result["hourly"][-1]["valid_at"],
        "future_steps": sum(t > now for t in forecast_times),
        "requested_steps": 12, "returned_steps": len(forecast_times)}
    if len(forecast_times) < 12:
        reasons.append("hourly_forecast_is_partial")
    result["quality"] = {"status": "review_required" if reasons else "available",
        "current_age_seconds": round(age, 3), "reasons": reasons,
        "freshness_policy": "preview-only: current valid time within -5 to +45 minutes of retrieval; not a provider accuracy guarantee"}
    result["cached"] = cached
    result["checked_at"] = now.isoformat()
    return result


def download(url):
    with build_opener(NoRedirects()).open(Request(url, headers={"User-Agent": "AsterPark-OpenResearchPreview/1.0"}), timeout=8) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise WeatherError("Weather response exceeds preview size limit")
        return json.loads(body)


class WeatherPreview:
    def __init__(self, fetch=download, clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic):
        self.fetch, self.clock, self.monotonic = fetch, clock, monotonic
        self.lock = threading.Lock()
        self.cache = {}

    def preview(self, latitude, longitude):
        key = coordinates(latitude, longitude)
        with self.lock:
            now = self.clock()
            entry = self.cache.get(key)
            if entry and self.monotonic() - entry[0] < 900:
                return with_age(entry[1], now, cached=True)
            payload = self.fetch(query_url(*key))
            result = normalize(payload, *key, self.clock())
            if len(self.cache) >= 32 and key not in self.cache:
                del self.cache[min(self.cache, key=lambda k: self.cache[k][0])]
            self.cache[key] = (self.monotonic(), result)
            return result
