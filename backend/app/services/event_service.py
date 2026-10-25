from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event
from app.schemas.schemas import EventCreate, EventRead
from app.services import metric_service, service_service


async def create(db: AsyncSession, service_id: int, data: EventCreate) -> Event:
    event = Event(
        service_id=service_id,
        level=data.level,
        message=data.message,
        payload=data.payload,
        source=data.source,
    )
    db.add(event)
    await db.flush()

    if data.level == "METRIC" and data.payload:
        await metric_service.create_from_event_payload(db, service_id, data.payload)

    await service_service.update_last_seen(db, service_id, commit=False)
    await db.commit()
    await db.refresh(event)
    return event


async def create_batch(
    db: AsyncSession,
    service_id: int,
    events: list[EventCreate],
) -> list[Event]:
    created: list[Event] = []

    for data in events:
        event = Event(
            service_id=service_id,
            level=data.level,
            message=data.message,
            payload=data.payload,
            source=data.source,
        )
        db.add(event)
        created.append(event)

        if data.level == "METRIC" and data.payload:
            await metric_service.create_from_event_payload(
                db, service_id, data.payload
            )

    if created:
        await service_service.update_last_seen(db, service_id, commit=False)
        await db.commit()
        for event in created:
            await db.refresh(event)

    return created


async def list_by_service(
    db: AsyncSession,
    service_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    level: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[EventRead], int]:
    filters = [Event.service_id == service_id]
    if level is not None:
        filters.append(Event.level == level)
    if since is not None:
        filters.append(Event.timestamp >= since)
    if until is not None:
        filters.append(Event.timestamp <= until)

    count_stmt = select(func.count()).select_from(Event).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Event)
        .where(*filters)
        .order_by(Event.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [EventRead.model_validate(event) for event in events], total


async def get_recent_for_service(
    db: AsyncSession,
    service_id: int,
    *,
    limit: int = 20,
) -> list[EventRead]:
    stmt = (
        select(Event)
        .where(Event.service_id == service_id)
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [EventRead.model_validate(event) for event in events]


async def get_recent_for_detection(
    db: AsyncSession,
    service_id: int,
    *,
    window_seconds: int = 60,
) -> list[dict]:
    # Naive UTC throughout — do not use .timestamp() on utcnow() (interprets as local time).
    cutoff_dt = datetime.utcnow() - timedelta(seconds=window_seconds)

    stmt = (
        select(Event)
        .where(
            Event.service_id == service_id,
            Event.timestamp >= cutoff_dt,
        )
        .order_by(Event.timestamp.desc())
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        {
            "level": event.level,
            "message": event.message,
            "timestamp": event.timestamp or datetime.utcnow(),
        }
        for event in events
    ]


async def list_for_incident_timeline(
    db: AsyncSession,
    service_id: int,
    started_at: datetime,
    *,
    end_at: datetime | None = None,
) -> list[EventRead]:
    filters = [
        Event.service_id == service_id,
        Event.timestamp >= started_at,
    ]
    if end_at is not None:
        filters.append(Event.timestamp <= end_at)

    stmt = select(Event).where(*filters).order_by(Event.timestamp.asc())
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [EventRead.model_validate(event) for event in events]
