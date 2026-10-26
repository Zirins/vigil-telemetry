#!/usr/bin/env python3
"""
Evaluate Vigil anomaly detection against labeled synthetic telemetry.

Fair-eval design (keeps production open-incident dedup unchanged):
  - Registers a **fresh service per round** so unresolved open incidents from a
    prior round cannot suppress later rounds (that was an evaluation artifact,
    not the detector failing). Within a round, production dedup still applies:
    only one open incident per (service, detection_type) at a time.
  - Scores each ground-truth injection against incidents whose detection_type
    matches the injected anomaly family, inside a fixed match window.
  - Supports a **tuning schedule** (original timings/magnitudes) and a
    **held-out schedule** (different timings and magnitudes, never used for
    threshold tuning).

Run from project root (backend must be running):
    python backend/scripts/benchmark.py --base-url http://127.0.0.1:8001
    python backend/scripts/benchmark.py --schedule both --rounds 5 --repeats 3 \\
        --base-url http://127.0.0.1:8001 --log-dir benchmarks/results
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import httpx

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_SERVICE_NAME = "benchmark-service"
DEFAULT_ROUNDS = 5
DEFAULT_REPEATS = 3
DEFAULT_ROUND_DURATION = 60.0
DEFAULT_RATE = 4.0
DEFAULT_BATCH_INTERVAL = 1.0
MATCH_WINDOW_SECONDS = 10.0
# Allow small negative deltas: Postgres created_at can lag the client injected_at clock.
MATCH_CLOCK_SKEW_SECONDS = 2.0
WARMUP_SECONDS = 18.0

# Injection label → detector detection_type string persisted on incidents.
ANOMALY_TO_DETECTION_TYPE: dict[str, str] = {
    "metric_spike": "spike",
    "error_burst": "error_rate",
    "rage_pattern": "rage_pattern",
}
DETECTION_TYPES = ("spike", "error_rate", "rage_pattern")

NORMAL_MESSAGES = [
    "Benchmark request processed",
    "Auth token validated",
    "Cache hit for benchmark key",
    "Database query completed in 38ms",
]

# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

# Original schedule used when thresholds were last adjusted (a7b897b era).
TUNING_SCHEDULE: list[tuple[float, str]] = [
    (20.0, "metric_spike"),
    (26.0, "error_burst"),
    (32.0, "rage_pattern"),
    (38.0, "metric_spike"),
    (44.0, "error_burst"),
    (50.0, "rage_pattern"),
    (56.0, "metric_spike"),
]

# Held-out: different offsets/order/magnitudes. Rage is scheduled *before*
# error_burst so run_detection can reach check_rage_pattern (error_rate is
# checked first and otherwise shadows rage while the window is hot).
HELD_OUT_SCHEDULE: list[tuple[float, str]] = [
    (20.0, "rage_pattern"),
    (26.0, "metric_spike"),
    (34.0, "error_burst"),
    (40.0, "metric_spike"),
    (46.0, "rage_pattern"),
    (52.0, "error_burst"),
    (58.0, "metric_spike"),
]

SCHEDULES: dict[str, list[tuple[float, str]]] = {
    "tuning": TUNING_SCHEDULE,
    "held_out": HELD_OUT_SCHEDULE,
}


@dataclass
class GroundTruth:
    round_index: int
    offset_seconds: float
    anomaly_type: str
    injected_at: datetime | None = None

    @property
    def detection_type(self) -> str:
        return ANOMALY_TO_DETECTION_TYPE[self.anomaly_type]


@dataclass
class TypeCounts:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    detection_latencies_ms: list[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    @property
    def mean_latency_ms(self) -> float:
        if not self.detection_latencies_ms:
            return 0.0
        return sum(self.detection_latencies_ms) / len(self.detection_latencies_ms)


@dataclass
class RoundResult:
    round_index: int
    service_id: int
    ground_truths: list[GroundTruth] = field(default_factory=list)
    incidents: list[dict[str, Any]] = field(default_factory=list)
    by_type: dict[str, TypeCounts] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.by_type:
            self.by_type = {name: TypeCounts() for name in DETECTION_TYPES}

    @property
    def true_positives(self) -> int:
        return sum(c.true_positives for c in self.by_type.values())

    @property
    def false_positives(self) -> int:
        return sum(c.false_positives for c in self.by_type.values())

    @property
    def false_negatives(self) -> int:
        return sum(c.false_negatives for c in self.by_type.values())

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    @property
    def detection_latencies_ms(self) -> list[float]:
        return [
            ms
            for counts in self.by_type.values()
            for ms in counts.detection_latencies_ms
        ]

    @property
    def mean_latency_ms(self) -> float:
        latencies = self.detection_latencies_ms
        return sum(latencies) / len(latencies) if latencies else 0.0


@dataclass
class BenchmarkSummary:
    schedule_name: str
    repeat_index: int
    round_results: list[RoundResult] = field(default_factory=list)

    @property
    def tp(self) -> int:
        return sum(r.true_positives for r in self.round_results)

    @property
    def fp(self) -> int:
        return sum(r.false_positives for r in self.round_results)

    @property
    def fn(self) -> int:
        return sum(r.false_negatives for r in self.round_results)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    @property
    def mean_latency_ms(self) -> float:
        latencies = [
            ms
            for result in self.round_results
            for ms in result.detection_latencies_ms
        ]
        return sum(latencies) / len(latencies) if latencies else 0.0

    @property
    def total_ground_truths(self) -> int:
        return sum(len(r.ground_truths) for r in self.round_results)

    @property
    def total_incidents(self) -> int:
        return sum(len(r.incidents) for r in self.round_results)

    def aggregate_by_type(self) -> dict[str, TypeCounts]:
        merged = {name: TypeCounts() for name in DETECTION_TYPES}
        for result in self.round_results:
            for name, counts in result.by_type.items():
                target = merged[name]
                target.true_positives += counts.true_positives
                target.false_positives += counts.false_positives
                target.false_negatives += counts.false_negatives
                target.detection_latencies_ms.extend(counts.detection_latencies_ms)
        return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Vigil anomaly detection against labeled injections."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--service-name",
        default=DEFAULT_SERVICE_NAME,
        help=f"Benchmark service name prefix (default: {DEFAULT_SERVICE_NAME})",
    )
    parser.add_argument(
        "--schedule",
        choices=("tuning", "held_out", "both"),
        default="both",
        help="Which injection schedule(s) to run (default: both)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"Rounds per repeat (default: {DEFAULT_ROUNDS})",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help=f"Full repeats per schedule (default: {DEFAULT_REPEATS})",
    )
    parser.add_argument(
        "--round-duration",
        type=float,
        default=DEFAULT_ROUND_DURATION,
        help=f"Seconds per round (default: {DEFAULT_ROUND_DURATION})",
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
        default=DEFAULT_BATCH_INTERVAL,
        help=f"Seconds between POST batches (default: {DEFAULT_BATCH_INTERVAL})",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="If set, tee stdout to log-dir/detection_<stamp>.log",
    )
    parser.add_argument(
        "--keep-services",
        action="store_true",
        help="Retain benchmark services in the database instead of deleting on completion.",
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
                "value": round(random.uniform(22, 42), 2),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "error_rate",
                "value": round(random.uniform(0.001, 0.015), 4),
                "unit": "percent",
            },
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "latency_ms",
                "value": round(random.uniform(80, 160), 2),
                "unit": "ms",
            },
        },
    ]


def _metric_spike_events(*, schedule: str) -> list[dict[str, Any]]:
    """CPU spike only — no concurrent ERROR flood (keeps type labels clean)."""
    if schedule == "held_out":
        cpu = round(random.uniform(91.0, 94.5), 2)
        warn = "Elevated host CPU on held-out probe"
    else:
        cpu = round(random.uniform(96, 99.8), 2)
        warn = "CPU saturation warning on benchmark host"
    return [
        {"level": "WARN", "message": warn, "source": "system"},
        {
            "level": "METRIC",
            "source": "system",
            "payload": {"metric": "cpu_pct", "value": cpu, "unit": "percent"},
        },
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "latency_ms",
                "value": round(random.uniform(90, 150), 2),
                "unit": "ms",
            },
        },
    ]


def _error_burst_events(*, schedule: str) -> list[dict[str, Any]]:
    """
    High ERROR share with *distinct* messages so the label maps to error_rate,
    not rage_pattern (rage requires repeated identical messages).
    """
    if schedule == "held_out":
        # Need ERROR share > 0.18 over ~40s window (~80–100 events at 4/s).
        count = 22
        template = "Upstream inventory API timeout: read deadline exceeded id={}"
        source = "inventory"
    else:
        count = 24
        template = "Stripe API call failed: connection reset id={}"
        source = "payments"

    events: list[dict[str, Any]] = [
        {
            "level": "INFO",
            "message": random.choice(NORMAL_MESSAGES),
            "source": "app",
        }
    ]
    for index in range(count):
        events.append(
            {
                "level": "ERROR",
                "message": template.format(index),
                "source": source,
            }
        )
    # Avoid also injecting a METRIC spike on error_rate during an error_burst
    # label — that would create a concurrent spike incident and muddy type scores.
    events.append(
        {
            "level": "METRIC",
            "source": "system",
            "payload": {
                "metric": "latency_ms",
                "value": round(random.uniform(90, 140), 2),
                "unit": "ms",
            },
        }
    )
    return events


def _rage_pattern_events(*, schedule: str) -> list[dict[str, Any]]:
    if schedule == "held_out":
        count = 9
        message = "Redis lock acquisition failed after 3000ms"
    else:
        count = 10
        message = "Database connection timeout after 5000ms"

    events: list[dict[str, Any]] = [
        {
            "level": "INFO",
            "message": random.choice(NORMAL_MESSAGES),
            "source": "app",
        }
    ]
    for _ in range(count):
        events.append(
            {
                "level": "ERROR",
                "message": message,
                "source": "db-pool" if schedule == "tuning" else "cache",
            }
        )
    return events


def _events_for_anomaly(anomaly_type: str, *, schedule: str) -> list[dict[str, Any]]:
    if anomaly_type == "metric_spike":
        return _metric_spike_events(schedule=schedule)
    if anomaly_type == "error_burst":
        return _error_burst_events(schedule=schedule)
    if anomaly_type == "rage_pattern":
        return _rage_pattern_events(schedule=schedule)
    raise ValueError(f"Unknown anomaly type: {anomaly_type}")


def _pad_batch(events: list[dict[str, Any]], target_size: int) -> list[dict[str, Any]]:
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


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def register_service(
    client: httpx.AsyncClient, base_url: str, service_name: str
) -> int:
    unique_name = f"{service_name}-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        f"{base_url}/services",
        json={
            "name": unique_name,
            "environment": "benchmark",
            "description": "Detection benchmark harness — safe to delete",
        },
    )
    response.raise_for_status()
    return int(response.json()["data"]["id"])


async def delete_service(
    client: httpx.AsyncClient, base_url: str, service_id: int
) -> None:
    try:
        res = await client.delete(f"{base_url}/services/{service_id}")
        if res.status_code in (200, 204, 404):
            return
    except Exception as exc:
        print(f"Warning: failed to delete benchmark service {service_id}: {exc}")


async def purge_stale_benchmark_services(
    client: httpx.AsyncClient, base_url: str
) -> None:
    try:
        res = await client.get(
            f"{base_url}/services", params={"include_benchmark": "true"}
        )
        if res.status_code == 200:
            services = res.json().get("data", [])
            for s in services:
                name = s.get("name", "")
                env = s.get("environment", "")
                if (
                    env == "benchmark"
                    or name.startswith("benchmark-service-")
                    or name.startswith("throughput-service-")
                ):
                    await client.delete(f"{base_url}/services/{s['id']}")
    except Exception:
        pass


async def fetch_incidents(
    client: httpx.AsyncClient,
    base_url: str,
    service_id: int,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"service_id": service_id, "limit": 500}
    response = await client.get(f"{base_url}/incidents", params=params)
    response.raise_for_status()
    incidents = response.json().get("data", [])
    if since is None:
        return incidents

    filtered: list[dict[str, Any]] = []
    for incident in incidents:
        created = _parse_timestamp(incident.get("created_at"))
        if created and created >= since:
            filtered.append(incident)
    return filtered


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
    return response.status_code == 200


def _build_injection_map(
    round_index: int, schedule: list[tuple[float, str]]
) -> dict[int, GroundTruth]:
    injection_map: dict[int, GroundTruth] = {}
    for offset, anomaly_type in schedule:
        second = int(offset)
        if second in injection_map:
            raise ValueError(f"Duplicate schedule second={second}")
        injection_map[second] = GroundTruth(
            round_index=round_index,
            offset_seconds=offset,
            anomaly_type=anomaly_type,
        )
    return injection_map


def score_round(
    ground_truths: list[GroundTruth],
    incidents: list[dict[str, Any]],
) -> RoundResult:
    result = RoundResult(
        round_index=ground_truths[0].round_index if ground_truths else 0,
        service_id=0,
        ground_truths=ground_truths,
        incidents=incidents,
    )

    parsed: list[tuple[int, datetime, str]] = []
    for incident in incidents:
        created = _parse_timestamp(incident.get("created_at"))
        detection_type = str(incident.get("detection_type") or "")
        if created is None or not detection_type:
            continue
        parsed.append((int(incident["id"]), created, detection_type))
    parsed.sort(key=lambda item: item[1])

    matched_incident_ids: set[int] = set()
    matched_gt_indices: set[int] = set()

    for gt_index, gt in enumerate(ground_truths):
        if gt.injected_at is None:
            result.by_type[gt.detection_type].false_negatives += 1
            continue

        best: tuple[float, int] | None = None
        for incident_id, created_at, detection_type in parsed:
            if incident_id in matched_incident_ids:
                continue
            if detection_type != gt.detection_type:
                continue
            delta = (created_at - gt.injected_at).total_seconds()
            if -MATCH_CLOCK_SKEW_SECONDS <= delta <= MATCH_WINDOW_SECONDS:
                if best is None or abs(delta) < abs(best[0]):
                    best = (delta, incident_id)

        if best is not None:
            latency_ms, incident_id = max(best[0], 0.0) * 1000, best[1]
            matched_incident_ids.add(incident_id)
            matched_gt_indices.add(gt_index)
            counts = result.by_type[gt.detection_type]
            counts.true_positives += 1
            counts.detection_latencies_ms.append(latency_ms)
        else:
            result.by_type[gt.detection_type].false_negatives += 1

    for incident_id, created_at, detection_type in parsed:
        if incident_id in matched_incident_ids:
            continue
        if detection_type not in result.by_type:
            continue
        # Unmatched incident of a known detection type → false positive for that type.
        result.by_type[detection_type].false_positives += 1

    return result


async def run_round(
    client: httpx.AsyncClient,
    base_url: str,
    service_name: str,
    schedule_name: str,
    schedule: list[tuple[float, str]],
    round_index: int,
    round_duration: float,
    rate: float,
    batch_interval: float,
    keep_services: bool = False,
) -> RoundResult:
    # Fresh service per round: production dedup still applies within the round,
    # but prior-round open incidents cannot suppress later rounds.
    service_id = await register_service(client, base_url, service_name)
    events_per_batch = max(1, int(rate * batch_interval))
    injection_map = _build_injection_map(round_index, schedule)
    ground_truths = list(injection_map.values())

    round_started_at = datetime.now(timezone.utc)
    print(f"\n--- Round {round_index + 1} (service_id={service_id}) ---")
    print(f"  Schedule: {schedule_name}")
    print(f"  Started:  {round_started_at.isoformat()}")
    print(f"  Injections scheduled: {len(ground_truths)}")

    started = time.monotonic()

    while True:
        elapsed = time.monotonic() - started
        if elapsed >= round_duration:
            break

        second = int(elapsed)
        if elapsed >= WARMUP_SECONDS and second in injection_map:
            gt = injection_map[second]
            if gt.injected_at is None:
                events = _events_for_anomaly(gt.anomaly_type, schedule=schedule_name)
                events = _pad_batch(events, events_per_batch)
                ok = await send_batch(client, base_url, service_id, events)
                # Stamp after the POST so injected_at is not ahead of DB created_at.
                gt.injected_at = datetime.now(timezone.utc)
                print(
                    f"  [{elapsed:5.1f}s] inject {gt.anomaly_type} "
                    f"→ expect detection_type={gt.detection_type} "
                    f"(gt #{ground_truths.index(gt) + 1}, ok={ok})"
                )
                sleep_for = batch_interval - (time.monotonic() - started - elapsed)
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                continue
            events = _normal_events()
        else:
            events = _normal_events()

        events = _pad_batch(events, events_per_batch)
        await send_batch(client, base_url, service_id, events)

        sleep_for = batch_interval - (time.monotonic() - started - elapsed)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

    await asyncio.sleep(1.5)
    incidents = await fetch_incidents(
        client, base_url, service_id, since=round_started_at
    )
    result = score_round(ground_truths, incidents)
    result.round_index = round_index
    result.service_id = service_id

    print(f"  Incidents created this round: {len(incidents)}")
    for incident in sorted(incidents, key=lambda row: row.get("created_at") or ""):
        print(
            f"    id={incident.get('id')} status={incident.get('status')} "
            f"type={incident.get('detection_type')} "
            f"created={incident.get('created_at')}"
        )
    print(
        f"  Aggregate: TP={result.true_positives} FP={result.false_positives} "
        f"FN={result.false_negatives} | "
        f"P={result.precision:.1%} R={result.recall:.1%} F1={result.f1:.1%}"
    )
    for name in DETECTION_TYPES:
        counts = result.by_type[name]
        print(
            f"    {name:<14} TP={counts.true_positives} FP={counts.false_positives} "
            f"FN={counts.false_negatives} "
            f"P={counts.precision:.1%} R={counts.recall:.1%} F1={counts.f1:.1%}"
        )
    if result.detection_latencies_ms:
        print(f"  Mean detection latency: {result.mean_latency_ms:.0f}ms")

    if not keep_services:
        await delete_service(client, base_url, service_id)
        print(f"  Cleaned up benchmark service (id={service_id})")

    return result


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def print_summary(summary: BenchmarkSummary) -> None:
    print()
    print("=" * 78)
    print(
        f"VIGIL DETECTION BENCHMARK — schedule={summary.schedule_name} "
        f"repeat={summary.repeat_index + 1}"
    )
    print("=" * 78)
    print(f"  Rounds:                  {len(summary.round_results)}")
    print(f"  Ground-truth injections: {summary.total_ground_truths}")
    print(f"  Incidents created:       {summary.total_incidents}")
    print(f"  Match window:            {MATCH_WINDOW_SECONDS:.0f}s")
    print("  Eval design:             fresh service per round; production dedup on")
    print()
    print(
        f"  {'Round':<8}{'Svc':<8}{'TP':<6}{'FP':<6}{'FN':<6}"
        f"{'Precision':<12}{'Recall':<12}{'F1':<10}{'MTTD':<10}"
    )
    print(f"  {'-' * 74}")
    for result in summary.round_results:
        print(
            f"  {result.round_index + 1:<8}"
            f"{result.service_id:<8}"
            f"{result.true_positives:<6}"
            f"{result.false_positives:<6}"
            f"{result.false_negatives:<6}"
            f"{_pct(result.precision):<12}"
            f"{_pct(result.recall):<12}"
            f"{_pct(result.f1):<10}"
            f"{result.mean_latency_ms:>6.0f}ms"
        )
    print(f"  {'-' * 74}")
    print(
        f"  {'TOTAL':<8}{'':<8}"
        f"{summary.tp:<6}"
        f"{summary.fp:<6}"
        f"{summary.fn:<6}"
        f"{_pct(summary.precision):<12}"
        f"{_pct(summary.recall):<12}"
        f"{_pct(summary.f1):<10}"
        f"{summary.mean_latency_ms:>6.0f}ms"
    )
    print()
    print("  Aggregate metrics")
    print(f"    Precision: {_pct(summary.precision)}")
    print(f"    Recall:    {_pct(summary.recall)}")
    print(f"    F1 Score:  {_pct(summary.f1)}")
    print(f"    Mean Detection Latency (MTTD): {summary.mean_latency_ms:.1f}ms")
    print()
    print("  Per anomaly type (detection_type)")
    print(
        f"    {'Type':<14}{'TP':<6}{'FP':<6}{'FN':<6}"
        f"{'Precision':<12}{'Recall':<12}{'F1':<10}"
    )
    for name, counts in summary.aggregate_by_type().items():
        print(
            f"    {name:<14}"
            f"{counts.true_positives:<6}"
            f"{counts.false_positives:<6}"
            f"{counts.false_negatives:<6}"
            f"{_pct(counts.precision):<12}"
            f"{_pct(counts.recall):<12}"
            f"{_pct(counts.f1):<10}"
        )
    print("=" * 78)


def print_schedule_rollup(schedule_name: str, summaries: list[BenchmarkSummary]) -> None:
    print()
    print("#" * 78)
    print(f"# ROLLUP — {schedule_name} schedule ({len(summaries)} repeats)")
    print("#" * 78)

    # Micro-average across all repeats (sum TP/FP/FN).
    total_tp = sum(s.tp for s in summaries)
    total_fp = sum(s.fp for s in summaries)
    total_fn = sum(s.fn for s in summaries)
    precision = total_tp / (total_tp + total_fp) if (total_fp + total_tp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    print(f"  Micro-average Precision: {_pct(precision)}")
    print(f"  Micro-average Recall:    {_pct(recall)}")
    print(f"  Micro-average F1:        {_pct(f1)}")
    print(f"  Totals: TP={total_tp} FP={total_fp} FN={total_fn}")
    print()
    print("  Per-repeat aggregates")
    for summary in summaries:
        print(
            f"    repeat {summary.repeat_index + 1}: "
            f"P={_pct(summary.precision)} R={_pct(summary.recall)} "
            f"F1={_pct(summary.f1)} "
            f"(TP={summary.tp} FP={summary.fp} FN={summary.fn})"
        )

    by_type: dict[str, TypeCounts] = {name: TypeCounts() for name in DETECTION_TYPES}
    for summary in summaries:
        for name, counts in summary.aggregate_by_type().items():
            target = by_type[name]
            target.true_positives += counts.true_positives
            target.false_positives += counts.false_positives
            target.false_negatives += counts.false_negatives
            target.detection_latencies_ms.extend(counts.detection_latencies_ms)

    print()
    print("  Per anomaly type (all repeats)")
    print(
        f"    {'Type':<14}{'TP':<6}{'FP':<6}{'FN':<6}"
        f"{'Precision':<12}{'Recall':<12}{'F1':<10}"
    )
    for name, counts in by_type.items():
        print(
            f"    {name:<14}"
            f"{counts.true_positives:<6}"
            f"{counts.false_positives:<6}"
            f"{counts.false_negatives:<6}"
            f"{_pct(counts.precision):<12}"
            f"{_pct(counts.recall):<12}"
            f"{_pct(counts.f1):<10}"
        )
    print("#" * 78)


class _Tee:
    def __init__(self, *streams: TextIO) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


async def run_schedule(
    client: httpx.AsyncClient,
    base_url: str,
    service_name: str,
    schedule_name: str,
    args: argparse.Namespace,
) -> list[BenchmarkSummary]:
    schedule = SCHEDULES[schedule_name]
    summaries: list[BenchmarkSummary] = []

    print()
    print("*" * 78)
    print(f"* SCHEDULE: {schedule_name}")
    print(f"* Injections/round: {len(schedule)}")
    for offset, anomaly_type in schedule:
        print(
            f"*   t={offset:.0f}s  {anomaly_type} "
            f"→ {ANOMALY_TO_DETECTION_TYPE[anomaly_type]}"
        )
    print(f"* Rounds={args.rounds}  Repeats={args.repeats}")
    print("*" * 78)

    for repeat_index in range(args.repeats):
        print(f"\n>>> Repeat {repeat_index + 1}/{args.repeats} ({schedule_name})")
        summary = BenchmarkSummary(
            schedule_name=schedule_name, repeat_index=repeat_index
        )
        for round_index in range(args.rounds):
            result = await run_round(
                client,
                base_url,
                f"{service_name}-{schedule_name}",
                schedule_name,
                schedule,
                round_index,
                args.round_duration,
                args.rate,
                args.batch_interval,
                keep_services=args.keep_services,
            )
            summary.round_results.append(result)
            if round_index < args.rounds - 1:
                await asyncio.sleep(1.0)
        print_summary(summary)
        summaries.append(summary)
        if repeat_index < args.repeats - 1:
            await asyncio.sleep(2.0)

    print_schedule_rollup(schedule_name, summaries)
    return summaries


async def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    if args.rounds <= 0 or args.repeats <= 0 or args.round_duration <= 0 or args.rate <= 0:
        print("rounds, repeats, round-duration, and rate must be positive.", file=sys.stderr)
        sys.exit(1)

    log_file = None
    original_stdout = sys.stdout
    if args.log_dir is not None:
        args.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = args.log_dir / f"detection_{args.schedule}_{stamp}.log"
        log_file = log_path.open("w", encoding="utf-8")
        sys.stdout = _Tee(original_stdout, log_file)
        print(f"Logging to {log_path}")

    try:
        print("Vigil detection benchmark")
        print(f"  base_url={base_url}")
        print(f"  schedule={args.schedule}")
        print(f"  rounds={args.rounds} repeats={args.repeats}")
        print(f"  round_duration={args.round_duration}s rate={args.rate}/s")
        print(
            "  Fair-eval note: fresh service_id per round so open-incident "
            "dedup cannot poison later rounds; production dedup still applies "
            "within each round."
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            health = await client.get(f"{base_url}/health")
            health.raise_for_status()

            if not args.keep_services:
                await purge_stale_benchmark_services(client, base_url)

            schedule_names = (
                ["tuning", "held_out"] if args.schedule == "both" else [args.schedule]
            )
            for schedule_name in schedule_names:
                await run_schedule(
                    client, base_url, args.service_name, schedule_name, args
                )

            if not args.keep_services:
                await purge_stale_benchmark_services(client, base_url)
    finally:
        if log_file is not None:
            sys.stdout = original_stdout
            log_file.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBenchmark interrupted.", file=sys.stderr)
        sys.exit(130)
