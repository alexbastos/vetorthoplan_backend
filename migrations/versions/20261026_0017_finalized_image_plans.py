"""Store immutable finalized plan snapshots and report artifacts.

Revision ID: 20261026_0017
Revises: 20261024_0016
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0017"
down_revision: str | None = "20261024_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finalized_image_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("clinical_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "image_id",
            sa.Uuid(),
            sa.ForeignKey("image_uploads.image_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("report_template_version", sa.String(100), nullable=False),
        sa.Column("report_png_key", sa.String(1024), nullable=False),
        sa.Column("report_png_sha256", sa.String(64), nullable=False),
        sa.Column("report_pdf_key", sa.String(1024), nullable=False),
        sa.Column("report_pdf_sha256", sa.String(64), nullable=False),
        sa.Column("finalized_by", sa.Uuid(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_finalized_image_plans_version_positive"),
        sa.CheckConstraint("plan_revision >= 1", name="ck_finalized_image_plans_revision_positive"),
        sa.CheckConstraint("length(snapshot_sha256) = 64", name="ck_finalized_plans_snapshot_sha256"),
        sa.CheckConstraint("length(report_png_sha256) = 64", name="ck_finalized_plans_png_sha256"),
        sa.CheckConstraint("length(report_pdf_sha256) = 64", name="ck_finalized_plans_pdf_sha256"),
        sa.UniqueConstraint("tenant_id", "image_id", "version", name="uq_finalized_plans_image_version"),
        sa.UniqueConstraint("tenant_id", "image_id", name="uq_finalized_plans_image"),
    )
    op.create_index(
        "ix_finalized_plans_tenant_case",
        "finalized_image_plans",
        ["tenant_id", "case_id"],
    )
    op.execute(
        """CREATE FUNCTION reject_finalized_plan_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'finalized image plan snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_finalized_image_plans_immutable
        BEFORE UPDATE ON finalized_image_plans
        FOR EACH ROW EXECUTE FUNCTION reject_finalized_plan_update()"""
    )
    op.execute(
        """CREATE FUNCTION reject_edit_after_plan_finalization() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM finalized_image_plans
                WHERE tenant_id = OLD.tenant_id AND image_id = OLD.image_id
            ) THEN
                RAISE EXCEPTION 'image plan has already been finalized';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_image_plans_frozen_after_finalization
        BEFORE UPDATE ON image_plans
        FOR EACH ROW EXECUTE FUNCTION reject_edit_after_plan_finalization()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_image_plans_frozen_after_finalization ON image_plans")
    op.execute("DROP FUNCTION IF EXISTS reject_edit_after_plan_finalization()")
    op.execute("DROP TRIGGER IF EXISTS trg_finalized_image_plans_immutable ON finalized_image_plans")
    op.execute("DROP FUNCTION IF EXISTS reject_finalized_plan_update()")
    op.drop_index("ix_finalized_plans_tenant_case", table_name="finalized_image_plans")
    op.drop_table("finalized_image_plans")
