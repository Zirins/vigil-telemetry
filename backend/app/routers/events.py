from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import Event, Service
from app.routers.helpers import error_response
from app.schemas.schemas import (
    AlertCreate,
    EventBatchIngest,
    EventListResponse,
    EventRead,
    IncidentCreate,
)
from app.services import detection, event_service, incident_service, service_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Hold references so asyncio tasks are not garbage-collected mid-flight.
_ai_tasks: set[asyncio.Task[None]] = set()


def _parse_since(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _anomaly_title(anomaly: dict[str, Any]) -> str:
    detection_type = anomaly.get("type", "anomaly")
    metric = anomaly.get("metric")
    if metric:
        return f"{detection_type} detected on {metric}"
    return f"{detection_type} detected"


def _anomaly_observed(anomaly: dict[str, Any]) -> Decimal | None:
    for key in ("observed", "error_rate", "occurrences"):
        value = anomaly.get(key)
        if value is not None:
            return Decimal(str(value))
    return None


def _anomaly_threshold(anomaly: dict[str, Any]) -> Decimal | None:
    value = anomaly.get("threshold")
    if value is not None:
        return Decimal(str(value))
    return None


async def _run_ai_analysis(incident_id: int, service_id: int) -> None:
    """Load real nlp module and persist Claude analysis for the incident."""
    nlp_service = importlib.import_module("app.services.nlp")
    if not getattr(nlp_service, "__file__", None):
        logger.error(
            "app.services.nlp is a stub without implementation; "
            "AI analysis skipped for incident %s",
            incident_id,
        )
        return

    logger.info(
        "Starting AI analysis for incident %s (service %s)", incident_id, service_id
    )
    try:
        await nlp_service.analyze_incident(incident_id, service_id)
        logger.info("Completed AI analysis for incident %s", incident_id)
    except Exception as exc:
        logger.exception("AI analysis failed for incident %s", incident_id)
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await incident_service.set_ai_analysis_status(
                db,
                incident_id,
                "failed",
                error=str(exc)[:1000],
            )


def _schedule_ai_analysis(incident_id: int, service_id: int) -> None:
    """Fire-and-forget async task — more reliable than BackgroundTasks for long API calls."""
    if not settings.ENABLE_LIVE_AI_ANALYSIS:
        logger.info(
            "Skipping live AI analysis for incident %s (service %s) [ENABLE_LIVE_AI_ANALYSIS=false]",
            incident_id,
            service_id,
        )
        return

    task = asyncio.create_task(_run_ai_analysis(incident_id, service_id))
    _ai_tasks.add(task)
    task.add_done_callback(_ai_tasks.discard)
    logger.info(
        "Scheduled AI analysis task for incident %s (service %s)",
        incident_id,
        service_id,
    )


async def _handle_anomaly(
    db: AsyncSession,
    service: Service,
    anomaly: dict[str, Any],
) -> None:
    service_id = service.id
    detection_type = str(anomaly.get("type", "anomaly"))
    logger.info(
        "_handle_anomaly called for service %s anomaly type %s",
        service_id,
        detection_type,
    )

    existing = await incident_service.get_open_incident(
        db, service_id, detection_type
    )
    if existing is not None:
        logger.info(
            "Skipping incident for service %s — open %s incident already exists (id=%s)",
            service_id,
            detection_type,
            existing.id,
        )
        return

    incident = await incident_service.create_open(
        db,
        IncidentCreate(
            service_id=service_id,
            title=_anomaly_title(anomaly),
            severity="P2",
            detection_type=detection_type,
        ),
    )
    if incident is None:
        logger.info(
            "Skipping incident for service %s — concurrent %s incident already open",
            service_id,
            detection_type,
        )
        return
    await incident_service.create_alert(
        db,
        AlertCreate(
            incident_id=incident.id,
            service_id=service_id,
            rule=detection_type,
            threshold_value=_anomaly_threshold(anomaly),
            observed_value=_anomaly_observed(anomaly),
        ),
    )
    await service_service.update_status(db, service_id, "degraded")
    _schedule_ai_analysis(incident.id, service_id)


async def _broadcast_event(service_id: int, event: EventRead | Event) -> None:
    from app.routers.ws import manager

    data = (
        event.model_dump(mode="json")
        if isinstance(event, EventRead)
        else EventRead.model_validate(event).model_dump(mode="json")
    )
    await manager.broadcast_to_service(
        service_id,
        {
            "type": "event",
            "data": data,
        },
    )


@router.post("/events", response_model=EventListResponse)
async def ingest_events(
    payload: EventBatchIngest,
    db: AsyncSession = Depends(get_db),
) -> EventListResponse | JSONResponse:
    try:
        service = await service_service.get_by_id(db, payload.service_id)
        if service is None:
            return error_response("Service not found", 404)

        created = await event_service.create_batch(
            db, payload.service_id, payload.events
        )
        reads = [EventRead.model_validate(event) for event in created]

        for event in created:
            anomaly = await detection.run_detection(db, payload.service_id, event)
            logger.info("Detection result for event %s: %s", event.id, anomaly)
            if anomaly is not None:
                await _handle_anomaly(db, service, anomaly)

        for read in reads:
            await _broadcast_event(payload.service_id, read)

        return EventListResponse(status="ok", data=reads, count=len(reads))
    except Exception as exc:
        return error_response(str(exc), 500)


@router.get("/events/{service_id}", response_model=EventListResponse)
async def list_events(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    level: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
) -> EventListResponse | JSONResponse:
    try:
        service = await service_service.get_by_id(db, service_id)
        if service is None:
            return error_response("Service not found", 404)

        events, total = await event_service.list_by_service(
            db,
            service_id,
            limit=limit,
            offset=offset,
            level=level,
            since=_parse_since(since),
            until=_parse_since(until),
        )
        return EventListResponse(status="ok", data=events, count=total)
    except ValueError:
        return error_response("Invalid since timestamp; use ISO 8601 format", 422)
    except Exception as exc:
        return error_response(str(exc), 500)
