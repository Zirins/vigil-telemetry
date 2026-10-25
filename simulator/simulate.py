#!/usr/bin/env python3
"""
Standalone async simulator that registers a test service and streams synthetic
telemetry to the Vigil backend, injecting occasional anomalies to trigger detection.

Run from project root:
    python simulator/simulate.py
    python simulator/simulate.py --duration 90 --rate 6 --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_SERVICE_NAME = "payment-service"
DEFAULT_DURATION = 120.0
DEFAULT_RATE = 4.0

NORMAL_MESSAGES = [
    "Payment processed successfully",
    "Auth token validated",
    "Database query completed in 42ms",
    "Request received: POST /charge",
    "Cache hit for customer_id cust_8821",
    "Webhook delivered to merchant endpoint",
]

DEGRADED_MESSAGES = [
    "Database connection timeout after 5000ms",
    "Stripe API call failed: connection reset",
    "Payment retry attempt 1/3 for order_9912",
    "High latency detected: 1840ms response time",
]

RAGE_MESSAGE = "Database connection timeout after 5000ms"


@dataclass
class SimulationStats:
    events_sent: int = 0
    batches_sent: int = 0
    error_bursts_injected: int = 0
    metric_spikes_injected: int = 0
    rage_patterns_injected: int = 0
    failed_batches: int = 0
    incidents_at_start: int = 0
    incidents_at_end: int = 0
    incident_ids_seen: set[int] = field(default_factory=set)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream synthetic events to Vigil and inject anomalies."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vigil API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--service-name",
        default=DEFAULT_SERVICE_NAME,
        help=f"Service name to register (default: {DEFAULT_SERVICE_NAME})",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help=f"Simulation duration in seconds (default: {DEFAULT_DURATION})",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE,
        help=f"Target events per second (default: {DEFAULT_RATE})",
    )
    parser.add_argument(
        "--batch-interval",
        type=float,
        default=1.0,
        help="Seconds between POST batches (default: 1.0)",
    )
    return parser.parse_args()


def _normal_events() -> list[dict[str, Any]]:
    return [
        {
            "level": "INFO",
            "message": random.choice(NORMAL_MESSAGES),
            "source": "app",
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "cpu_pct",
                "value": round(random.uniform(20, 45), 2),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "error_rate",
                "value": round(random.uniform(0.001, 0.02), 4),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "latency_p99",
                "value": round(random.uniform(45, 95), 2),
                "unit": "ms",
            },
        },
    ]


def _error_burst_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "level": "INFO",
            "message": random.choice(NORMAL_MESSAGES),
            "source": "app",
        }
    ]
    for _ in range(12):
        events.append(
            {
                "level": "ERROR",
                "message": random.choice(DEGRADED_MESSAGES),
                "source": "db-pool",
            }
        )
    events.extend(
        [
            {
                "level": "METRIC",
                "source": "system",
                "payload": {
                    "metric": "error_rate",
                    "value": round(random.uniform(0.35, 0.55), 4),
                    "unit": "percent",
                },
            },
            {
                "level": "METRIC",
                "source": "system",
                "payload": {
                    "metric": "cpu_pct",
                    "value": round(random.uniform(72, 88), 2),
                    "unit": "percent",
                },
            },
        ]
    )
    return events


def _metric_spike_events() -> list[dict[str, Any]]:
    return [
        {
            "level": "WARN",
            "message": random.choice(DEGRADED_MESSAGES),
            "source": "db-pool",
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "cpu_pct",
                "value": round(random.uniform(94, 99.5), 2),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "error_rate",
                "value": round(random.uniform(0.65, 0.92), 4),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "latency_p99",
                "value": round(random.uniform(550, 1250), 2),
                "unit": "ms",
            },
        },
    ]


def _rage_pattern_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "level": "INFO",
            "message": random.choice(NORMAL_MESSAGES),
            "source": "app",
        }
    ]
    for _ in range(8):
        events.append(
            {
                "level": "ERROR",
                "message": RAGE_MESSAGE,
                "source": "db-pool",
            }
        )
    events.append(
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "cpu_pct",
                "value": round(random.uniform(85, 92), 2),
                "unit": "percent",
            },
        }
    )
    return events


async def register_service(
    client: httpx.AsyncClient, base_url: str, service_name: str
) -> int:
    response = await client.post(
        f"{base_url}/services",
        json={
            "name": service_name,
            "environment": "dev",
            "description": "Synthetic telemetry from simulator/simulate.py",
        },
    )

    if response.status_code == 200:
        body = response.json()
        return int(body["data"]["id"])

    if response.status_code == 409:
        list_response = await client.get(f"{base_url}/services")
        list_response.raise_for_status()
        for service in list_response.json().get("data", []):
            if service["name"] == service_name:
                return int(service["id"])
        raise RuntimeError(f"Service '{service_name}' exists but could not be resolved")

    response.raise_for_status()
    raise RuntimeError(f"Unexpected service registration response: {response.status_code}")


async def fetch_incidents(
    client: httpx.AsyncClient, base_url: str, service_id: int
) -> tuple[int, set[int]]:
    response = await client.get(
        f"{base_url}/incidents",
        params={"service_id": service_id, "limit": 500},
    )
    response.raise_for_status()
    body = response.json()
    incidents = body.get("data", [])
    incident_ids = {int(incident["id"]) for incident in incidents}
    return int(body.get("count", len(incidents))), incident_ids


async def send_batch(
    client: httpx.AsyncClient,
    base_url: str,
    service_id: int,
    events: list[dict[str, Any]],
) -> bool:
    response = await client.post(
        f"{base_url}/events",
        json={"service_id": service_id, "events": events},
    )
    if response.status_code != 200:
        print(
            f"  [warn] batch failed ({response.status_code}): {response.text}",
            file=sys.stderr,
        )
        return False
    return True


def _choose_batch(
    stats: SimulationStats,
    elapsed: float,
    duration: float,
    batch_index: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return events and optional anomaly label injected this batch."""
    warmup_seconds = min(25.0, duration * 0.2)
    if elapsed < warmup_seconds:
        return _normal_events(), None

    remaining = duration - elapsed
    anomaly_window = elapsed > warmup_seconds and remaining > 5

    if not anomaly_window:
        return _normal_events(), None

    roll = random.random()
    if batch_index % 18 == 0 and roll < 0.85:
        stats.metric_spikes_injected += 1
        return _metric_spike_events(), "metric_spike"
    if batch_index % 14 == 0 and roll < 0.75:
        stats.rage_patterns_injected += 1
        return _rage_pattern_events(), "rage_pattern"
    if batch_index % 11 == 0 and roll < 0.7:
        stats.error_bursts_injected += 1
        return _error_burst_events(), "error_burst"
    if roll < 0.04:
        choice = random.choice(["metric_spike", "error_burst", "rage_pattern"])
        if choice == "metric_spike":
            stats.metric_spikes_injected += 1
            return _metric_spike_events(), choice
        if choice == "rage_pattern":
            stats.rage_patterns_injected += 1
            return _rage_pattern_events(), choice
        stats.error_bursts_injected += 1
        return _error_burst_events(), choice

    return _normal_events(), None


