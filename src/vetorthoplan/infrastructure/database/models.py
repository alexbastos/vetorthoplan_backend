from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuthSubjectMappingModel(Base):
    """Maps an authentication service subject to the backend's internal actor UUID."""

    __tablename__ = "auth_subject_mappings"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_auth_subject_mappings_issuer_subject"),)

    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthOrganizationMappingModel(Base):
    """Maps an authentication service organization CUID to an internal tenant UUID."""

    __tablename__ = "auth_organization_mappings"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "organization_id",
            name="uq_auth_organization_mappings_issuer_organization",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PendingStorageCleanupModel(Base):
    __tablename__ = "pending_storage_cleanups"
    object_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    cleanup_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CaseModel(Base):
    __tablename__ = "clinical_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'IN_PLANNING', 'READY', 'ARCHIVED')",
            name="ck_clinical_cases_status",
        ),
        CheckConstraint(
            "sex IS NULL OR sex IN ('FEMALE', 'MALE', 'UNKNOWN')",
            name="ck_clinical_cases_sex",
        ),
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0",
            name="ck_clinical_cases_weight_positive",
        ),
        CheckConstraint(
            "approximate_age_months IS NULL OR approximate_age_months BETWEEN 0 AND 600",
            name="ck_clinical_cases_age_range",
        ),
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg <= 99999.99",
            name="ck_clinical_cases_weight_maximum",
        ),
        CheckConstraint(
            "age_source IS NULL OR age_source IN ('DECLARED', 'BIRTH_DATE')",
            name="ck_clinical_cases_age_source",
        ),
        Index("ix_clinical_cases_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_clinical_cases_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    animal_name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[str] = mapped_column(String(80), nullable=False)
    breed: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approximate_age_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    age_reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CaseIdempotencyModel(Base):
    __tablename__ = "case_idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "actor_id",
            "operation",
            "key_hash",
            name="uq_case_idempotency_scope",
        ),
        Index("ix_case_idempotency_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImageUploadModel(Base):
    __tablename__ = "image_uploads"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('DICOM', 'PNG', 'JPEG')",
            name="ck_image_uploads_kind",
        ),
        CheckConstraint(
            "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', "
            "'REJECTED', 'FAILED', 'CANCELLED')",
            name="ck_image_uploads_status",
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 104857600",
            name="ck_image_uploads_size_range",
        ),
        UniqueConstraint("object_key", name="uq_image_uploads_object_key"),
        UniqueConstraint(
            "tenant_id",
            "created_by",
            "idempotency_key_hash",
            name="uq_image_uploads_idempotency_scope",
        ),
        Index("ix_image_uploads_tenant_case", "tenant_id", "case_id"),
        Index("ix_image_uploads_case_sha256", "tenant_id", "case_id", "sha256"),
        Index("ix_image_uploads_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    image_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_metadata: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    preview_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    preview_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IngestionJobModel(Base):
    __tablename__ = "image_ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
            name="ck_image_ingestion_jobs_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_image_ingestion_jobs_attempts_nonnegative",
        ),
        Index("ix_image_ingestion_jobs_status_created_at", "status", "created_at"),
        Index("ix_image_ingestion_jobs_tenant_id", "tenant_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("image_uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ImagePlanModel(Base):
    __tablename__ = "image_plans"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_image_plans_revision_positive"),
        UniqueConstraint("tenant_id", "image_id", name="uq_image_plans_tenant_image"),
        Index("ix_image_plans_tenant_case", "tenant_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinalizedPlanModel(Base):
    __tablename__ = "finalized_image_plans"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_finalized_image_plans_version_positive"),
        CheckConstraint("plan_revision >= 1", name="ck_finalized_image_plans_revision_positive"),
        UniqueConstraint("tenant_id", "image_id", "version", name="uq_finalized_plans_image_version"),
        UniqueConstraint("tenant_id", "image_id", name="uq_finalized_plans_image"),
        Index("ix_finalized_plans_tenant_case", "tenant_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("image_uploads.image_id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    report_png_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    report_png_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_pdf_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    report_pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    finalized_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TploRotationTableModel(Base):
    __tablename__ = "tplo_rotation_tables"
    __table_args__ = (
        CheckConstraint("length(table_version) > 0", name="ck_tplo_rotation_table_version_nonempty"),
        CheckConstraint("length(source) > 0", name="ck_tplo_rotation_table_source_nonempty"),
        CheckConstraint("length(source_url) > 0", name="ck_tplo_rotation_table_source_url_nonempty"),
        CheckConstraint("length(source_asset_url) > 0", name="ck_tplo_rotation_table_asset_url_nonempty"),
        CheckConstraint("length(entries_sha256) = 64", name="ck_tplo_rotation_table_hash_length"),
        CheckConstraint(
            "target_slope_degrees > 0 AND target_slope_degrees < 90",
            name="ck_tplo_rotation_table_slope_range",
        ),
        UniqueConstraint("table_version", name="uq_tplo_rotation_tables_version"),
        Index(
            "uq_tplo_rotation_tables_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    table_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_asset_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_slope_degrees: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    entries: Mapped[list[dict[str, float | int]]] = mapped_column(JSON, nullable=False)
    entries_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImplantCatalogImportModel(Base):
    __tablename__ = "implant_catalog_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AWAITING_SOURCE', 'WAITING_FOR_CONVERTER', 'QUEUED', 'PROCESSING', "
            "'REVIEW_REQUIRED', 'APPROVED', 'REJECTED', 'FAILED')",
            name="ck_implant_catalog_imports_status",
        ),
        Index("ix_implant_catalog_imports_status_created", "status", "created_at"),
        Index("ix_implant_catalog_imports_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_media_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True, unique=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    svg_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    editable_asset_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    editable_asset_media_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    preview_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    conversion_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    converter_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
