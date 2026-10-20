from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath
from uuid import UUID

from vetorthoplan.domain.imaging.errors import ImagingValidationError

MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class ImageKind(StrEnum):
    DICOM = "DICOM"
    PNG = "PNG"
    JPEG = "JPEG"


class ImageUploadStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    QUARANTINED = "QUARANTINED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


MEDIA_TYPE_TO_KIND = {
    "application/dicom": ImageKind.DICOM,
    "image/dicom": ImageKind.DICOM,
    "image/png": ImageKind.PNG,
    "image/jpeg": ImageKind.JPEG,
}

KIND_EXTENSIONS = {
    ImageKind.DICOM: {".dcm", ".dicom"},
    ImageKind.PNG: {".png"},
    ImageKind.JPEG: {".jpg", ".jpeg"},
}


@dataclass(frozen=True, slots=True)
class ImageUpload:
    id: UUID
    image_id: UUID
    tenant_id: UUID
    case_id: UUID
    original_filename: str
    kind: ImageKind
    media_type: str
    size_bytes: int
    sha256: str
    object_key: str
    status: ImageUploadStatus
    created_by: UUID
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None
    detected_media_type: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    rejection_code: str | None = None
    processed_at: datetime | None = None
    metadata: dict[str, str] | None = None
    preview_object_key: str | None = None
    preview_media_type: str | None = None
    preview_width_px: int | None = None
    preview_height_px: int | None = None
    idempotency_key_hash: str | None = None
    request_hash: str | None = None

    @classmethod
    def create(
        cls,
        *,
        upload_id: UUID,
        image_id: UUID,
        tenant_id: UUID,
        case_id: UUID,
        actor_id: UUID,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
        object_key: str,
        created_at: datetime,
        expires_at: datetime,
        idempotency_key_hash: str | None = None,
        request_hash: str | None = None,
    ) -> ImageUpload:
        filename = original_filename.strip()
        if not filename or len(filename) > 255 or PurePath(filename).name != filename:
            raise ImagingValidationError(
                "original_filename deve conter somente um nome de arquivo válido.",
                field="original_filename",
            )

        normalized_media_type = media_type.strip().lower()
        kind = MEDIA_TYPE_TO_KIND.get(normalized_media_type)
        if kind is None:
            raise ImagingValidationError(
                "media_type deve ser DICOM, PNG ou JPEG.",
                field="media_type",
            )

        if PurePath(filename).suffix.lower() not in KIND_EXTENSIONS[kind]:
            raise ImagingValidationError(
                "A extensão do arquivo não corresponde ao media_type declarado.",
                field="original_filename",
            )

        if size_bytes <= 0 or size_bytes > MAX_UPLOAD_SIZE_BYTES:
            raise ImagingValidationError(
                f"size_bytes deve estar entre 1 e {MAX_UPLOAD_SIZE_BYTES} bytes.",
                field="size_bytes",
            )

        normalized_sha256 = sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized_sha256):
            raise ImagingValidationError(
                "sha256 deve ser um digest hexadecimal de 64 caracteres.",
                field="sha256",
            )

        if created_at.tzinfo is None or expires_at.tzinfo is None:
            raise ImagingValidationError("Datas de upload devem conter timezone.")
        if expires_at <= created_at:
            raise ImagingValidationError("expires_at deve ser posterior a created_at.")

        return cls(
            id=upload_id,
            image_id=image_id,
            tenant_id=tenant_id,
            case_id=case_id,
            original_filename=filename,
            kind=kind,
            media_type=normalized_media_type,
            size_bytes=size_bytes,
            sha256=normalized_sha256,
            object_key=object_key,
            status=ImageUploadStatus.PENDING_UPLOAD,
            created_by=actor_id,
            created_at=created_at,
            expires_at=expires_at,
            completed_at=None,
            idempotency_key_hash=idempotency_key_hash,
            request_hash=request_hash,
        )

    def confirm(self, *, completed_at: datetime) -> ImageUpload:
        if self.status != ImageUploadStatus.PENDING_UPLOAD:
            return self
        if completed_at.tzinfo is None:
            raise ImagingValidationError("completed_at deve conter timezone.")
        return replace(
            self,
            status=ImageUploadStatus.QUARANTINED,
            completed_at=completed_at,
        )

    def cancel(self) -> ImageUpload:
        if self.status == ImageUploadStatus.CANCELLED:
            return self
        if self.status != ImageUploadStatus.PENDING_UPLOAD:
            raise ImagingValidationError("Somente sessões PENDING_UPLOAD podem ser canceladas.")
        return replace(self, status=ImageUploadStatus.CANCELLED)

    def start_processing(self) -> ImageUpload:
        if self.status == ImageUploadStatus.PROCESSING:
            return self
        if self.status != ImageUploadStatus.QUARANTINED:
            raise ImagingValidationError("Somente imagens em quarentena podem ser processadas.")
        return replace(self, status=ImageUploadStatus.PROCESSING)

    def mark_ready(
        self,
        *,
        detected_media_type: str,
        width_px: int | None,
        height_px: int | None,
        metadata: dict[str, str],
        preview_object_key: str,
        preview_media_type: str,
        preview_width_px: int,
        preview_height_px: int,
        processed_at: datetime,
    ) -> ImageUpload:
        if self.status != ImageUploadStatus.PROCESSING:
            raise ImagingValidationError("Somente imagens em processamento podem ficar prontas.")
        if processed_at.tzinfo is None:
            raise ImagingValidationError("processed_at deve conter timezone.")
        if (width_px is None) != (height_px is None):
            raise ImagingValidationError("Dimensões devem ser informadas em conjunto.")
        if width_px is not None and (width_px <= 0 or height_px is None or height_px <= 0):
            raise ImagingValidationError("Dimensões da imagem devem ser positivas.")
        if not preview_object_key or preview_media_type != "image/png":
            raise ImagingValidationError("A imagem pronta deve possuir uma prévia PNG.")
        if preview_width_px <= 0 or preview_height_px <= 0:
            raise ImagingValidationError("As dimensões da prévia devem ser positivas.")
        return replace(
            self,
            status=ImageUploadStatus.READY,
            detected_media_type=detected_media_type,
            width_px=width_px,
            height_px=height_px,
            metadata=dict(metadata),
            preview_object_key=preview_object_key,
            preview_media_type=preview_media_type,
            preview_width_px=preview_width_px,
            preview_height_px=preview_height_px,
            rejection_code=None,
            processed_at=processed_at,
        )

    def reject(self, *, rejection_code: str, processed_at: datetime) -> ImageUpload:
        if self.status not in {ImageUploadStatus.QUARANTINED, ImageUploadStatus.PROCESSING}:
            raise ImagingValidationError("Somente imagens pendentes de ingestão podem ser rejeitadas.")
        if not rejection_code or len(rejection_code) > 64:
            raise ImagingValidationError("rejection_code inválido.")
        if processed_at.tzinfo is None:
            raise ImagingValidationError("processed_at deve conter timezone.")
        return replace(
            self,
            status=ImageUploadStatus.REJECTED,
            rejection_code=rejection_code,
            processed_at=processed_at,
        )

    def fail(self, *, processed_at: datetime) -> ImageUpload:
        if self.status not in {ImageUploadStatus.QUARANTINED, ImageUploadStatus.PROCESSING}:
            raise ImagingValidationError("Somente imagens em ingestão podem falhar operacionalmente.")
        if processed_at.tzinfo is None:
            raise ImagingValidationError("processed_at deve conter timezone.")
        return replace(self, status=ImageUploadStatus.FAILED, rejection_code=None, processed_at=processed_at)

    def prepare_retry(self) -> ImageUpload:
        if self.status != ImageUploadStatus.FAILED:
            raise ImagingValidationError("Somente imagens com falha operacional podem ser reenfileiradas.")
        return replace(self, status=ImageUploadStatus.QUARANTINED, processed_at=None)
