from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Alert, Incident, Service
from app.schemas.schemas import (
    AlertCreate,
    AlertRead,
    IncidentCreate,
    IncidentDetail,
    IncidentRead,
)

_OPEN_STATUSES = ("open", "investigating")


async def list_incidents(
    db: AsyncSession,
    *,
    status: str | None = None,
    service_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[IncidentRead], int]:
    filters = []
    if status is not None:
        filters.append(Incident.status == status)
    if service_id is not None:
        filters.append(Incident.service_id == service_id)

    count_stmt = select(func.count()).select_from(Incident)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Incident, Service.name.label("service_name"))
        .join(Service, Service.id == Incident.service_id)
        .order_by(Incident.started_at.desc())
    )
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()
    return [
        IncidentRead.model_validate(incident).model_copy(
            update={"service_name": service_name}
        )
        for incident, service_name in rows
    ], total


async def get_by_id(db: AsyncSession, incident_id: int) -> Incident | None:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    return result.scalar_one_or_none()


async def get_open_incident(
    db: AsyncSession, service_id: int, detection_type: str
) -> Incident | None:
    stmt = (
        select(Incident)
        .where(
            Incident.service_id == service_id,
            Incident.detection_type == detection_type,
            Incident.status.in_(_OPEN_STATUSES),
        )
        .order_by(Incident.started_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_detail(db: AsyncSession, incident_id: int) -> IncidentDetail | None:
    stmt = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.alerts))
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()
    if incident is None:
        return None

    return IncidentDetail(
        id=incident.id,
        service_id=incident.service_id,
        title=incident.title,
        status=incident.status or "open",
        severity=incident.severity,
        detection_type=incident.detection_type,
        started_at=incident.started_at,
        resolved_at=incident.resolved_at,
        postmortem=incident.postmortem,
        created_at=incident.created_at,
        ai_summary=incident.ai_summary,
        ai_root_cause=incident.ai_root_cause,
        ai_affected_components=incident.ai_affected_components,
        ai_remediation_steps=incident.ai_remediation_steps,
        ai_confidence=incident.ai_confidence,
        ai_analyzed_at=incident.ai_analyzed_at,
        ai_analysis_status=incident.ai_analysis_status,
        alerts=[AlertRead.model_validate(alert) for alert in incident.alerts],
    )


async def create(db: AsyncSession, data: IncidentCreate) -> Incident:
    incident = await _insert_incident(db, data)
    if incident is None:
        raise RuntimeError(
            "Active incident already exists for this service and detection type"
        )
    return incident


async def create_open(db: AsyncSession, data: IncidentCreate) -> Incident | None:
    """
    Insert an open incident, or return None when an active duplicate exists.

    App-level checks are not race-safe; a partial unique index enforces dedup at
    commit time. IntegrityError here means a concurrent request won the insert.
    """
    return await _insert_incident(db, data)


async def _insert_incident(
    db: AsyncSession, data: IncidentCreate
) -> Incident | None:
    incident = Incident(
        service_id=data.service_id,
        title=data.title,
        status=data.status or "open",
        severity=data.severity,
        detection_type=data.detection_type,
    )
    db.add(incident)
    try:
        await db.commit()
        await db.refresh(incident)
        return incident
    except IntegrityError:
        await db.rollback()
        return None


async def resolve(
    db: AsyncSession,
    incident_id: int,
    postmortem: str | None = None,
) -> Incident | None:
    incident = await get_by_id(db, incident_id)
    if incident is None:
        return None

    incident.status = "resolved"
    incident.resolved_at = datetime.utcnow()
    if postmortem is not None:
        incident.postmortem = postmortem

    await db.commit()
    await db.refresh(incident)
    return incident


async def get_most_recent_created_at(
    db: AsyncSession, service_id: int
) -> datetime | None:
    stmt = (
        select(Incident.created_at)
        .where(Incident.service_id == service_id)
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_open_by_service(db: AsyncSession, service_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.service_id == service_id,
            Incident.status.in_(_OPEN_STATUSES),
        )
    )
    return (await db.execute(stmt)).scalar_one()


async def list_active_by_service(
    db: AsyncSession, service_id: int
) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(
            Incident.service_id == service_id,
            Incident.status.in_(_OPEN_STATUSES),
        )
        .order_by(Incident.started_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_alert(db: AsyncSession, data: AlertCreate) -> Alert:
    alert = Alert(
        incident_id=data.incident_id,
        service_id=data.service_id,
        rule=data.rule,
        threshold_value=data.threshold_value,
        observed_value=data.observed_value,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def update_ai_analysis(
    db: AsyncSession,
    incident_id: int,
    *,
    ai_summary: str,
    ai_root_cause: str,
    ai_affected_components: list[str],
    ai_remediation_steps: list[str],
    ai_confidence: Decimal,
) -> Incident | None:
    incident = await get_by_id(db, incident_id)
    if incident is None:
        return None

    incident.ai_summary = ai_summary
    incident.ai_root_cause = ai_root_cause
    incident.ai_affected_components = ai_affected_components
    incident.ai_remediation_steps = ai_remediation_steps
    incident.ai_confidence = ai_confidence
    incident.ai_analyzed_at = datetime.utcnow()
    incident.ai_analysis_status = "completed"
    incident.ai_analysis_error = None

    await db.commit()
    await db.refresh(incident)
    return incident


async def set_ai_analysis_status(
    db: AsyncSession,
    incident_id: int,
    status: str,
    *,
    error: str | None = None,
) -> Incident | None:
    incident = await get_by_id(db, incident_id)
    if incident is None:
        return None

    incident.ai_analysis_status = status
    incident.ai_analysis_error = error
    await db.commit()
    await db.refresh(incident)
    return incident
