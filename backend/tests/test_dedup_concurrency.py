from __future__ import annotations

import asyncio
from collections import deque
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.models import Alert, Event, Incident, Metric, Service
from app.schemas.schemas import ServiceCreate
from app.services import detection, incident_service, service_service


@pytest.mark.asyncio
async def test_concurrent_ingestion_open_incident_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Two truly concurrent ingestion requests triggering the same detector
    for the same service must leave exactly one open incident. Both requests
    must actually reach the insert path.
    """
    test_service_name = f"test-dedup-{uuid4().hex[:8]}"
    service_id: int | None = None

    async with AsyncSessionLocal() as db:
        service = await service_service.create(
            db,
            ServiceCreate(name=test_service_name, environment="test"),
        )
        service_id = service.id

    try:
        # Pre-seed metric baseline with variance so value=500.0 triggers spike detection
        metric_key = f"{service_id}:cpu"
        detection._windows[metric_key] = deque([10.0, 10.2, 9.8, 10.1, 9.9] * 4, maxlen=60)

        # Coordinate concurrency at the race window:
        # Ensure both concurrent requests check get_open_incident and receive None
        # before either proceeds to _insert_incident.
        barrier = asyncio.Barrier(2)
        insert_calls = 0

        orig_get_open = incident_service.get_open_incident
        orig_insert = incident_service._insert_incident

        async def synchronized_get_open(db, s_id, d_type):
            res = await orig_get_open(db, s_id, d_type)
            # Both requests await here; releasing only when both have checked
            await barrier.wait()
            return res

        async def tracked_insert(db, data):
            nonlocal insert_calls
            insert_calls += 1
            return await orig_insert(db, data)

        monkeypatch.setattr(incident_service, "get_open_incident", synchronized_get_open)
        monkeypatch.setattr(incident_service, "_insert_incident", tracked_insert)

        payload = {
            "service_id": service_id,
            "events": [
                {
                    "level": "METRIC",
                    "payload": {"metric": "cpu", "value": 500.0},
                }
            ],
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp1, resp2 = await asyncio.wait_for(
                asyncio.gather(
                    client.post("/events", json=payload),
                    client.post("/events", json=payload),
                ),
                timeout=15,
            )

        assert resp1.status_code == 200, f"Request 1 failed: {resp1.text}"
        assert resp2.status_code == 200, f"Request 2 failed: {resp2.text}"

        # Crucial check: verify both requests actually reached the insert path
        assert insert_calls == 2, f"Expected 2 insert attempts, got {insert_calls}"

        # Verify database state in real PostgreSQL: exactly one open incident must exist
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Incident).where(
                    Incident.service_id == service_id,
                    Incident.detection_type == "spike",
                    Incident.status.in_(("open", "investigating")),
                )
            )
            open_incidents = result.scalars().all()
            assert len(open_incidents) == 1, (
                f"Expected exactly 1 open incident, found {len(open_incidents)}"
            )

    finally:
        # Cleanup test data from PostgreSQL
        if service_id is not None:
            detection._windows.pop(f"{service_id}:cpu", None)
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(Alert).where(Alert.service_id == service_id)
                )
                await db.execute(
                    delete(Incident).where(Incident.service_id == service_id)
                )
                await db.execute(
                    delete(Event).where(Event.service_id == service_id)
                )
                await db.execute(
                    delete(Metric).where(Metric.service_id == service_id)
                )
                await db.execute(
                    delete(Service).where(Service.id == service_id)
                )
                await db.commit()
