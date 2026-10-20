"""Add cancelled upload session state.

Revision ID: 20261019_0012
Revises: 20261019_0011
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261019_0012"
down_revision: str | None = "20261019_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', "
        "'REJECTED', 'FAILED', 'CANCELLED')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM image_uploads WHERE status = 'CANCELLED'")
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', 'REJECTED', 'FAILED')",
    )
