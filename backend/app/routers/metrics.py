from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.helpers import error_response
from app.schemas.schemas import MetricListResponse
from app.services import metric_service, service_service

router = APIRouter()


@router.get("/metrics/{service_id}", response_model=MetricListResponse)
async def list_metrics(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    metric_name: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MetricListResponse | JSONResponse:
    try:
        service = await service_service.get_by_id(db, service_id)
        if service is None:
            return error_response("Service not found", 404)

        metrics, total = await metric_service.list_by_service(
            db,
            service_id,
            metric_name=metric_name,
            limit=limit,
            offset=offset,
        )
        return MetricListResponse(status="ok", data=metrics, count=total)
    except Exception as exc:
        return error_response(str(exc), 500)


@router.get("/metrics/{service_id}/recent", response_model=MetricListResponse)
async def list_recent_metrics(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    names: str = Query(default="cpu_pct,error_rate"),
    limit: int = Query(default=60, ge=1, le=500),
) -> MetricListResponse | JSONResponse:
    try:
        service = await service_service.get_by_id(db, service_id)
        if service is None:
            return error_response("Service not found", 404)

        metric_names = [name.strip() for name in names.split(",") if name.strip()]
        metrics = await metric_service.get_recent_by_names(
            db,
            service_id,
            metric_names,
            limit=limit,
        )
        return MetricListResponse(status="ok", data=metrics, count=len(metrics))
    except Exception as exc:
        return error_response(str(exc), 500)
