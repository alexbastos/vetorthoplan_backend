import hashlib
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from PIL import Image

from vetorthoplan.application.use_cases import ProcessNextImageIngestion
from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus
from vetorthoplan.infrastructure.image_content import BasicImageContentInspector

NOW = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
TENANT_ID = UUID("00000000-0000-4000-8000-000000000401")
CASE_ID = UUID("00000000-0000-4000-8000-000000000402")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000403")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000404")
JOB_ID = UUID("00000000-0000-4000-8000-000000000405")


def png_content() -> bytes:
    output = io.BytesIO()
    Image.new("L", (640, 480), color=127).save(output, format="PNG")
    return output.getvalue()


PNG = png_content()


def make_upload(*, kind: ImageKind = ImageKind.PNG) -> ImageUpload:
    media_type = "image/png" if kind == ImageKind.PNG else "image/jpeg"
    filename = "imagem.png" if kind == ImageKind.PNG else "imagem.jpg"
    upload = ImageUpload.create(
        upload_id=UPLOAD_ID,
        image_id=IMAGE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        actor_id=UUID("00000000-0000-4000-8000-000000000406"),
        original_filename=filename,
        media_type=media_type,
        size_bytes=len(PNG),
        sha256=hashlib.sha256(PNG).hexdigest(),
        object_key="quarantine/synthetic/image",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return upload.confirm(completed_at=NOW)


def make_job() -> IngestionJob:
    return IngestionJob.schedule(
        job_id=JOB_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        image_id=IMAGE_ID,
        upload_id=UPLOAD_ID,
        scheduled_at=NOW,
    )


class JobQueue:
    def __init__(self, job: IngestionJob) -> None:
        self.job = job

    async def claim_next(self, now: datetime) -> IngestionJob | None:
        self.job = self.job.start(started_at=now)
        return self.job

    async def save(self, job: IngestionJob) -> IngestionJob:
        self.job = job
        return job


class UploadRepository:
    def __init__(self, upload: ImageUpload) -> None:
        self.upload = upload

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None:
        return self.upload if tenant_id == TENANT_ID and upload_id == UPLOAD_ID else None

    async def save(self, upload: ImageUpload) -> ImageUpload:
        self.upload = upload
        return upload


class Storage:
    async def read_uploaded_object(self, upload: ImageUpload) -> bytes:
        return PNG

    async def store_preview(self, upload: ImageUpload, content: bytes, media_type: str):
        from vetorthoplan.application.ports import StoredPreviewObject

        assert content.startswith(b"\x89PNG")
        return StoredPreviewObject(object_key="derived/test/preview.png", media_type=media_type)


class Clock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_worker_marks_valid_content_ready() -> None:
    repository = UploadRepository(make_upload())
    queue = JobQueue(make_job())
    use_case = ProcessNextImageIngestion(
        job_queue=queue,
        upload_repository=repository,
        storage=Storage(),
        inspector=BasicImageContentInspector(),
        clock=Clock(),
    )

    result = await use_case.execute()

    assert result is not None
    assert result.job.status == IngestionJobStatus.SUCCEEDED
    assert result.image is not None
    assert result.image.status == ImageUploadStatus.READY
    assert (result.image.width_px, result.image.height_px) == (640, 480)


@pytest.mark.asyncio
async def test_worker_rejects_content_with_different_format() -> None:
    repository = UploadRepository(make_upload(kind=ImageKind.JPEG))
    queue = JobQueue(make_job())
    use_case = ProcessNextImageIngestion(
        job_queue=queue,
        upload_repository=repository,
        storage=Storage(),
        inspector=BasicImageContentInspector(),
        clock=Clock(),
    )

    result = await use_case.execute()

    assert result is not None
    assert result.job.status == IngestionJobStatus.REJECTED
    assert result.job.error_code == "format_mismatch"
    assert result.image is not None
    assert result.image.status == ImageUploadStatus.REJECTED
