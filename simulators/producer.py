"""Publish bounded, explicitly synthetic source samples through the HTTP boundary.

Run from the repository root: python -m simulators.producer --source weather
Default operation prints JSON lines and never contacts the gateway.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from backend.domain import SCENARIOS, registry
from backend.model_rules import evaluate
from backend.connectors.adapters import SyntheticDomainAdapter
from backend.connectors.catalog import default_catalog


class ProducerError(RuntimeError):
    """A source contract or delivery failure that needs operator attention."""


class SyntheticProducer:
    """Pure-model source samples, using the gateway's single mapping catalog."""

    def __init__(self, source_ids, profile="normal"):
        specs = {spec.id: spec for spec in default_catalog()}
        if not source_ids or any(source not in specs for source in source_ids):
            raise ValueError("Select at least one known source")
        if profile not in {item["id"] for item in SCENARIOS}:
            raise ValueError("Unknown synthetic profile")
        self.sources = tuple(dict.fromkeys(source_ids))
        self.profile = profile
        self.session_id = uuid.uuid4().hex
        self.base = {asset["id"]: asset for asset in registry()}
        self.adapters = {source: SyntheticDomainAdapter(specs[source]) for source in self.sources}

    def batches(self, tick, timestamp=None):
        """One complete sample per selected source; the caller supplies its tick.

        Retrying delivery must reuse the returned batch, without regenerating its
        timestamp or event IDs. Each process has a distinct producer session ID.
        """
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise ValueError("Tick must be a nonnegative integer")
        timestamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="microseconds")
        context = evaluate(self.base, self.profile, {}, tick, timestamp, {}, [])
        batches = {}
        for source, adapter in self.adapters.items():
            events = adapter.snapshot(context).events
            for event in events:
                event["event_id"] = f"producer:{self.session_id}:{event['event_id']}"
            batches[source] = {"synthetic": True, "events": events}
        return batches


def require_paused_sources(client, source_ids):
    """Preflight only: producers never pause/resume a gateway source themselves."""
    for source in source_ids:
        response = client.get(f"/api/connectors/{source}")
        if response.status_code != 200:
            raise ProducerError(f"Cannot inspect {source}: HTTP {response.status_code}")
        catalog = response.json()
        if catalog.get("synthetic") is not True or not catalog.get("capabilities", {}).get("demo_ingest"):
            raise ProducerError(f"{source} does not permit synthetic ingestion")
        if catalog.get("health", {}).get("mode") != "paused":
            raise ProducerError(f"Pause the in-process {source} connector before publishing")


def publish_batch(client, source_id, batch, retries=2, sleep=time.sleep):
    """Bounded retry of the *same* event IDs after transport/5xx failures.

    Per-event rejection is final, including a partially accepted batch. A lost
    success response can be retried safely within the gateway's bounded dedup
    window; this is not a durable or exactly-once delivery guarantee.
    """
    if not 0 <= retries <= 5:
        raise ValueError("Retries must be between 0 and 5")
    for attempt in range(retries + 1):
        try:
            response = client.post(f"/api/connectors/{source_id}/ingest", json=batch)
        except httpx.TransportError as exc:
            if attempt == retries:
                raise ProducerError(f"{source_id}: delivery failed after {attempt + 1} attempts") from exc
        else:
            if response.status_code < 500:
                if response.status_code != 200:
                    raise ProducerError(f"{source_id}: ingestion returned HTTP {response.status_code}")
                result = response.json()
                if result.get("rejected") != 0:
                    codes = sorted({error.get("code", "unknown") for error in result.get("errors", [])})
                    raise ProducerError(f"{source_id}: {result.get('rejected')} events rejected ({', '.join(codes)}); batch may be partially applied")
                if result.get("accepted", 0) + result.get("duplicates", 0) != len(batch["events"]):
                    raise ProducerError(f"{source_id}: incomplete ingestion acknowledgment")
                return result
            if attempt == retries:
                raise ProducerError(f"{source_id}: ingestion returned HTTP {response.status_code} after {attempt + 1} attempts")
        sleep(min(.25 * 2 ** attempt, 2))
    raise AssertionError("Unreachable delivery loop")


def _rate(value):
    try:
        rate = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Rate must be a finite number between 0.1 and 20 Hz")
    if not math.isfinite(rate) or not .1 <= rate <= 20:
        raise argparse.ArgumentTypeError("Rate must be a finite number between 0.1 and 20 Hz")
    return rate


def _count(value):
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Count must be an integer between 1 and 100000")
    if not 1 <= count <= 100000:
        raise argparse.ArgumentTypeError("Count must be an integer between 1 and 100000")
    return count


def _api_url(value):
    try:
        parsed = urlsplit(value)
        parsed.port  # Validate the optional port before constructing an HTTP client.
    except ValueError:
        raise argparse.ArgumentTypeError("Use a valid gateway HTTP(S) origin")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise argparse.ArgumentTypeError("Use a gateway HTTP(S) origin, e.g. http://127.0.0.1:8000")
    return value.rstrip("/")


def main(argv=None):
    sources = [spec.id for spec in default_catalog()]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, choices=[*sources, "all"], help="Repeat for several sources; use all for all ten")
    parser.add_argument("--profile", choices=[item["id"] for item in SCENARIOS], default="normal", help="Synthetic scenario, independent of the gateway scenario")
    parser.add_argument("--rate", type=_rate, default=1.0, help="Samples per second, 0.1–20 (default 1)")
    parser.add_argument("--count", type=_count, default=1, help="Finite samples per source, 1–100000 (default 1)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--api-url", type=_api_url, help="Explicit gateway origin enables HTTP publishing")
    target.add_argument("--emit-json", action="store_true", help="Print JSON lines without networking (the default)")
    args = parser.parse_args(argv)
    selected = sources if "all" in args.source else list(dict.fromkeys(args.source))
    producer = SyntheticProducer(selected, args.profile)
    client = httpx.Client(base_url=args.api_url, timeout=10, follow_redirects=False, trust_env=False) if args.api_url else None
    try:
        if client:
            require_paused_sources(client, selected)
        deadline = time.monotonic()
        for tick in range(1, args.count + 1):
            for source, batch in producer.batches(tick).items():
                if client:
                    result = publish_batch(client, source, batch)
                    output = {"synthetic": True, "session_id": producer.session_id, "source_id": source,
                              "sample": tick, "accepted": result["accepted"], "duplicates": result["duplicates"]}
                else:
                    output = {"source_id": source, **batch}
                print(json.dumps(output, allow_nan=False), flush=True)
            if tick < args.count:
                # Do not burst to catch up after slow requests or retries.
                deadline = max(deadline + 1 / args.rate, time.monotonic())
                time.sleep(max(0, deadline - time.monotonic()))
    except (ProducerError, httpx.HTTPError, ValueError) as exc:
        print(f"Synthetic producer stopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if client:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
