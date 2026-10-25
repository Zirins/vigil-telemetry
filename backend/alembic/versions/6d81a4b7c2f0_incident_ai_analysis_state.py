"""incident AI analysis state

Revision ID: 6d81a4b7c2f0
Revises: 2f8a1c9d4e7b
Create Date: 2026-07-14 02:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6d81a4b7c2f0"
down_revision: Union[str, None] = "2f8a1c9d4e7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "ai_analysis_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_generated",
        ),
    )
    op.add_column(
        "incidents",
        sa.Column("ai_analysis_error", sa.Text(), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE incidents
            SET ai_analysis_status = CASE
                WHEN ai_analyzed_at IS NOT NULL THEN 'completed'
                WHEN ai_summary IS NOT NULL
                  OR ai_root_cause IS NOT NULL
                  OR ai_affected_components IS NOT NULL
                  OR ai_remediation_steps IS NOT NULL THEN 'failed'
                ELSE 'unavailable'
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE incidents
            SET postmortem =
                'Auto-resolved during demo reset because it duplicated an existing open incident.'
            WHERE postmortem =
                'Auto-resolved during demo reset ??? duplicate of an existing open incident.'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("incidents", "ai_analysis_error")
    op.drop_column("incidents", "ai_analysis_status")
