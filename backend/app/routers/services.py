from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.helpers import error_response
from app.schemas.schemas import (
    OkResponse,
    ServiceCreate,
    ServiceDetailResponse,
    ServiceListResponse,
    ServiceRead,
    ServiceStatusUpdate,
)
from app.services import service_service

router = APIRouter()


@router.get("", response_model=ServiceListResponse)
async def list_services(
    environment: str | None = Query(default=None),
    include_benchmark: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> ServiceListResponse | JSONResponse:
    try:
        services = await service_service.list_services(
            db, environment=environment, include_benchmark=include_benchmark
        )
        return ServiceListResponse(status="ok", data=services, count=len(services))
    except Exception as exc:
        return error_response(str(exc), 500)


@router.post("", response_model=OkResponse[ServiceRead])
async def register_service(
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
) -> OkResponse[ServiceRead] | JSONResponse:
    try:
        service = await service_service.create(db, payload)
        return OkResponse(
            status="ok",
            data=ServiceRead.model_validate(service),
        )
    except IntegrityError:
        return error_response("Service name already exists", 409)
    except Exception as exc:
        return error_response(str(exc), 500)


@router.get("/{service_id}", response_model=ServiceDetailResponse)
async def get_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
) -> ServiceDetailResponse | JSONResponse:
    try:
        detail = await service_service.get_detail(db, service_id)
        if detail is None:
            return error_response("Service not found", 404)
        return ServiceDetailResponse(status="ok", data=detail)
    except Exception as exc:
        return error_response(str(exc), 500)


@router.patch("/{service_id}/status", response_model=OkResponse[ServiceRead])
async def update_service_status(
    service_id: int,
    payload: ServiceStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> OkResponse[ServiceRead] | JSONResponse:
    try:
        service = await service_service.update_status(db, service_id, payload.status)
        if service is None:
            return error_response("Service not found", 404)
        return OkResponse(
            status="ok",
            data=ServiceRead.model_validate(service),
        )
    except Exception as exc:
        return error_response(str(exc), 500)


@router.delete("/{service_id}", response_model=OkResponse[dict[str, bool]])
async def delete_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
) -> OkResponse[dict[str, bool]] | JSONResponse:
    try:
        deleted = await service_service.delete_service(db, service_id)
        if not deleted:
            return error_response("Service not found", 404)
        return OkResponse(
            status="ok",
            data={"deleted": True},
        )
    except Exception as exc:
        return error_response(str(exc), 500)

