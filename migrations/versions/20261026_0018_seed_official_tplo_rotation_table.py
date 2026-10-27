"""Persist the official BioMedtrix/VOI TPLO rotation reference table.

Revision ID: 20261026_0018
Revises: 20261026_0017
Create Date: 2026-10-26
"""

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0018"
down_revision: str | None = "20261026_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_VERSION = "VOI_TPLO_ROTATION_GUIDE_2018_01_15"
TABLE_SOURCE = "BioMedtrix/VOI TPLO Rotation Guide Chart 1-15-18"
TABLE_SOURCE_URL = "https://biomedtrix.com/tplo-rotation-guide-chart-1-15-18-2/"
TABLE_IMAGE_URL = "https://biomedtrix.com/wp-content/uploads/2020/11/TPLO-Rotation-Guide-Chart-1-15-18.png"


BLADE_DIAMETERS_MM = (8, 10, 12, 15, 18, 21, 24, 27, 30, 33)

# Each row is TPA 10..45 degrees, followed by rotation in mm for the blade sizes above.
ROTATION_GRID = (
    (10, 0.70, 0.87, 1.05, 1.31, 1.57, 1.83, 2.09, 2.36, 2.62, 2.88),
    (11, 0.84, 1.05, 1.26, 1.57, 1.88, 2.20, 2.51, 2.83, 3.14, 3.46),
    (12, 0.98, 1.22, 1.47, 1.83, 2.20, 2.57, 2.93, 3.30, 3.67, 4.03),
    (13, 1.12, 1.40, 1.68, 2.09, 2.51, 2.93, 3.35, 3.77, 4.19, 4.61),
    (14, 1.26, 1.57, 1.88, 2.36, 2.83, 3.30, 3.77, 4.24, 4.71, 5.18),
    (15, 1.40, 1.75, 2.09, 2.62, 3.14, 3.67, 4.19, 4.71, 5.24, 5.76),
    (16, 1.54, 1.92, 2.30, 2.88, 3.46, 4.03, 4.61, 5.18, 5.76, 6.34),
    (17, 1.68, 2.09, 2.51, 3.14, 3.77, 4.40, 5.03, 5.65, 6.28, 6.91),
    (18, 1.82, 2.27, 2.72, 3.40, 4.08, 4.76, 5.45, 6.13, 6.81, 7.49),
    (19, 1.95, 2.44, 2.93, 3.67, 4.40, 5.13, 5.86, 6.60, 7.33, 8.06),
    (20, 2.09, 2.62, 3.14, 3.93, 4.71, 5.50, 6.28, 7.07, 7.85, 8.64),
    (21, 2.23, 2.79, 3.35, 4.19, 5.03, 5.86, 6.70, 7.54, 8.38, 9.22),
    (22, 2.37, 2.97, 3.56, 4.45, 5.34, 6.23, 7.12, 8.01, 8.90, 9.79),
    (23, 2.51, 3.14, 3.77, 4.71, 5.65, 6.60, 7.54, 8.48, 9.42, 10.37),
    (24, 2.65, 3.32, 3.98, 4.97, 5.97, 6.96, 7.96, 8.95, 9.95, 10.94),
    (25, 2.79, 3.49, 4.19, 5.24, 6.28, 7.33, 8.38, 9.42, 10.47, 11.52),
    (26, 2.93, 3.67, 4.40, 5.50, 6.60, 7.70, 8.80, 9.90, 11.00, 12.10),
    (27, 3.07, 3.84, 4.61, 5.76, 6.91, 8.06, 9.22, 10.37, 11.52, 12.67),
    (28, 3.21, 4.01, 4.82, 6.02, 7.23, 8.43, 9.63, 10.84, 12.04, 13.25),
    (29, 3.35, 4.19, 5.03, 6.28, 7.54, 8.80, 10.05, 11.31, 12.57, 13.82),
    (30, 3.49, 4.36, 5.24, 6.54, 7.85, 9.16, 10.47, 11.78, 13.09, 14.40),
    (31, 3.63, 4.54, 5.45, 6.81, 8.17, 9.53, 10.89, 12.25, 13.61, 14.97),
    (32, 3.77, 4.71, 5.65, 7.07, 8.48, 9.90, 11.31, 12.72, 14.14, 15.55),
    (33, 3.91, 4.89, 5.86, 7.33, 8.80, 10.26, 11.73, 13.19, 14.66, 16.13),
    (34, 4.05, 5.06, 6.07, 7.59, 9.11, 10.63, 12.15, 13.67, 15.18, 16.70),
    (35, 4.19, 5.24, 6.28, 7.85, 9.42, 11.00, 12.57, 14.14, 15.71, 17.28),
    (36, 4.33, 5.41, 6.49, 8.12, 9.74, 11.36, 12.99, 14.61, 16.23, 17.85),
    (37, 4.47, 5.59, 6.70, 8.38, 10.05, 11.73, 13.40, 15.08, 16.76, 18.43),
    (38, 4.61, 5.76, 6.91, 8.64, 10.37, 12.10, 13.82, 15.55, 17.28, 19.01),
    (39, 4.75, 5.93, 7.12, 8.90, 10.68, 12.46, 14.24, 16.02, 17.80, 19.58),
    (40, 4.89, 6.11, 7.33, 9.16, 11.00, 12.83, 14.66, 16.49, 18.33, 20.16),
    (41, 5.03, 6.28, 7.54, 9.42, 11.31, 13.19, 15.08, 16.96, 18.85, 20.73),
    (42, 5.17, 6.46, 7.75, 9.69, 11.62, 13.56, 15.50, 17.44, 19.37, 21.31),
    (43, 5.31, 6.63, 7.96, 9.95, 11.94, 13.93, 15.92, 17.91, 19.90, 21.89),
    (44, 5.45, 6.81, 8.17, 10.21, 12.25, 14.29, 16.34, 18.38, 20.42, 22.46),
    (45, 5.59, 6.98, 8.38, 10.47, 12.57, 14.66, 16.76, 18.85, 20.94, 23.04),
)


