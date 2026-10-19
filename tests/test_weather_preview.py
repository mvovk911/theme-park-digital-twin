"""External preview must preserve missing values, units, time and separation."""
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.integrations.weather import FIELDS, WeatherError, WeatherPreview, normalize, query_url

NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)


def fixture():
    values = dict(zip(FIELDS, [12, 10, 4, 7, 0]))
    units = {key: spec[1] for key, spec in FIELDS.items()}
    return {"latitude": 48.2, "longitude": 16.4, "elevation": 190,
        "utc_offset_seconds": 0, "current_units": units, "hourly_units": units,
        "current": {"time": NOW.timestamp(), "interval": 900, **values},
        "hourly": {"time": [NOW.timestamp()+i*3600 for i in range(12)],
                   **{key: [value]*12 for key, value in values.items()}}}


def test_preview_has_external_model_provenance_not_sensor_or_forecast_issue_time():
    result = normalize(fixture(), 48.2082, 16.3738, NOW)
    assert result["synthetic"] is False and result["external"] is True
    assert result["mutates_live_state"] is False and result["authoritative_for_park"] is False
    assert result["provenance"]["source_type"] == "numerical_weather_model"
    assert result["forecast_issued_at"] is None
    assert result["current"]["values"]["wind_speed_mps"]["value"] == 4
    assert result["quality"]["status"] == "available"
    assert result["current"]["values"]["precipitation_mm"]["aggregation_window_seconds"] == 900
    assert result["hourly"][0]["values"]["precipitation_mm"]["aggregation_window_seconds"] == 3600
    assert result["current"]["values"]["wind_gust_mps"]["temporal_aggregation"] == "preceding_window_max"
    assert result["current"]["values"]["temperature_c"]["temporal_aggregation"] == "instant"


def test_hourly_coverage_and_missing_values_cannot_look_current():
    raw = fixture()
    raw["hourly"]["time"] = [t-24*3600 for t in raw["hourly"]["time"]]
    result = normalize(raw, 48.2, 16.4, NOW)
    assert result["quality"]["status"] == "review_required"
    assert "hourly_forecast_has_no_future_coverage" in result["quality"]["reasons"]
    assert result["forecast_coverage"]["future_steps"] == 0
    raw = fixture();raw["hourly"]["precipitation"][1] = None
    assert "hourly_fields_missing_or_invalid" in normalize(raw, 48.2, 16.4, NOW)["quality"]["reasons"]


def test_unknown_aggregation_interval_is_rejected():
    raw = fixture();del raw["current"]["interval"]
    with pytest.raises(WeatherError, match="interval"):
        normalize(raw, 48.2, 16.4, NOW)


@pytest.mark.parametrize("value,unit,reason", [(None, "°C", "missing_value"), (True, "°C", "invalid_value"),
    (95, "°C", "invalid_value"), (12, "°F", "unexpected_unit")])
def test_bad_current_fields_remain_unknown_without_filling(value, unit, reason):
    raw = fixture();raw["current"]["temperature_2m"] = value
    raw["current_units"] = {**raw["current_units"], "temperature_2m": unit}
    result = normalize(raw, 48.2, 16.4, NOW)
    field = result["current"]["values"]["temperature_c"]
    assert field["value"] is None and field["reason"] == reason
    assert result["quality"]["status"] == "review_required"


def test_bad_time_arrays_and_timezone_are_rejected():
    for change in [lambda x: x.update(utc_offset_seconds=3600),
                   lambda x: x["hourly"]["time"].reverse(),
                   lambda x: x["hourly"]["temperature_2m"].pop(),
                   lambda x: x["current"].update(time=True)]:
        raw = fixture();change(raw)
        with pytest.raises(WeatherError):normalize(raw, 48.2, 16.4, NOW)


@pytest.mark.parametrize("latitude,longitude", [(float('nan'), 0), (0, float('inf')), (91, 0), (0, -181), (True, 0)])
def test_coordinates_are_bounded_and_cannot_change_network_destination(latitude, longitude):
    with pytest.raises(WeatherError):query_url(latitude, longitude)


def test_cache_never_refreshes_retrieval_or_valid_time_and_ages_quality():
    calls = [];clock = [NOW]
    preview = WeatherPreview(fetch=lambda url: calls.append(url) or fixture(), clock=lambda: clock[0], monotonic=lambda: 0)
    initial = preview.preview(48.2, 16.4)
    clock[0] += timedelta(minutes=50)
    later = preview.preview(48.2, 16.4)
    assert len(calls) == 1 and later["cached"]
    assert later["retrieved_at"] == initial["retrieved_at"]
    assert later["current"] == initial["current"]
    assert later["quality"]["status"] == "review_required"
    later["current"]["values"]["temperature_c"]["value"] = 999
    assert preview.preview(48.2, 16.4)["current"]["values"]["temperature_c"]["value"] == 12


def test_preview_http_does_not_write_park_or_expose_provider_error(tmp_path):
    app = create_app(str(tmp_path/'park.db'), run_background=False)
    app.state.weather_preview.fetch = lambda url: fixture()
    app.state.weather_preview.clock = lambda: NOW
    with TestClient(app) as client:
        before = client.get('/api/audit').json()
        scenario = client.get('/api/state').json()['scenario']
        result = client.get('/api/integrations/weather/preview?latitude=48.2&longitude=16.4')
        assert result.status_code == 200
        assert client.get('/api/audit').json() == before
        assert client.get('/api/state').json()['scenario'] == scenario
        app.state.weather_preview.fetch = lambda url: (_ for _ in ()).throw(RuntimeError('PRIVATE_PROVIDER_DETAIL'))
        failed = client.get('/api/integrations/weather/preview?latitude=49&longitude=16')
        assert failed.status_code == 502 and 'PRIVATE_PROVIDER_DETAIL' not in failed.text
        assert client.get('/api/integrations/weather/preview?latitude=91&longitude=0').status_code == 422
