"""Make implant source and editable asset formats explicit and replaceable."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0020"
down_revision: str | None = "20261027_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "implant_catalog_imports",
        sa.Column("source_media_type", sa.String(160), nullable=True),
    )
    op.add_column(
        "implant_catalog_imports",
        sa.Column("editable_asset_object_key", sa.String(1024), nullable=True),
    )
    op.add_column(
        "implant_catalog_imports",
        sa.Column("editable_asset_media_type", sa.String(160), nullable=True),
    )
    op.execute(
        "UPDATE implant_catalog_imports "
        "SET editable_asset_object_key = svg_object_key, "
        "editable_asset_media_type = 'image/svg+xml' "
        "WHERE svg_object_key IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("implant_catalog_imports", "editable_asset_media_type")
    op.drop_column("implant_catalog_imports", "editable_asset_object_key")
    op.drop_column("implant_catalog_imports", "source_media_type")