def _validated_entries() -> list[dict[str, float | int]]:
    if len(ROTATION_GRID) != 36:
        raise RuntimeError("TPLO rotation grid must contain TPA values 10 through 45")
    entries: list[dict[str, float | int]] = []
    for expected_tpa, row in enumerate(ROTATION_GRID, start=10):
        if len(row) != len(BLADE_DIAMETERS_MM) + 1 or row[0] != expected_tpa:
            raise RuntimeError(f"Invalid TPLO rotation row for TPA {expected_tpa}")
        rotations = row[1:]
        if any(not math.isfinite(value) or value <= 0 for value in rotations):
            raise RuntimeError(f"Invalid rotation value for TPA {expected_tpa}")
        if any(left >= right for left, right in zip(rotations, rotations[1:], strict=False)):
            raise RuntimeError(f"Blade rotations are not increasing for TPA {expected_tpa}")
        entries.extend(
            {
                "tpa_degrees": expected_tpa,
                "blade_diameter_mm": blade_diameter,
                "rotation_mm": round(rotation, 2),
            }
            for blade_diameter, rotation in zip(BLADE_DIAMETERS_MM, rotations, strict=True)
        )
    if len(entries) != 360:
        raise RuntimeError("TPLO rotation grid must contain exactly 360 combinations")
    if not any(
        entry["tpa_degrees"] == 25 and entry["blade_diameter_mm"] == 24 and entry["rotation_mm"] == 8.38
        for entry in entries
    ):
        raise RuntimeError("TPLO rotation grid does not match the published 25/24 mm reference")
    for column_index in range(1, len(BLADE_DIAMETERS_MM) + 1):
        column_values = [row[column_index] for row in ROTATION_GRID]
        if any(
            left > right for left, right in zip(column_values, column_values[1:], strict=False)
        ):
            raise RuntimeError("TPLO rotation values must not decrease as TPA increases")
    return entries


def upgrade() -> None:
    op.create_table(
        "tplo_rotation_tables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("table_version", sa.String(100), nullable=False),
        sa.Column("source", sa.String(1000), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("source_asset_url", sa.String(1000), nullable=False),
        sa.Column("target_slope_degrees", sa.Numeric(5, 2), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("entries_sha256", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(table_version) > 0", name="ck_tplo_rotation_table_version_nonempty"),
        sa.CheckConstraint("length(source) > 0", name="ck_tplo_rotation_table_source_nonempty"),
        sa.CheckConstraint("length(source_url) > 0", name="ck_tplo_rotation_table_source_url_nonempty"),
        sa.CheckConstraint("length(source_asset_url) > 0", name="ck_tplo_rotation_table_asset_url_nonempty"),
        sa.CheckConstraint("length(entries_sha256) = 64", name="ck_tplo_rotation_table_hash_length"),
        sa.CheckConstraint(
            "target_slope_degrees > 0 AND target_slope_degrees < 90",
            name="ck_tplo_rotation_table_slope_range",
        ),
        sa.UniqueConstraint("table_version", name="uq_tplo_rotation_tables_version"),
    )
    op.create_index(
        "uq_tplo_rotation_tables_active",
        "tplo_rotation_tables",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    entries = _validated_entries()
    canonical_entries = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    op.get_bind().execute(
        sa.text(
            "INSERT INTO tplo_rotation_tables "
            "(id, table_version, source, source_url, source_asset_url, target_slope_degrees, entries, "
            "entries_sha256, is_active, created_at) VALUES "
            "(:id, :table_version, :source, :source_url, :source_asset_url, :target_slope_degrees, "
            "CAST(:entries AS json), :entries_sha256, :is_active, :created_at)"
        ),
        {
            "id": "d99c679a-3af7-4c26-a087-aec69b0f0e91",
            "table_version": TABLE_VERSION,
            "source": TABLE_SOURCE,
            "source_url": TABLE_SOURCE_URL,
            "source_asset_url": TABLE_IMAGE_URL,
            "target_slope_degrees": 5,
            "entries": canonical_entries,
            "entries_sha256": hashlib.sha256(canonical_entries.encode("utf-8")).hexdigest(),
            "is_active": True,
            "created_at": datetime.now(UTC),
        },
    )
    op.execute(
        """CREATE FUNCTION protect_tplo_rotation_table_version() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'TPLO rotation table versions cannot be deleted';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.table_version IS DISTINCT FROM OLD.table_version
                OR NEW.source IS DISTINCT FROM OLD.source
                OR NEW.source_url IS DISTINCT FROM OLD.source_url
                OR NEW.source_asset_url IS DISTINCT FROM OLD.source_asset_url
                OR NEW.target_slope_degrees IS DISTINCT FROM OLD.target_slope_degrees
                OR NEW.entries IS DISTINCT FROM OLD.entries
                OR NEW.entries_sha256 IS DISTINCT FROM OLD.entries_sha256
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'TPLO rotation table version data is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_tplo_rotation_table_version_immutable
        BEFORE UPDATE OR DELETE ON tplo_rotation_tables
        FOR EACH ROW EXECUTE FUNCTION protect_tplo_rotation_table_version()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tplo_rotation_table_version_immutable ON tplo_rotation_tables")
    op.execute("DROP FUNCTION IF EXISTS protect_tplo_rotation_table_version()")
    op.drop_index("uq_tplo_rotation_tables_active", table_name="tplo_rotation_tables")
    op.drop_table("tplo_rotation_tables")