def _pad_batch(events: list[dict[str, Any]], target_size: int) -> list[dict[str, Any]]:
    if len(events) >= target_size:
        return events
    padded = list(events)
    while len(padded) < target_size:
        padded.append(
            {
                "level": "INFO",
                "message": random.choice(NORMAL_MESSAGES),
                "source": "app",
            }
        )
    return padded


async def run_simulation(
    base_url: str,
    service_name: str,
    duration: float,
    rate: float,
    batch_interval: float,
) -> SimulationStats:
    stats = SimulationStats()
    events_per_batch = max(1, int(rate * batch_interval))

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Registering service '{service_name}' at {base_url} ...")
        service_id = await register_service(client, base_url, service_name)
        print(f"Service registered with id={service_id}")

        stats.incidents_at_start, _ = await fetch_incidents(
            client, base_url, service_id
        )

        print(
            f"Simulating for {duration:.0f}s at ~{rate:.1f} events/s "
            f"({events_per_batch} events every {batch_interval:.1f}s) ..."
        )
        started = time.monotonic()
        batch_index = 0

        while True:
            elapsed = time.monotonic() - started
            if elapsed >= duration:
                break

            events, anomaly_label = _choose_batch(
                stats, elapsed, duration, batch_index
            )
            events = _pad_batch(events, events_per_batch)

            ok = await send_batch(client, base_url, service_id, events)
            stats.batches_sent += 1
            if ok:
                stats.events_sent += len(events)
                if anomaly_label:
                    print(f"  [{elapsed:6.1f}s] injected anomaly: {anomaly_label}")
            else:
                stats.failed_batches += 1

            _, incident_ids = await fetch_incidents(client, base_url, service_id)
            stats.incident_ids_seen.update(incident_ids)

            batch_index += 1
            sleep_for = batch_interval - (time.monotonic() - started - elapsed)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        stats.incidents_at_end, final_ids = await fetch_incidents(
            client, base_url, service_id
        )
        stats.incident_ids_seen.update(final_ids)

    return stats


def print_summary(
    stats: SimulationStats,
    duration: float,
    rate: float,
    service_name: str,
) -> None:
    incidents_triggered = max(0, stats.incidents_at_end - stats.incidents_at_start)
    new_incident_ids = stats.incident_ids_seen

    print()
    print("=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    print(f"  Service:              {service_name}")
    print(f"  Duration:             {duration:.1f}s")
    print(f"  Target rate:          {rate:.1f} events/s")
    print(f"  Events sent:          {stats.events_sent}")
    print(f"  Batches sent:         {stats.batches_sent}")
    print(f"  Failed batches:       {stats.failed_batches}")
    print(f"  Anomalies injected:")
    print(f"    - Metric spikes:    {stats.metric_spikes_injected}")
    print(f"    - Error bursts:     {stats.error_bursts_injected}")
    print(f"    - Rage patterns:    {stats.rage_patterns_injected}")
    print(f"  Incidents at start:   {stats.incidents_at_start}")
    print(f"  Incidents at end:     {stats.incidents_at_end}")
    print(f"  Incidents triggered:  {incidents_triggered}")
    if new_incident_ids:
        print(f"  Incident IDs seen:    {sorted(new_incident_ids)}")
    print("=" * 60)


async def main() -> None:
    args = parse_args()
    if args.duration <= 0:
        print("Duration must be positive.", file=sys.stderr)
        sys.exit(1)
    if args.rate <= 0:
        print("Rate must be positive.", file=sys.stderr)
        sys.exit(1)

    try:
        stats = await run_simulation(
            base_url=args.base_url.rstrip("/"),
            service_name=args.service_name,
            duration=args.duration,
            rate=args.rate,
            batch_interval=args.batch_interval,
        )
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_summary(stats, args.duration, args.rate, args.service_name)


if __name__ == "__main__":
    asyncio.run(main())
