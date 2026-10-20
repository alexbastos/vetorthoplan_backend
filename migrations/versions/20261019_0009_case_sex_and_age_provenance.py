"""Require sex for new cases and record the age source/reference.

Revision ID: 20261019_0009
Revises: 20261016_0008
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0009"
down_revision: str | None = "20261016_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinical_cases", sa.Column("age_source", sa.String(length=24), nullable=True))
    op.add_column("clinical_cases", sa.Column("age_reference_date", sa.Date(), nullable=True))
    op.drop_constraint("ck_clinical_cases_single_age_source", "clinical_cases", type_="check")
    op.create_check_constraint(
        "ck_clinical_cases_age_source",
        "clinical_cases",
        "age_source IS NULL OR age_source IN ('DECLARED', 'BIRTH_DATE')",
    )
    # Preserve legacy data as it was recorded; backfill provenance without changing its values.
    op.execute(
        "UPDATE clinical_cases SET age_source = CASE "
        "WHEN birth_date IS NOT NULL THEN 'BIRTH_DATE' "
        "WHEN approximate_age_months IS NOT NULL THEN 'DECLARED' ELSE NULL END, "
        "age_reference_date = CASE WHEN birth_date IS NOT NULL OR approximate_age_months IS NOT NULL "
        "THEN created_at::date ELSE NULL END"
    )


def downgrade() -> None:
    op.drop_constraint("ck_clinical_cases_age_source", "clinical_cases", type_="check")
    op.create_check_constraint(
        "ck_clinical_cases_single_age_source",
        "clinical_cases",
        "birth_date IS NULL OR approximate_age_months IS NULL",
    )
    op.drop_column("clinical_cases", "age_reference_date")
    op.drop_column("clinical_cases", "age_source")
