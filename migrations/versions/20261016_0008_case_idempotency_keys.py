"""Persist idempotency keys for case creation.

Revision ID: 20261016_0008
Revises: 20260918_0007
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_0008"
down_revision: str | None = "20260918_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_case_idempotency_keys"),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "operation",
            "key_hash",
            name="uq_case_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_case_idempotency_created_at",
        "case_idempotency_keys",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_idempotency_created_at", table_name="case_idempotency_keys")
    op.drop_table("case_idempotency_keys")
