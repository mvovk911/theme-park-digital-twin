# External weather preview

The prototype has one real, read-only external adapter:

```http
GET /api/integrations/weather/preview?latitude=48.2082&longitude=16.3738
```

Coordinates are required. The example uses Vienna city centre as an illustrative
reference, **not the location of a real or configured Aster Park**. It fetches
current numerical weather-model estimates and twelve hourly steps from
[Open-Meteo's documented forecast endpoint](https://open-meteo.com/en/docs).
Current conditions are modeled estimates, not observations from a local wind mast.

The response includes requested and returned grid coordinates, valid times,
retrieval time, canonical units, quality, attribution and a raw-payload hash.
`forecast_issued_at` remains null because this API response does not identify an
issue timestamp. Retrieval time must not be substituted for issue time.
Current precipitation carries the provider's accumulation interval; hourly totals
carry a 3,600-second window. Gusts are preceding-window maxima, while temperature
and wind speed are instantaneous model estimates. Missing, nonnumeric, out-of-range
or wrong-unit fields remain unknown. Forecast
arrays must align and use hourly spacing. Quality separately reports future coverage,
partial horizons and missing forecast fields; a fresh current estimate cannot hide
a wholly historical hourly series. Cached results retain original retrieval
and valid times; the quality check advances with the clock. The cache holds at
most 32 coordinate pairs for fifteen minutes. A failed refresh returns an explicit
502; no fallback synthetic value is presented as external weather.

This preview does **not** inject values into the synthetic connector backbone,
alter a planner branch, change a scenario, or close/open a ride. It is a concrete
adapter boundary for later authorized configuration and calibration. The existing
weather station remains labeled synthetic. OEM operating limits, lightning
observation, local wind/gust measurements and operator procedures are separate
requirements for an actual weather-related operational decision.

## Actual connection evidence

A live read from Horde succeeded on **19 October 2026 at 19:55:30 UTC**. It returned
a current valid time of 19:45 UTC and a modeled 10.1 °C at the illustrative
reference location. The normalized, attributed [response is archived here](experiments/external-weather/2026-10-19-vienna-preview.json).
A second [reviewed response](experiments/external-weather/2026-10-19-vienna-preview-reviewed.json)
was fetched at 20:00:58 UTC after adding aggregation windows and forecast coverage.
Its [capture manifest](experiments/external-weather/reviewed-capture.json) records
the adapter source and response hashes. The first response is preserved as an
earlier checkpoint, before that metadata improvement.

The local coordinator's first request failed with a network connection reset; the
Horde request succeeded. No value was injected into live synthetic state.

Fifteen focused checks cover provenance, missing/invalid fields, units, coordinate
bounds, time arrays, aging without timestamp refresh, cache isolation, HTTP error
redaction and absence of park/audit writes. They use explicitly synthetic fixtures;
the archived response above is separate actual network evidence.

## Provider terms and next integration step

Weather data attribution: **Open-Meteo.com, CC BY 4.0**. The public service is for
noncommercial use. A commercial park deployment needs an appropriate provider
agreement and service configuration; see the [provider's terms](https://open-meteo.com/en/terms).

For an actual pilot, configure the park's coordinates, source ownership, allowed
fields and refresh/freshness policy. Preserve external source provenance and compare
against the local station. A forecast alert can open an operator review task; this
preview confers no physical command authority.
