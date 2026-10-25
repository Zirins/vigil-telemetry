#!/usr/bin/env python3
"""
Measure Vigil event ingestion throughput and POST /events latency.

Registers a dedicated service, runs four rate tiers (10/25/50/100 events/sec),
and reports achieved throughput, response latency percentiles, and confirmed DB writes.

Run from project root (backend must be running on localhost:8000):
    python backend/scripts/throughput_benchmark.py
    python backend/scripts/throughput_benchmark.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIER_DURATION = 30.0
DEFAULT_BATCH_INTERVAL = 1.0
FAILURE_THRESHOLD = 0.05
RATE_TIERS = [10, 25, 50, 100]


@dataclass
class TierResult:
    target_rate: int
    duration_seconds: float
    events_sent: int
    events_confirmed: int
    batches_attempted: int
    batches_failed: int
    latencies_ms: list[float]
    stopped_early: bool
    stop_reason: str | None = None

    @property
    def actual_rate(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.events_sent / self.duration_seconds

    @property
    def db_write_rate(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.events_confirmed / self.duration_seconds

    @property
    def failure_rate(self) -> float:
        if self.batches_attempted == 0:
            return 0.0
        return self.batches_failed / self.batches_attempted

    @property
    def mean_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    @property
    def p95_latency_ms(self) -> float:
        return _percentile(self.latencies_ms, 95)

    @property
    def p99_latency_ms(self) -> float:
        return _percentile(self.latencies_ms, 99)

    @property
    def status(self) -> str:
        if self.stopped_early:
            return f"STOP ({self.stop_reason})"
        if self.batches_failed > 0:
            return "DEGRADED"
        return "OK"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _build_events(count: int, batch_index: int) -> list[dict[str, Any]]:
    return [
        {
            "level": "INFO",
            "message": f"throughput probe batch={batch_index} seq={index}",
            "source": "throughput-benchmark",
        }
        for index in range(count)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Vigil POST /events ingestion throughput and latency."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--tier-duration",
        type=float,
        default=DEFAULT_TIER_DURATION,
        help=f"Seconds per rate tier (default: {DEFAULT_TIER_DURATION})",
    )
    parser.add_argument(
        "--batch-interval",
        type=float,
        default=DEFAULT_BATCH_INTERVAL,
        help=f"Seconds between POST batches (default: {DEFAULT_BATCH_INTERVAL})",
    )
    return parser.parse_args()


async def register_service(client: httpx.AsyncClient, base_url: str) -> tuple[int, str]:
    service_name = f"throughput-service-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        f"{base_url}/services",
        json={
            "name": service_name,
            "environment": "benchmark",
            "description": "Throughput benchmark harness — safe to delete",
        },
    )
    response.raise_for_status()
    body = response.json()
    return int(body["data"]["id"]), service_name


async def fetch_event_count(
    client: httpx.AsyncClient, base_url: str, service_id: int
) -> int:
    response = await client.get(
        f"{base_url}/events/{service_id}",
        params={"limit": 1},
    )
    response.raise_for_status()
    return int(response.json()["count"])


async def send_batch(
    client: httpx.AsyncClient,
    base_url: str,
    service_id: int,
    events: list[dict[str, Any]],
) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/events",
            json={"service_id": service_id, "events": events},
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return response.status_code == 200, latency_ms
    except httpx.HTTPError:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, latency_ms


async def run_tier(
    client: httpx.AsyncClient,
    base_url: str,
    service_id: int,
    target_rate: int,
    duration: float,
    batch_interval: float,
) -> TierResult:
    events_per_batch = max(1, int(target_rate * batch_interval))
    count_before = await fetch_event_count(client, base_url, service_id)

    latencies_ms: list[float] = []
    events_sent = 0
    batches_attempted = 0
    batches_failed = 0
    stopped_early = False
    stop_reason: str | None = None

    tier_started = time.monotonic()
    batch_index = 0

    print(f"\n--- Tier: {target_rate} events/sec ---")
    print(
        f"  Batch size: {events_per_batch} events every {batch_interval:.2f}s "
        f"(target {events_per_batch / batch_interval:.0f}/s)"
    )

    while True:
        elapsed = time.monotonic() - tier_started
        if elapsed >= duration:
            break

        events = _build_events(events_per_batch, batch_index)
        ok, latency_ms = await send_batch(client, base_url, service_id, events)

        batches_attempted += 1
        latencies_ms.append(latency_ms)
        if ok:
            events_sent += len(events)
        else:
            batches_failed += 1

        if batches_attempted >= 5:
            failure_rate = batches_failed / batches_attempted
            if failure_rate > FAILURE_THRESHOLD:
                stopped_early = True
                stop_reason = f">{FAILURE_THRESHOLD:.0%} batch failure rate"
                print(
                    f"  Stopping tier early at {elapsed:.1f}s — "
                    f"{batches_failed}/{batches_attempted} batches failed "
                    f"({failure_rate:.1%})"
                )
                break

        batch_index += 1
        sleep_for = batch_interval - (time.monotonic() - tier_started - elapsed)
        if sleep_for > 0 and not stopped_early:
            await asyncio.sleep(sleep_for)

    elapsed_total = time.monotonic() - tier_started
    await asyncio.sleep(0.5)
    count_after = await fetch_event_count(client, base_url, service_id)
    events_confirmed = max(0, count_after - count_before)

    result = TierResult(
        target_rate=target_rate,
        duration_seconds=elapsed_total,
        events_sent=events_sent,
        events_confirmed=events_confirmed,
        batches_attempted=batches_attempted,
        batches_failed=batches_failed,
        latencies_ms=latencies_ms,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )

    print(
        f"  Result: sent={result.events_sent} confirmed={result.events_confirmed} "
        f"actual={result.actual_rate:.1f}/s db={result.db_write_rate:.1f}/s "
        f"mean={result.mean_latency_ms:.0f}ms p99={result.p99_latency_ms:.0f}ms "
        f"failed={result.batches_failed}/{result.batches_attempted}"
    )
    return result


def _fmt_rate(value: float) -> str:
    return f"{value:.1f}/s"


def print_summary(
    service_id: int,
    service_name: str,
    tier_duration: float,
    results: list[TierResult],
) -> None:
    print()
    print("=" * 88)
    print("VIGIL INGESTION THROUGHPUT BENCHMARK")
    print("=" * 88)
    print(f"  Service:       {service_name} (id={service_id})")
    print(f"  Tier duration: {tier_duration:.0f}s")
    print(f"  Rate tiers:    {', '.join(str(r) for r in RATE_TIERS)} events/sec")
    print(f"  Early stop:    >{FAILURE_THRESHOLD:.0%} batch failure rate")
    print()
    header = (
        f"  {'Tier':<6}{'Target':<10}{'Actual':<10}{'DB Rate':<10}"
        f"{'Mean':<9}{'P95':<9}{'P99':<9}"
        f"{'Failed':<12}{'Confirmed':<12}{'Status'}"
    )
    print(header)
    print(f"  {'-' * 84}")

    for result in results:
        failed = f"{result.batches_failed}/{result.batches_attempted}"
        confirmed = f"{result.events_confirmed}/{result.events_sent}"
        print(
            f"  {result.target_rate:<6}"
            f"{_fmt_rate(float(result.target_rate)):<10}"
            f"{_fmt_rate(result.actual_rate):<10}"
            f"{_fmt_rate(result.db_write_rate):<10}"
            f"{result.mean_latency_ms:>6.0f}ms "
            f"{result.p95_latency_ms:>6.0f}ms "
            f"{result.p99_latency_ms:>6.0f}ms "
            f"{failed:<12}"
            f"{confirmed:<12}"
            f"{result.status}"
        )

    print(f"  {'-' * 84}")
    print()
    print("  Resume bullets")
    print("  " + "-" * 40)

    best = max(
        (r for r in results if not r.stopped_early and r.batches_failed == 0),
        key=lambda r: r.target_rate,
        default=None,
    )
    if best is not None:
        print(
            f"  - Processed {_fmt_rate(best.actual_rate)} with "
            f"{best.p99_latency_ms:.0f}ms P99 POST /events latency"
        )
        print(
            f"  - Sustained {best.target_rate} events/sec throughput with "
            f"zero failed batches over {best.duration_seconds:.0f}s"
        )
    else:
        partial = max(results, key=lambda r: r.actual_rate)
        print(
            f"  - Peak achieved {_fmt_rate(partial.actual_rate)} before saturation "
            f"(P99 {partial.p99_latency_ms:.0f}ms)"
        )

    zero_fail = [r for r in results if r.batches_failed == 0 and not r.stopped_early]
    if zero_fail:
        peak = max(zero_fail, key=lambda r: r.target_rate)
        print(
            f"  - Zero failed batches up to {peak.target_rate} events/sec "
            f"(mean latency {peak.mean_latency_ms:.0f}ms)"
        )

    print("=" * 88)


async def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    if args.tier_duration <= 0 or args.batch_interval <= 0:
        print("tier-duration and batch-interval must be positive.", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        health = await client.get(f"{base_url}/health")
        health.raise_for_status()

        print(f"Registering throughput service at {base_url} ...")
        service_id, service_name = await register_service(client, base_url)
        print(f"Service registered: {service_name} (id={service_id})")

        results: list[TierResult] = []
        try:
            for target_rate in RATE_TIERS:
                result = await run_tier(
                    client,
                    base_url,
                    service_id,
                    target_rate,
                    args.tier_duration,
                    args.batch_interval,
                )
                results.append(result)
                if result.stopped_early:
                    print("  Backend saturated — skipping higher tiers.")
                    break
                await asyncio.sleep(1.0)
        finally:
            try:
                await client.delete(f"{base_url}/services/{service_id}")
                print(f"Cleaned up throughput service: {service_name} (id={service_id})")
            except Exception:
                pass

    print_summary(service_id, service_name, args.tier_duration, results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBenchmark interrupted.", file=sys.stderr)
        sys.exit(130)
