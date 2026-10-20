"""Represent operational ingestion failures separately from content rejection.

Revision ID: 20261019_0010
Revises: 20261019_0009
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261019_0010"
down_revision: str | None = "20261019_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', 'REJECTED', 'FAILED')",
    )


def downgrade() -> None:
    op.execute("UPDATE image_uploads SET status = 'REJECTED' WHERE status = 'FAILED'")
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', 'REJECTED')",
    )
