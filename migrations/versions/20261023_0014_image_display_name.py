"""Add image display name.

Revision ID: 20261023_0014
Revises: 20261020_0013
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0014"
down_revision: str | None = "20261020_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("image_uploads", sa.Column("display_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("image_uploads", "display_name")
