from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event
from app.services import event_service

# In-memory rolling windows per service+metric (keyed by "service_id:metric_name")
# Resets on restart — that's fine for MVP
_windows: dict[str, deque[float]] = {}
WINDOW_SIZE = 60
SPIKE_Z_THRESHOLD = 4.5
MIN_BASELINE_SAMPLES = 18


def check_metric_anomaly(
    service_id: int, metric_name: str, value: float
) -> dict[str, Any] | None:
    """Z-score spike detection: value > mean + zσ over the rolling window."""
    key = f"{service_id}:{metric_name}"
    if key not in _windows:
        _windows[key] = deque(maxlen=WINDOW_SIZE)

    window = _windows[key]

    if len(window) >= MIN_BASELINE_SAMPLES:
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = variance**0.5

        if std > 0 and value > mean + (SPIKE_Z_THRESHOLD * std):
            return {
                "type": "spike",
                "metric": metric_name,
                "observed": value,
                "mean": round(mean, 4),
                "std": round(std, 4),
                "threshold": round(mean + SPIKE_Z_THRESHOLD * std, 4),
            }

    window.append(value)
    return None


def check_error_rate_breach(
    recent_events: list[dict[str, Any]],
    window_seconds: int = 40,
    threshold_pct: float = 0.18,
    min_events: int = 30,
) -> dict[str, Any] | None:
    """Detects error-rate bursts when ERROR/FATAL share exceeds threshold."""
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    window = [e for e in recent_events if e["timestamp"] >= cutoff]

    if len(window) < min_events:
        return None

    errors = [e for e in window if e["level"] in ("ERROR", "FATAL")]
    error_rate = len(errors) / len(window)

    if error_rate > threshold_pct:
        return {
            "type": "error_rate",
            "error_rate": round(error_rate, 4),
            "threshold": threshold_pct,
            "total_events": len(window),
            "error_events": len(errors),
        }
    return None


def check_rage_pattern(
    recent_events: list[dict[str, Any]],
    window_seconds: int = 18,
    min_occurrences: int = 8,
) -> dict[str, Any] | None:
    """Detects repeated identical failures in rapid succession."""
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    errors = [
        e
        for e in recent_events
        if e["level"] in ("ERROR", "FATAL") and e["timestamp"] >= cutoff
    ]

    if len(errors) < min_occurrences:
        return None

    message_counts = Counter(
        (e.get("message") or "")[:80] for e in errors if e.get("message")
    )
    if not message_counts:
        return None

    repeated_message, count = message_counts.most_common(1)[0]
    if count >= min_occurrences:
        return {
            "type": "rage_pattern",
            "repeated_message": repeated_message,
            "occurrences": count,
            "window_seconds": window_seconds,
        }
    return None


def _event_to_detection_dict(event: Event) -> dict[str, Any]:
    return {
        "level": event.level,
        "message": event.message,
        "timestamp": event.timestamp or datetime.utcnow(),
        "payload": event.payload,
    }


async def run_detection(
    db: AsyncSession, service_id: int, event: Event
) -> dict[str, Any] | None:
    """
    Route the persisted event through metric and sequence detectors.
    Returns an incident payload dict when an anomaly is found, else None.
    """
    if event.level == "METRIC" and event.payload:
        metric_name = event.payload.get("metric")
        raw_value = event.payload.get("value")
        if metric_name is not None and raw_value is not None:
            spike = check_metric_anomaly(
                service_id, str(metric_name), float(raw_value)
            )
            if spike is not None:
                return spike

    # Log-sequence heuristics only on elevated log levels (avoids re-firing on every INFO/METRIC).
    if event.level not in ("ERROR", "FATAL"):
        return None

    recent_events = await event_service.get_recent_for_detection(
        db, service_id, window_seconds=45
    )

    current = _event_to_detection_dict(event)
    if not any(
        e["level"] == current["level"]
        and e.get("message") == current.get("message")
        and e["timestamp"] == current["timestamp"]
        for e in recent_events
    ):
        recent_events.insert(0, current)

    error_burst = check_error_rate_breach(recent_events)
    if error_burst is not None:
        return error_burst

    repeated_failure = check_rage_pattern(recent_events)
    if repeated_failure is not None:
        return repeated_failure

    return None
