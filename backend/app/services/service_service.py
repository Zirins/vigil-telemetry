from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Incident, Metric, Service
from app.schemas.schemas import (
    IncidentRead,
    ServiceCreate,
    ServiceDetail,
    ServiceListItem,
)

from app.services import event_service, incident_service

_OPEN_STATUSES = ("open", "investigating")
_SEVERITY_RANK = {"P1": 1, "P2": 2, "P3": 3}
_RANK_TO_SEVERITY = {1: "P1", 2: "P2", 3: "P3"}
_DASHBOARD_METRICS = ("latency_p99", "latency_ms", "error_rate")


def derive_service_status(
    open_count: int,
    highest_severity: str | None,
    latest_error_rate: Decimal | float | None,
    latest_latency_p99: Decimal | float | None,
    fallback_status: str | None = None,
) -> str:
    """
    Derives operational service status dynamically from real-time incidents and telemetry
    rather than trusting an unmanaged or stale database column.
    """
    if open_count > 0:
        if highest_severity == "P1":
            return "down"
        return "degraded"

    if latest_error_rate is not None:
        try:
            err = float(latest_error_rate)
            if err >= 0.10:
                return "down"
            if err >= 0.015:  # >= 1.5% error rate is degraded
                return "degraded"
        except (ValueError, TypeError):
            pass

    if latest_latency_p99 is not None:
        try:
            lat = float(latest_latency_p99)
            if lat >= 2000:
                return "down"
            if lat >= 600:
                return "degraded"
        except (ValueError, TypeError):
            pass

    if fallback_status in ("down", "degraded"):
        return fallback_status

    return "healthy"


async def list_services(
    db: AsyncSession,
    environment: str | None = None,
    include_benchmark: bool = False,
) -> list[ServiceListItem]:
    """
    Single round-trip list query: open counts, latest dashboard metrics, and
    highest active severity are joined via window-function subqueries (not N+1).
    Status is dynamically derived from real-time telemetry and active incidents.
    """
    open_count_subq = (
        select(func.count(Incident.id))
        .where(
            Incident.service_id == Service.id,
            Incident.status.in_(_OPEN_STATUSES),
        )
        .correlate(Service)
        .scalar_subquery()
    )

    severity_rank = case(
        (Incident.severity == "P1", 1),
        (Incident.severity == "P2", 2),
        (Incident.severity == "P3", 3),
        else_=99,
    )

    ranked_metrics = (
        select(
            Metric.service_id.label("service_id"),
            Metric.metric_name.label("metric_name"),
            Metric.value.label("value"),
            func.row_number()
            .over(
                partition_by=(Metric.service_id, Metric.metric_name),
                order_by=Metric.timestamp.desc(),
            )
            .label("rn"),
        )
        .where(Metric.metric_name.in_(_DASHBOARD_METRICS))
        .subquery("ranked_metrics")
    )

    latest_metrics = (
        select(
            ranked_metrics.c.service_id,
            func.coalesce(
                func.max(
                    case(
                        (
                            ranked_metrics.c.metric_name == "latency_p99",
                            ranked_metrics.c.value,
                        ),
                    )
                ),
                func.max(
                    case(
                        (
                            ranked_metrics.c.metric_name == "latency_ms",
                            ranked_metrics.c.value,
                        ),
                    )
                ),
            ).label("latest_latency_p99"),
            func.max(
                case(
                    (
                        ranked_metrics.c.metric_name == "error_rate",
                        ranked_metrics.c.value,
                    ),
                )
            ).label("latest_error_rate"),
        )
        .where(ranked_metrics.c.rn == 1)
        .group_by(ranked_metrics.c.service_id)
        .subquery("latest_metrics")
    )

    highest_severity = (
        select(
            Incident.service_id.label("service_id"),
            func.min(severity_rank).label("min_severity_rank"),
        )
        .where(
            Incident.status.in_(_OPEN_STATUSES),
            Incident.severity.is_not(None),
        )
        .group_by(Incident.service_id)
        .subquery("highest_severity")
    )

    stmt = (
        select(
            Service,
            open_count_subq.label("open_incident_count"),
            latest_metrics.c.latest_latency_p99,
            latest_metrics.c.latest_error_rate,
            highest_severity.c.min_severity_rank,
        )
        .outerjoin(latest_metrics, latest_metrics.c.service_id == Service.id)
        .outerjoin(highest_severity, highest_severity.c.service_id == Service.id)
    )

    if environment:
        stmt = stmt.where(Service.environment == environment)
    elif not include_benchmark:
        stmt = stmt.where(Service.environment != "benchmark")

    stmt = stmt.order_by(Service.name)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        ServiceListItem(
            id=service.id,
            name=service.name,
            environment=service.environment or "production",
            description=service.description,
            status=derive_service_status(
                open_count=open_count or 0,
                highest_severity=_RANK_TO_SEVERITY.get(min_rank)
                if min_rank is not None and min_rank in _RANK_TO_SEVERITY
                else None,
                latest_error_rate=latest_error_rate,
                latest_latency_p99=latest_latency_p99,
                fallback_status=service.status,
            ),
            last_seen_at=service.last_seen_at,
            created_at=service.created_at,
            open_incident_count=open_count or 0,
            latest_latency_p99=latest_latency_p99,
            latest_error_rate=latest_error_rate,
            highest_open_severity=_RANK_TO_SEVERITY.get(min_rank)
            if min_rank is not None and min_rank in _RANK_TO_SEVERITY
            else None,
        )
        for service, open_count, latest_latency_p99, latest_error_rate, min_rank in rows
    ]


