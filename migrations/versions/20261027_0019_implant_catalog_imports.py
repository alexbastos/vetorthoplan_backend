"""Add versioned implant catalog import and review records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0019"
down_revision: str | None = "20261026_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "implant_catalog_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("source_object_key", sa.String(1024), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("svg_object_key", sa.String(1024), nullable=True),
        sa.Column("preview_object_key", sa.String(1024), nullable=True),
        sa.Column("conversion_metadata", sa.JSON(), nullable=True),
        sa.Column("converter_version", sa.String(100), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('AWAITING_SOURCE', 'WAITING_FOR_CONVERTER', 'QUEUED', 'PROCESSING', "
            "'REVIEW_REQUIRED', 'APPROVED', 'REJECTED', 'FAILED')",
            name="ck_implant_catalog_imports_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_object_key", name="uq_implant_catalog_imports_source_key"),
    )
    op.create_index(
        "ix_implant_catalog_imports_status_created",
        "implant_catalog_imports",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_implant_catalog_imports_tenant_created",
        "implant_catalog_imports",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_implant_catalog_imports_tenant_created", table_name="implant_catalog_imports")
    op.drop_index("ix_implant_catalog_imports_status_created", table_name="implant_catalog_imports")
    op.drop_table("implant_catalog_imports")
