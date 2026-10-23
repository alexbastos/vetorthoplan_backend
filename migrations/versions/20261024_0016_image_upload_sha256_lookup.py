"""Index image uploads by case and SHA-256.

Revision ID: 20261024_0016
Revises: 20261023_0015
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0016"
down_revision: str | None = "20261023_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_image_uploads_case_sha256",
        "image_uploads",
        ["tenant_id", "case_id", "sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_uploads_case_sha256", table_name="image_uploads")
