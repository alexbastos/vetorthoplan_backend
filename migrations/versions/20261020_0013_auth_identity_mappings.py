"""Create mappings for external authentication identities and organizations.

Revision ID: 20261020_0013
Revises: 20261019_0012
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0013"
down_revision: str | None = "20261019_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_subject_mappings",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("actor_id", name="pk_auth_subject_mappings"),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_auth_subject_mappings_issuer_subject",
        ),
    )
    op.create_table(
        "auth_organization_mappings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("organization_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_auth_organization_mappings"),
        sa.UniqueConstraint(
            "issuer",
            "organization_id",
            name="uq_auth_organization_mappings_issuer_organization",
        ),
    )


def downgrade() -> None:
    op.drop_table("auth_organization_mappings")
    op.drop_table("auth_subject_mappings")
