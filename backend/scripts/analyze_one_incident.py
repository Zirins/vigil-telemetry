#!/usr/bin/env python3
"""
Run Claude AI analysis for a single incident (manual backfill only).

Does not touch the live ingestion path in events.py — use this when you want
real ai_* fields on one incident without enabling batch or simulator triggers.

Run from project root:
    python backend/scripts/analyze_one_incident.py 418
    python backend/scripts/analyze_one_incident.py 418 --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.services import incident_service, nlp, service_service  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Claude analysis for one incident (manual backfill)."
    )
    parser.add_argument(
        "incident_id",
        type=int,
        help="Incident primary key to analyze",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to call Claude after reviewing the printed incident details",
    )
    return parser.parse_args()


async def analyze_one(incident_id: int, *, confirm: bool) -> None:
    async with AsyncSessionLocal() as db:
        incident = await incident_service.get_by_id(db, incident_id)
        if incident is None:
            print(f"Incident {incident_id} not found.")
            sys.exit(1)

        service = await service_service.get_by_id(db, incident.service_id)
        service_name = service.name if service else f"service_id={incident.service_id}"

        print("Target incident (verify before calling Claude):")
        print(f"  id:              {incident.id}")
        print(f"  title:           {incident.title}")
        print(f"  service:         {service_name}")
        print(f"  service_id:      {incident.service_id}")
        print(f"  status:          {incident.status}")
        print(f"  severity:        {incident.severity}")
        print(f"  detection_type:  {incident.detection_type}")
        print(f"  started_at:      {incident.started_at}")
        print(f"  ai_analyzed_at:  {incident.ai_analyzed_at or '(not yet analyzed)'}")

        if not confirm:
            print()
            print("No API call made. Re-run with --confirm to analyze this incident.")
            return

    print()
    print(f"Calling Claude for incident {incident_id} …")
    await nlp.analyze_incident(incident_id, incident.service_id)

    async with AsyncSessionLocal() as db:
        updated = await incident_service.get_detail(db, incident_id)
        if updated is None:
            print(f"Incident {incident_id} missing after analysis.")
            sys.exit(1)

        if updated.ai_analyzed_at is None:
            print("Analysis finished but ai_analyzed_at is still null — check backend logs.")
            sys.exit(1)

        print()
        print("AI analysis persisted:")
        print(f"  ai_analyzed_at:  {updated.ai_analyzed_at}")
        print(f"  ai_confidence:   {updated.ai_confidence}")
        print(f"  ai_summary:      {(updated.ai_summary or '')[:120]}…")


async def main() -> None:
    args = parse_args()
    try:
        await analyze_one(args.incident_id, confirm=args.confirm)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
