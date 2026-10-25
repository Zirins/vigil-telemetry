from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.helpers import error_response
from app.schemas.schemas import (
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentRead,
    IncidentResolve,
    OkResponse,
)
from app.services import incident_service, service_service

router = APIRouter()


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None),
    service_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> IncidentListResponse | JSONResponse:
    try:
        incidents, total = await incident_service.list_incidents(
            db,
            status=status,
            service_id=service_id,
            limit=limit,
            offset=offset,
        )
        return IncidentListResponse(status="ok", data=incidents, count=total)
    except Exception as exc:
        return error_response(str(exc), 500)


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
) -> IncidentDetailResponse | JSONResponse:
    try:
        detail = await incident_service.get_detail(db, incident_id)
        if detail is None:
            return error_response("Incident not found", 404)
        return IncidentDetailResponse(status="ok", data=detail)
    except Exception as exc:
        return error_response(str(exc), 500)


@router.post("/{incident_id}/resolve", response_model=OkResponse[IncidentRead])
async def resolve_incident(
    incident_id: int,
    payload: IncidentResolve,
    db: AsyncSession = Depends(get_db),
) -> OkResponse[IncidentRead] | JSONResponse:
    try:
        incident = await incident_service.resolve(
            db, incident_id, postmortem=payload.postmortem
        )
        if incident is None:
            return error_response("Incident not found", 404)

        await service_service.update_status(db, incident.service_id, "healthy")
        return OkResponse(
            status="ok",
            data=IncidentRead.model_validate(incident),
        )
    except Exception as exc:
        return error_response(str(exc), 500)
