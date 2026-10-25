from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    environment: Mapped[Optional[str]] = mapped_column(
        String(50), server_default="production"
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="healthy"
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    events: Mapped[list[Event]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    metrics: Mapped[list[Metric]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_service_time", "service_id", desc("timestamp")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    service: Mapped[Service] = relationship(back_populates="events")


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        Index(
            "idx_metrics_service_name_time",
            "service_id",
            "metric_name",
            desc("timestamp"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    service: Mapped[Service] = relationship(back_populates="metrics")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("idx_incidents_service_status", "service_id", "status"),
        Index(
            "uq_incidents_open_service_detection_type",
            "service_id",
            "detection_type",
            unique=True,
            postgresql_where=text(
                "status IN ('open', 'investigating') AND detection_type IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default="open")
    severity: Mapped[Optional[str]] = mapped_column(String(10))
    detection_type: Mapped[Optional[str]] = mapped_column(String(50))
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_root_cause: Mapped[Optional[str]] = mapped_column(Text)
    ai_affected_components: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    ai_remediation_steps: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    ai_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    ai_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ai_analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="not_generated"
    )
    ai_analysis_error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    postmortem: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    service: Mapped[Service] = relationship(back_populates="incidents")
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("idx_alerts_incident", "incident_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    observed_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    fired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    acknowledged: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false"
    )

    incident: Mapped[Incident] = relationship(back_populates="alerts")
    service: Mapped[Service] = relationship(back_populates="alerts")
