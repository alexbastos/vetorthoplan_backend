"""Track late objects after case deletion.

Revision ID: 20261023_0015
Revises: 20261023_0014
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0015"
down_revision: str | None = "20261023_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_storage_cleanups",
        sa.Column("object_key", sa.String(length=1024), primary_key=True),
        sa.Column("cleanup_after", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pending_storage_cleanups_after", "pending_storage_cleanups", ["cleanup_after"])


def downgrade() -> None:
    op.drop_index("ix_pending_storage_cleanups_after", table_name="pending_storage_cleanups")
    op.drop_table("pending_storage_cleanups")