async def get_by_id(db: AsyncSession, service_id: int) -> Service | None:
    result = await db.execute(select(Service).where(Service.id == service_id))
    return result.scalar_one_or_none()


async def get_detail(db: AsyncSession, service_id: int) -> ServiceDetail | None:
    service = await get_by_id(db, service_id)
    if service is None:
        return None

    recent_events = await event_service.get_recent_for_service(db, service_id, limit=20)
    active_incidents = await incident_service.list_active_by_service(db, service_id)
    recent_incident_count = await incident_service.count_open_by_service(db, service_id)

    highest_sev = None
    min_rank = 99
    for inc in active_incidents:
        if inc.severity and inc.severity in _SEVERITY_RANK:
            rank = _SEVERITY_RANK[inc.severity]
            if rank < min_rank:
                min_rank = rank
                highest_sev = inc.severity

    # Fetch latest metrics for derived status consistency
    latest_err = None
    latest_lat = None
    metric_rows = (
        await db.execute(
            select(Metric.metric_name, Metric.value)
            .where(
                Metric.service_id == service_id,
                Metric.metric_name.in_(_DASHBOARD_METRICS),
            )
            .order_by(Metric.timestamp.desc())
            .limit(10)
        )
    ).all()
    for m_name, m_val in metric_rows:
        if m_name == "error_rate" and latest_err is None:
            latest_err = m_val
        elif m_name in ("latency_p99", "latency_ms") and latest_lat is None:
            latest_lat = m_val

    derived_status = derive_service_status(
        open_count=recent_incident_count,
        highest_severity=highest_sev,
        latest_error_rate=latest_err,
        latest_latency_p99=latest_lat,
        fallback_status=service.status,
    )

    return ServiceDetail(
        id=service.id,
        name=service.name,
        environment=service.environment or "production",
        description=service.description,
        status=derived_status,
        last_seen_at=service.last_seen_at,
        created_at=service.created_at,
        recent_incident_count=recent_incident_count,
        recent_events=recent_events,
        active_incidents=[
            IncidentRead.model_validate(incident) for incident in active_incidents
        ],
    )


async def create(db: AsyncSession, data: ServiceCreate) -> Service:
    service = Service(
        name=data.name,
        environment=data.environment,
        description=data.description,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


async def delete_service(db: AsyncSession, service_id: int) -> bool:
    service = await get_by_id(db, service_id)
    if service is None:
        return False
    await db.delete(service)
    await db.commit()
    return True


async def update_status(
    db: AsyncSession, service_id: int, status: str
) -> Service | None:
    service = await get_by_id(db, service_id)
    if service is None:
        return None

    service.status = status
    await db.commit()
    await db.refresh(service)
    return service


async def update_last_seen(
    db: AsyncSession,
    service_id: int,
    seen_at: datetime | None = None,
    *,
    commit: bool = True,
) -> None:
    service = await get_by_id(db, service_id)
    if service is None:
        return

    service.last_seen_at = seen_at or datetime.utcnow()
    if commit:
        await db.commit()
