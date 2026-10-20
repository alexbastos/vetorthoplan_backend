"""Add scoped idempotency to upload session creation.

Revision ID: 20261019_0011
Revises: 20261019_0010
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0011"
down_revision: str | None = "20261019_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("image_uploads", sa.Column("idempotency_key_hash", sa.String(64), nullable=True))
    op.add_column("image_uploads", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_image_uploads_idempotency_scope",
        "image_uploads",
        ["tenant_id", "created_by", "idempotency_key_hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_image_uploads_idempotency_scope", "image_uploads", type_="unique")
    op.drop_column("image_uploads", "request_hash")
    op.drop_column("image_uploads", "idempotency_key_hash")
