from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

_ORM_CONFIG = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Response envelopes
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    model_config = _ORM_CONFIG

    status: Literal["error"] = "error"
    message: str
    code: int


class OkResponse(BaseModel, Generic[T]):
    model_config = _ORM_CONFIG

    status: Literal["ok"] = "ok"
    data: T


class OkListResponse(BaseModel, Generic[T]):
    model_config = _ORM_CONFIG

    status: Literal["ok"] = "ok"
    data: list[T]
    count: int


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    model_config = _ORM_CONFIG

    level: str
    message: Optional[str] = None
    source: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class EventRead(BaseModel):
    model_config = _ORM_CONFIG

    id: int
    service_id: int
    level: str
    message: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    source: Optional[str] = None
    timestamp: Optional[datetime] = None


class EventBatchIngest(BaseModel):
    model_config = _ORM_CONFIG

    service_id: int
    events: list[EventCreate]


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


class MetricCreate(BaseModel):
    model_config = _ORM_CONFIG

    service_id: int
    metric_name: str
    value: Decimal
    unit: Optional[str] = None


class MetricRead(BaseModel):
    model_config = _ORM_CONFIG

    id: int
    service_id: int
    metric_name: str
    value: Decimal
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------


class AlertCreate(BaseModel):
    model_config = _ORM_CONFIG

    incident_id: int
    service_id: int
    rule: str
    threshold_value: Optional[Decimal] = None
    observed_value: Optional[Decimal] = None


class AlertRead(BaseModel):
    model_config = _ORM_CONFIG

    id: int
    incident_id: int
    service_id: int
    rule: str
    threshold_value: Optional[Decimal] = None
    observed_value: Optional[Decimal] = None
    fired_at: Optional[datetime] = None
    acknowledged: Optional[bool] = False


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


class IncidentCreate(BaseModel):
    model_config = _ORM_CONFIG

    service_id: int
    title: str
    status: Optional[str] = "open"
    severity: Optional[str] = None
    detection_type: Optional[str] = None


class IncidentRead(BaseModel):
    model_config = _ORM_CONFIG

    id: int
    service_id: int
    service_name: Optional[str] = None
    title: str
    status: Optional[str] = "open"
    severity: Optional[str] = None
    detection_type: Optional[str] = None
    started_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    postmortem: Optional[str] = None
    created_at: Optional[datetime] = None


class IncidentDetail(IncidentRead):
    ai_summary: Optional[str] = None
    ai_root_cause: Optional[str] = None
    ai_affected_components: Optional[list[str]] = None
    ai_remediation_steps: Optional[list[str]] = None
    ai_confidence: Optional[Decimal] = None
    ai_analyzed_at: Optional[datetime] = None
    ai_analysis_status: str = "not_generated"
    alerts: list[AlertRead] = []


class IncidentResolve(BaseModel):
    model_config = _ORM_CONFIG

    postmortem: Optional[str] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ServiceBase(BaseModel):
    model_config = _ORM_CONFIG

    name: str
    environment: str = "production"
    description: Optional[str] = None


class ServiceCreate(ServiceBase):
    pass


class ServiceRead(ServiceBase):
    id: int
    status: Optional[str] = "healthy"
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ServiceListItem(ServiceRead):
    open_incident_count: int = 0
    latest_latency_p99: Optional[Decimal] = None
    latest_error_rate: Optional[Decimal] = None
    highest_open_severity: Optional[str] = None


class ServiceDetail(ServiceRead):
    recent_incident_count: int = 0
    recent_events: list[EventRead] = []
    active_incidents: list[IncidentRead] = []


class ServiceStatusUpdate(BaseModel):
    model_config = _ORM_CONFIG

    status: str


# ---------------------------------------------------------------------------
# Typed list / single response aliases
# ---------------------------------------------------------------------------

ServiceListResponse = OkListResponse[ServiceListItem]
ServiceDetailResponse = OkResponse[ServiceDetail]
EventListResponse = OkListResponse[EventRead]
MetricListResponse = OkListResponse[MetricRead]
IncidentListResponse = OkListResponse[IncidentRead]
IncidentDetailResponse = OkResponse[IncidentDetail]
AlertListResponse = OkListResponse[AlertRead]
