"""incident open dedup partial unique index

Revision ID: 2f8a1c9d4e7b
Revises: 1140c8c60c5a
Create Date: 2026-06-19 03:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2f8a1c9d4e7b"
down_revision: Union[str, None] = "1140c8c60c5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Resolve existing duplicate open incidents before adding the constraint.
    op.execute(
        sa.text(
            """
            UPDATE incidents
            SET status = 'resolved',
                resolved_at = NOW(),
                postmortem = 'Auto-resolved before open-incident dedup index migration.'
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY service_id, detection_type
                               ORDER BY started_at ASC NULLS LAST, id ASC
                           ) AS rn
                    FROM incidents
                    WHERE status IN ('open', 'investigating')
                      AND detection_type IS NOT NULL
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )

    op.create_index(
        "uq_incidents_open_service_detection_type",
        "incidents",
        ["service_id", "detection_type"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('open', 'investigating') AND detection_type IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_incidents_open_service_detection_type",
        table_name="incidents",
    )
