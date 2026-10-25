from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import anthropic

from app.config import settings
from app.database import AsyncSessionLocal
from app.services import event_service, incident_service, service_service

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

INCIDENT_ANALYSIS_PROMPT = """
You are an expert SRE (Site Reliability Engineer) analyzing a production incident.
Analyze the following events and metrics from a failing service and produce a structured incident report.

Return ONLY valid JSON. No markdown. No explanation. No preamble.

Schema:
{{
  "severity": "P1" | "P2" | "P3",
  "summary": "<2-3 sentence plain-language description of what is happening>",
  "root_cause": "<most likely root cause based on the evidence>",
  "affected_components": ["<component1>", "<component2>"],
  "remediation_steps": [
    "<actionable step 1>",
    "<actionable step 2>",
    "<actionable step 3>"
  ],
  "confidence": <float 0.0-1.0>
}}

Severity guide:
- P1: Complete service outage or data loss risk
- P2: Major degradation, partial outage, significant user impact
- P3: Minor degradation, performance issue, early warning signal

Confidence: how strongly the evidence points to the root cause (1.0 = very clear, 0.0 = ambiguous)

Service: {service_name}
Detection type: {detection_type}
Anomaly details: {anomaly_details}

Recent events (newest first):
{events_text}
"""


def _parse_analysis_response(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)


def _build_anomaly_details(incident_detail: Any) -> dict[str, Any]:
    if incident_detail.alerts:
        alert = incident_detail.alerts[0]
        return {
            "rule": alert.rule,
            "threshold_value": (
                float(alert.threshold_value) if alert.threshold_value is not None else None
            ),
            "observed_value": (
                float(alert.observed_value) if alert.observed_value is not None else None
            ),
        }
    return {"detection_type": incident_detail.detection_type}


def _format_events_text(recent_events: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            f"[{event['timestamp']}] [{event['level']}] "
            f"{event.get('message', '')} {event.get('payload', '')}"
            for event in recent_events[:50]
        ]
    )


async def analyze_incident(incident_id: int, service_id: int) -> None:
    """
    Fetch incident context, call Claude, and persist AI analysis fields.
    Intended to run as a background task after incident creation.
    """
    logger.info("analyze_incident entered for incident %s service %s", incident_id, service_id)

    async with AsyncSessionLocal() as db:
        incident_detail = await incident_service.get_detail(db, incident_id)
        if incident_detail is None:
            logger.warning("Incident %s not found for AI analysis", incident_id)
            return

        service = await service_service.get_by_id(db, service_id)
        if service is None:
            logger.warning("Service %s not found for AI analysis", service_id)
            await incident_service.set_ai_analysis_status(
                db,
                incident_id,
                "failed",
                error="Related service was not found.",
            )
            return

        await incident_service.set_ai_analysis_status(
            db,
            incident_id,
            "processing",
        )

        recent_events = await event_service.get_recent_for_detection(
            db, service_id, window_seconds=120
        )

        prompt = INCIDENT_ANALYSIS_PROMPT.format(
            service_name=service.name,
            detection_type=incident_detail.detection_type or "unknown",
            anomaly_details=json.dumps(_build_anomaly_details(incident_detail)),
            events_text=_format_events_text(recent_events),
        )

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            block.text for block in message.content if block.type == "text"
        )
        if not raw:
            raise ValueError("Analysis provider returned no report content")
        analysis = _parse_analysis_response(raw)
        logger.info("Claude analysis parsed for incident %s", incident_id)
    except Exception as exc:
        logger.exception("Claude API call failed for incident %s: %s", incident_id, exc)
        async with AsyncSessionLocal() as db:
            await incident_service.set_ai_analysis_status(
                db,
                incident_id,
                "failed",
                error=str(exc)[:1000],
            )
        return

    async with AsyncSessionLocal() as db:
        updated = await incident_service.update_ai_analysis(
            db,
            incident_id,
            ai_summary=analysis["summary"],
            ai_root_cause=analysis["root_cause"],
            ai_affected_components=analysis["affected_components"],
            ai_remediation_steps=analysis["remediation_steps"],
            ai_confidence=Decimal(str(analysis["confidence"])),
        )
        if updated is None:
            logger.error("Failed to persist AI analysis for incident %s", incident_id)
            return
        logger.info("AI analysis persisted for incident %s", incident_id)
