from __future__ import annotations

import importlib.util
import logging
import sys
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
logging.getLogger("app").setLevel(logging.DEBUG)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def _clear_stale_stub(module_name: str) -> None:
    """Remove a prior sys.modules stub so the real package module can load."""
    existing = sys.modules.get(module_name)
    if existing is not None and not getattr(existing, "__file__", None):
        del sys.modules[module_name]


def _install_stubs() -> None:
    """Register lightweight stubs only for modules that are not yet implemented."""
    if importlib.util.find_spec("app.services.detection") is None:
        detection = ModuleType("app.services.detection")

        async def run_detection(db: Any, service_id: int, event: Any) -> None:
            return None

        detection.run_detection = run_detection
        sys.modules["app.services.detection"] = detection
    else:
        _clear_stale_stub("app.services.detection")

    if importlib.util.find_spec("app.services.nlp") is None:
        nlp = ModuleType("app.services.nlp")

        async def analyze_incident(**kwargs: Any) -> dict[str, Any]:
            return {
                "severity": "P3",
                "summary": "AI analysis pending — stub response.",
                "root_cause": "Analysis not yet available.",
                "affected_components": [],
                "remediation_steps": ["Complete NLP service implementation."],
                "confidence": 0.0,
            }

        nlp.analyze_incident = analyze_incident
        sys.modules["app.services.nlp"] = nlp
    else:
        _clear_stale_stub("app.services.nlp")

    if importlib.util.find_spec("app.routers.ws") is None:
        ws = ModuleType("app.routers.ws")

        class ConnectionManager:
            async def broadcast_to_service(self, service_id: int, message: dict) -> None:
                return None

            async def broadcast_all(self, message: dict) -> None:
                return None

        ws.manager = ConnectionManager()
        sys.modules["app.routers.ws"] = ws
    else:
        _clear_stale_stub("app.routers.ws")


_install_stubs()

from app.routers import events, incidents, metrics, services, ws  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(
    title="Vigil",
    description="AI-Powered Observability & Incident Intelligence Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(events.router, tags=["events"])
app.include_router(metrics.router, tags=["metrics"])
app.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
app.include_router(ws.router, prefix="/ws", tags=["websockets"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
