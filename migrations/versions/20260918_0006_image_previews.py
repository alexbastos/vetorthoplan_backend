"""Add safe image previews and allowlisted metadata.

Revision ID: 20260918_0006
Revises: 20260918_0005
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0006"
down_revision: str | None = "20260918_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("image_uploads", sa.Column("image_metadata", sa.JSON()))
    op.add_column("image_uploads", sa.Column("preview_object_key", sa.String(1024)))
    op.add_column("image_uploads", sa.Column("preview_media_type", sa.String(64)))
    op.add_column("image_uploads", sa.Column("preview_width_px", sa.Integer()))
    op.add_column("image_uploads", sa.Column("preview_height_px", sa.Integer()))


def downgrade() -> None:
    op.drop_column("image_uploads", "preview_height_px")
    op.drop_column("image_uploads", "preview_width_px")
    op.drop_column("image_uploads", "preview_media_type")
    op.drop_column("image_uploads", "preview_object_key")
    op.drop_column("image_uploads", "image_metadata")
