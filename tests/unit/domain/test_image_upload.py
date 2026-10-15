from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from vetorthoplan.domain.imaging import (
    ImageKind,
    ImageUpload,
    ImageUploadStatus,
    ImagingValidationError,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def build_upload(**overrides: object) -> ImageUpload:
    values = {
        "upload_id": UUID("00000000-0000-4000-8000-000000000101"),
        "image_id": UUID("00000000-0000-4000-8000-000000000102"),
        "tenant_id": UUID("00000000-0000-4000-8000-000000000103"),
        "case_id": UUID("00000000-0000-4000-8000-000000000104"),
        "actor_id": UUID("00000000-0000-4000-8000-000000000105"),
        "original_filename": "joelho-direito.dcm",
        "media_type": "application/dicom",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "object_key": "quarantine/test/file.dcm",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return ImageUpload.create(**values)  # type: ignore[arg-type]


def test_create_image_upload_normalizes_metadata() -> None:
    upload = build_upload(media_type=" IMAGE/PNG ", original_filename="imagem.png", sha256="A" * 64)

    assert upload.kind == ImageKind.PNG
    assert upload.media_type == "image/png"
    assert upload.sha256 == "a" * 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("original_filename", "../imagem.png"),
        ("original_filename", "imagem.exe"),
        ("media_type", "application/pdf"),
        ("size_bytes", 104_857_601),
        ("sha256", "invalid"),
    ],
)
def test_create_image_upload_rejects_unsafe_metadata(field: str, value: object) -> None:
    overrides = {field: value}
    if field == "original_filename" and value == "imagem.exe":
        overrides["media_type"] = "image/png"

    with pytest.raises(ImagingValidationError):
        build_upload(**overrides)


def test_confirm_image_upload_moves_it_to_quarantine() -> None:
    upload = build_upload()
    completed_at = NOW + timedelta(minutes=2)

    confirmed = upload.confirm(completed_at=completed_at)

    assert confirmed.status == ImageUploadStatus.QUARANTINED
    assert confirmed.completed_at == completed_at
    assert upload.status == ImageUploadStatus.PENDING_UPLOAD
