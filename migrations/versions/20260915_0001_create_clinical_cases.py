"""Create clinical cases.

Revision ID: 20260915_0001
Revises:
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("animal_name", sa.String(length=120), nullable=False),
        sa.Column("species", sa.String(length=80), nullable=False),
        sa.Column("breed", sa.String(length=120), nullable=True),
        sa.Column("sex", sa.String(length=20), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("approximate_age_months", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'IN_PLANNING', 'READY', 'ARCHIVED')",
            name="ck_clinical_cases_status",
        ),
        sa.CheckConstraint(
            "sex IS NULL OR sex IN ('FEMALE', 'MALE', 'UNKNOWN')",
            name="ck_clinical_cases_sex",
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0",
            name="ck_clinical_cases_weight_positive",
        ),
        sa.CheckConstraint(
            "approximate_age_months IS NULL OR approximate_age_months BETWEEN 0 AND 600",
            name="ck_clinical_cases_age_range",
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg <= 99999.99",
            name="ck_clinical_cases_weight_maximum",
        ),
        sa.CheckConstraint(
            "birth_date IS NULL OR approximate_age_months IS NULL",
            name="ck_clinical_cases_single_age_source",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_cases"),
    )
    op.create_index(
        "ix_clinical_cases_tenant_created_at",
        "clinical_cases",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_clinical_cases_tenant_status",
        "clinical_cases",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_cases_tenant_status", table_name="clinical_cases")
    op.drop_index("ix_clinical_cases_tenant_created_at", table_name="clinical_cases")
    op.drop_table("clinical_cases")
