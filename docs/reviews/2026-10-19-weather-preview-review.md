# Independent review: external weather preview

Reviewed 19 October 2026: `backend/integrations/weather.py`, route installation, focused tests, preview documentation and archived Vienna response. No request was made to the shared eight-hour service and no physical action was attempted. This is source/fixture review; the archived successful Horde network request is separately identified evidence supplied by the coordinator.

**Verdict: the adapter is appropriately separated from the synthetic park, but its original normalized representation loses important temporal meaning.** Preserve precipitation/gust windows and check forecast coverage before using the data for an operational question.

## What is sound

The fixed provider endpoint, bounded coordinates/response size, explicit redirect rejection and error redaction provide a small understandable integration boundary. A bounded cache retains original retrieval/valid times, recalculates age and does not invent a fallback observation. No canonical ingestion, scenario change, action or work order occurs. Failed refreshes return an explicit failure.

The documentation correctly calls current conditions numerical weather-model estimates, not a local mast reading; keeps `forecast_issued_at:null`; distinguishes Vienna reference coordinates from a configured park location; preserves provider attribution; and avoids suggesting that a weather forecast authorizes ride operation. The Open-Meteo documentation confirms current conditions use model data and defines valid time separately from aggregation interval. [Provider API documentation](https://open-meteo.com/en/docs).

All 13 original weather checks passed independently as part of a 30-test combined evidence/weather run. The existing tests cover explicit fixtures, not provider forecast accuracy or field calibration.

## P2: accumulation windows were dropped

The original adapter discards `current.interval` and gives current/hourly precipitation the same normalized `precipitation_mm` shape. A 2 mm quantity over fifteen minutes and 2 mm over an hour are different operational inputs. Wind gust values similarly summarize a window rather than representing ordinary instantaneous wind speed.

The provider documents `current.interval` as the duration for backward-looking aggregates; hourly precipitation is the preceding-hour sum. The 15-minute gust field is a preceding-window maximum. Preserve the interval and a field-level temporal statistic such as `instant`, `sum` or `maximum`, without inventing an issue timestamp. [Open-Meteo field and response definitions](https://open-meteo.com/en/docs).

Reproduced with a valid fixture containing `current.interval:900`: the normalized output retained 2 mm but no interval. This is a semantic gap even though no current code acts on the preview.

## P2: current freshness did not establish forecast coverage

The original overall quality check inspects current valid time and current fields only. In an isolated fixture, current valid time was 20:00 UTC while all twelve hourly entries were from the previous day/current morning, ending at 07:00 UTC. At 20:00 the adapter returned `quality.status:available` with no reasons. Array alignment and increasing timestamps passed, but there was no usable prospective horizon.

Require separate forecast coverage metadata and a quality reason when the requested future period is unavailable, begins implausibly far in the future, or contains incorrect cadence. A current-hour entry may legitimately precede retrieval time; do not reject it simply because the clock has advanced within the hour. Cache checks should age forecast coverage as well as current estimates.

Both findings were sent to the coordinator. This report records the original reproduced behavior; any fix needs a new focused regression result and source identity before marking it resolved.

## Practical value threshold

The preview is a useful first real API connection. Its demonstrated value is provenance-preserving external context, not weather-dependent park optimization. The next meaningful step is configured park location plus a comparison against local measurements, with explicit forecast horizon and issue-time limitations. Only then should a separate advisory workflow use it to request human review. Linking an arbitrary reference forecast directly to the existing synthetic heatwave model would blur observation, assumption and action.

## Coordinator resolution checkpoint

Both findings were corrected before publication of the adapter. Current estimates
now retain the provider's interval; precipitation carries preceding-window sum
metadata and gusts preceding-window maximum metadata, with separate hourly windows.
Quality separately checks future hourly coverage, partial horizons and missing
forecast fields. The reviewer counterexamples are regression tests. Fifteen focused
weather checks pass. A fresh actual Horde response after these changes is archived
with its adapter-source hash in `docs/experiments/external-weather/reviewed-capture.json`.
