#!/usr/bin/env python3
"""
Reset demo data for local dashboards without calling Claude.

- Ensures a believable multi-service fleet (5 healthy, 1 degraded)
- Deduplicates open incidents (only 1 realistic P2 incident on payment-service)
- Eliminates synthetic benchmark clutter and test harness artifacts
- Seeds metric + event history with realistic P99 latencies and SLO error rates
- Sets fresh heartbeats (< 30s ago) with zero time drift
- Writes static AI report fields directly (no API credits)

Run from project root:
    python backend/scripts/reset_demo_data.py
    python backend/scripts/reset_demo_data.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.models import Event, Incident, Metric, Service  # noqa: E402

_OPEN_STATUSES = ("open", "investigating")
_SEVERITIES = ("P1", "P2", "P3")

_DEMO_SERVICES = [
    {
        "name": "api-gateway",
        "environment": "production",
        "status": "healthy",
        "description": "Edge reverse proxy and ingress routing layer",
        "base_latency": 42.0,
    },
    {
        "name": "payment-service",
        "environment": "production",
        "status": "degraded",
        "description": "Core payment processing and checkout pipeline",
        "base_latency": 210.0,
    },
    {
        "name": "auth-service",
        "environment": "production",
        "status": "healthy",
        "description": "OAuth2 authentication and session verification",
        "base_latency": 54.0,
    },
    {
        "name": "order-service",
        "environment": "production",
        "status": "healthy",
        "description": "Order state machine and fulfillment engine",
        "base_latency": 72.0,
    },
    {
        "name": "inventory-service",
        "environment": "production",
        "status": "healthy",
        "description": "Warehouse inventory and stock reservations",
        "base_latency": 63.0,
    },
    {
        "name": "notification-worker",
        "environment": "production",
        "status": "healthy",
        "description": "Async transactional email, SMS, and webhook delivery",
        "base_latency": 95.0,
    },
]

_STATIC_AI = {
    "ai_summary": (
        "Elevated error rate and metric spikes correlated with downstream database "
        "connection pool timeouts during payment batch checkout."
    ),
    "ai_root_cause": (
        "Connection pool saturation on the primary database caused retry storms and "
        "latency amplification on payment verification paths."
    ),
    "ai_affected_components": ["db-pool", "payment-api", "stripe-adapter"],
    "ai_remediation_steps": [
        "Scale connection pool max size and verify pool wait metrics.",
        "Enable circuit breaker on external payment provider calls.",
        "Roll back the last deployment if error rate remains above SLO for 10 minutes.",
    ],
    "ai_confidence": Decimal("0.88"),
}


def _jitter(
    center: float,
    sigma: float,
    *,
    low: float | None = None,
    high: float | None = None,
    digits: int = 4,
) -> float:
    value = random.gauss(center, sigma)
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return round(value, digits)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset Vigil demo data without AI API calls.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without committing changes.",
    )
    return parser.parse_args()


async def reset_demo_data(*, dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        services = await _ensure_demo_services(db, now)

        # Clean up any orphaned open incidents
        open_incidents = (
            await db.execute(
                select(Incident)
                .where(Incident.status.in_(_OPEN_STATUSES))
                .order_by(Incident.service_id, Incident.detection_type, Incident.started_at)
            )
        ).scalars().all()

        groups: dict[tuple[int, str | None], list[Incident]] = defaultdict(list)
        for incident in open_incidents:
            groups[(incident.service_id, incident.detection_type)].append(incident)

        resolved_duplicates = 0
        kept: list[Incident] = []

        for (_service_id, _detection_type), incidents in groups.items():
            incidents.sort(key=lambda row: row.started_at or row.created_at or now)
            keeper = incidents[0]
            kept.append(keeper)
            for duplicate in incidents[1:]:
                duplicate.status = "resolved"
                duplicate.resolved_at = now
                duplicate.postmortem = (
                    "Auto-resolved during demo reset because it duplicated an existing open incident."
                )
                resolved_duplicates += 1

        # Keep open incident only on payment-service error_rate
        payment_svc = next((s for s in services if s.name == "payment-service"), None)
        for inc in kept:
            if payment_svc and inc.service_id == payment_svc.id and inc.detection_type == "error_rate":
                continue
            inc.status = "resolved"
            inc.resolved_at = now
            resolved_duplicates += 1

        await _ensure_open_incidents(db, services, kept, now)

        all_open = (
            await db.execute(
                select(Incident)
                .where(Incident.status.in_(_OPEN_STATUSES))
                .order_by(Incident.started_at.desc())
            )
        ).scalars().all()

        open_counts: dict[int, int] = defaultdict(int)
        for incident in all_open:
            open_counts[incident.service_id] += 1

        for service in services:
            open_count = open_counts.get(service.id, 0)
            if open_count == 0:
                service.status = "healthy"
            elif open_count == 1:
                service.status = "degraded"
            else:
                service.status = "down" if open_count >= 3 else "degraded"

        service_ids = [service.id for service in services]
        await _clear_demo_telemetry(db, service_ids)
        await _seed_metrics_and_events(db, services, now)
        _align_incident_timelines(services, all_open, now)

        # Fresh heartbeats within seconds (zero time drift)
        for service in services:
            service.last_seen_at = now - timedelta(seconds=random.randint(4, 26))

        healthy = sum(1 for service in services if service.status == "healthy")
        degraded = sum(1 for service in services if service.status in ("degraded", "down"))

        if dry_run:
            await db.rollback()
            print(
                f"[dry-run] would resolve {resolved_duplicates} duplicate incidents, "
                f"maintain {len(all_open)} open incidents across {len(services)} services "
                f"({healthy} healthy, {degraded} degraded/down)"
            )
            return

        await db.commit()
        print(
            f"Reset complete: {len(services)} operational services ({healthy} healthy, {degraded} degraded). "
            f"Active incidents: {len(all_open)}."
        )


async def _ensure_demo_services(db, now: datetime) -> list[Service]:
    demo_names = {spec["name"] for spec in _DEMO_SERVICES}
    all_current = (await db.execute(select(Service))).scalars().all()

    # Cascade-delete all non-demo services (benchmark, throughput, test harness)
    for svc in all_current:
        if svc.name not in demo_names:
            await db.delete(svc)
    await db.flush()

    existing = {
        service.name: service
        for service in (await db.execute(select(Service))).scalars().all()
    }
    services: list[Service] = []

    for spec in _DEMO_SERVICES:
        service = existing.get(spec["name"])
        if service is None:
            service = Service(
                name=spec["name"],
                environment=spec["environment"],
                description=spec["description"],
                status=spec["status"],
                last_seen_at=now - timedelta(seconds=random.randint(5, 25)),
            )
            db.add(service)
            await db.flush()
        else:
            service.environment = spec["environment"]
            service.description = spec["description"]
            service.status = spec["status"]
            service.last_seen_at = now - timedelta(seconds=random.randint(5, 25))
        services.append(service)

    return services


async def _ensure_open_incidents(
    db,
    services: list[Service],
    kept: list[Incident],
    now: datetime,
) -> None:
    """Ensure payment-service has exactly one open incident with rich postmortem."""
    kept_keys = {
        (incident.service_id, incident.detection_type) for incident in kept
        if incident.status in _OPEN_STATUSES
    }
    payment_svc = next((s for s in services if s.name == "payment-service"), None)
    if not payment_svc:
        return

    key = (payment_svc.id, "error_rate")
    if key not in kept_keys:
        incident = Incident(
            service_id=payment_svc.id,
            title="Elevated error rate and connection pool saturation",
            status="investigating",
            severity="P2",
            detection_type="error_rate",
            started_at=now - timedelta(minutes=14),
            ai_summary=_STATIC_AI["ai_summary"],
            ai_root_cause=_STATIC_AI["ai_root_cause"],
            ai_affected_components=_STATIC_AI["ai_affected_components"],
            ai_remediation_steps=_STATIC_AI["ai_remediation_steps"],
            ai_confidence=_STATIC_AI["ai_confidence"],
            ai_analysis_status="completed",
            ai_analyzed_at=now - timedelta(minutes=2),
        )
        db.add(incident)


async def _clear_demo_telemetry(db, service_ids: list[int]) -> None:
    if not service_ids:
        return
    await db.execute(delete(Event).where(Event.service_id.in_(service_ids)))
    await db.execute(delete(Metric).where(Metric.service_id.in_(service_ids)))


def _align_incident_timelines(
    services: list[Service],
    incidents: list[Incident],
    now: datetime,
) -> None:
    """Align payment-service incident + AI analysis timestamps."""
    service_by_id = {service.id: service for service in services}

    for incident in incidents:
        service = service_by_id.get(incident.service_id)
        if service and service.name == "payment-service":
            incident.started_at = now - timedelta(minutes=14)
            incident.severity = "P2"
            incident.status = "investigating"
            incident.ai_summary = _STATIC_AI["ai_summary"]
            incident.ai_root_cause = _STATIC_AI["ai_root_cause"]
            incident.ai_affected_components = _STATIC_AI["ai_affected_components"]
            incident.ai_remediation_steps = _STATIC_AI["ai_remediation_steps"]
            incident.ai_confidence = _STATIC_AI["ai_confidence"]
            incident.ai_analysis_status = "completed"
            incident.ai_analyzed_at = now - timedelta(minutes=2)


async def _seed_metrics_and_events(
    db,
    services: list[Service],
    now: datetime,
) -> None:
    spec_by_name = {spec["name"]: spec for spec in _DEMO_SERVICES}

    for index, service in enumerate(services):
        spec = spec_by_name.get(service.name, {})
        base_latency = spec.get("base_latency", 50.0)
        is_degraded = service.name == "payment-service"

        for point in range(20):
            # 20 discrete points spanning the last 20 minutes right up to now
            seconds_ago = (19 - point) * 60 + random.randint(0, 8)
            ts = now - timedelta(seconds=seconds_ago)

            if is_degraded:
                # Realistic degradation curve for payment-service
                if point < 13:
                    error_rate = _jitter(0.012, 0.0015, low=0.008, high=0.018)
                    latency = _jitter(base_latency * 0.75, 8.0, low=110.0, high=160.0, digits=1)
                    cpu = _jitter(42.0, 3.0, low=30.0, high=55.0, digits=1)
                else:
                    error_rate = _jitter(0.038, 0.003, low=0.031, high=0.046)
                    latency = _jitter(base_latency, 12.0, low=180.0, high=245.0, digits=1)
                    cpu = _jitter(82.0, 4.0, low=72.0, high=94.0, digits=1)
            else:
                # Stable enterprise health: 99.9% SLO compliance, low P99
                healthy_target = 0.0008 + (index * 0.0003)
                error_rate = _jitter(healthy_target, 0.00015, low=0.0001, high=0.0025)
                latency = _jitter(base_latency, 2.5, low=max(20.0, base_latency - 8.0), high=base_latency + 10.0, digits=1)
                cpu = _jitter(22.0 + index * 4.0, 2.0, low=12.0, high=48.0, digits=1)

            error_decimal = Decimal(str(error_rate))
            latency_decimal = Decimal(str(latency))

            db.add(
                Metric(
                    service_id=service.id,
                    metric_name="latency_p99",
                    value=latency_decimal,
                    unit="ms",
                    timestamp=ts,
                )
            )
            db.add(
                Metric(
                    service_id=service.id,
                    metric_name="error_rate",
                    value=error_decimal,
                    unit="ratio",
                    timestamp=ts,
                )
            )
            db.add(
                Event(
                    service_id=service.id,
                    level="METRIC",
                    source="system",
                    payload={
                        "metric": "cpu_pct",
                        "value": cpu,
                        "unit": "percent",
                    },
                    timestamp=ts,
                )
            )
            db.add(
                Event(
                    service_id=service.id,
                    level="METRIC",
                    source="system",
                    payload={
                        "metric": "error_rate",
                        "value": error_rate,
                        "unit": "ratio",
                    },
                    timestamp=ts,
                )
            )


async def main() -> None:
    args = parse_args()
    try:
        await reset_demo_data(dry_run=args.dry_run)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
