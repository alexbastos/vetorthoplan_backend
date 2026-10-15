"""Support confirmation of image uploads.

Revision ID: 20260917_0003
Revises: 20260917_0002
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_uploads",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED')",
    )


def downgrade() -> None:
    op.execute("UPDATE image_uploads SET status = 'PENDING_UPLOAD' WHERE status = 'QUARANTINED'")
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD')",
    )
    op.drop_column("image_uploads", "completed_at")
