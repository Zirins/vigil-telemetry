from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric
from app.schemas.schemas import MetricCreate, MetricRead


async def create(db: AsyncSession, data: MetricCreate) -> Metric:
    metric = Metric(
        service_id=data.service_id,
        metric_name=data.metric_name,
        value=data.value,
        unit=data.unit,
    )
    db.add(metric)
    await db.flush()
    await db.refresh(metric)
    return metric


async def create_from_event_payload(
    db: AsyncSession,
    service_id: int,
    payload: dict[str, Any],
) -> Metric | None:
    metric_name = payload.get("metric")
    raw_value = payload.get("value")
    if metric_name is None or raw_value is None:
        return None

    return await create(
        db,
        MetricCreate(
            service_id=service_id,
            metric_name=str(metric_name),
            value=Decimal(str(raw_value)),
            unit=payload.get("unit"),
        ),
    )


async def list_by_service(
    db: AsyncSession,
    service_id: int,
    *,
    metric_name: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> tuple[list[MetricRead], int]:
    filters = [Metric.service_id == service_id]
    if metric_name is not None:
        filters.append(Metric.metric_name == metric_name)

    count_stmt = select(func.count()).select_from(Metric).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Metric)
        .where(*filters)
        .order_by(Metric.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    metrics = result.scalars().all()

    return [MetricRead.model_validate(metric) for metric in metrics], total


async def get_recent_by_names(
    db: AsyncSession,
    service_id: int,
    metric_names: list[str],
    *,
    limit: int = 60,
) -> list[MetricRead]:
    if not metric_names:
        return []

    stmt = (
        select(Metric)
        .where(
            Metric.service_id == service_id,
            Metric.metric_name.in_(metric_names),
        )
        .order_by(Metric.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    metrics = result.scalars().all()
    return [MetricRead.model_validate(metric) for metric in metrics]
