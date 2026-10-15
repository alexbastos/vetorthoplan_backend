"""Add versioned geometric plans.

Revision ID: 20260918_0007
Revises: 20260918_0006
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0007"
down_revision: str | None = "20260918_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("clinical_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_image_plans_revision_positive"),
        sa.UniqueConstraint("tenant_id", "image_id", name="uq_image_plans_tenant_image"),
    )
    op.create_index("ix_image_plans_tenant_case", "image_plans", ["tenant_id", "case_id"])


def downgrade() -> None:
    op.drop_index("ix_image_plans_tenant_case", table_name="image_plans")
    op.drop_table("image_plans")
