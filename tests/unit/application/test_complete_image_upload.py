from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ImageUploadExpiredError,
    ImageUploadNotFoundError,
    ImageUploadObjectInvalidError,
)
from vetorthoplan.application.ports import StoredUploadObject
from vetorthoplan.application.use_cases import CompleteImageUpload
from vetorthoplan.domain.imaging import ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus

UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000201")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000202")
CASE_ID = UUID("00000000-0000-4000-8000-000000000203")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000204")
OTHER_TENANT_ID = UUID("00000000-0000-4000-8000-000000000205")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000206")
JOB_ID = UUID("00000000-0000-4000-8000-000000000207")
NOW = datetime(2026, 9, 17, 13, 0, tzinfo=UTC)


def make_upload(*, quarantined: bool = False) -> ImageUpload:
    upload = ImageUpload.create(
        upload_id=UPLOAD_ID,
        image_id=IMAGE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        actor_id=ACTOR_ID,
        original_filename="joelho.dcm",
        media_type="application/dicom",
        size_bytes=4096,
        sha256="e" * 64,
        object_key="quarantine/test/joelho.dcm",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return upload.confirm(completed_at=NOW + timedelta(minutes=2)) if quarantined else upload


class Repository:
    def __init__(self, upload: ImageUpload | None) -> None:
        self.upload = upload
        self.saved: list[ImageUpload] = []

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None:
        if self.upload is None or tenant_id != self.upload.tenant_id or upload_id != self.upload.id:
            return None
        return self.upload

    async def save(self, upload: ImageUpload) -> ImageUpload:
        self.upload = upload
        self.saved.append(upload)
        return upload


class Storage:
    def __init__(self, stored: StoredUploadObject | None) -> None:
        self.stored = stored
        self.inspections = 0

    async def inspect_uploaded_object(self, upload: ImageUpload) -> StoredUploadObject | None:
        self.inspections += 1
        return self.stored


class Clock:
    def __init__(self, now: datetime = NOW + timedelta(minutes=3)) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class IdGenerator:
    def new(self) -> UUID:
        return JOB_ID


class JobQueue:
    def __init__(self, existing: IngestionJob | None = None) -> None:
        self.job = existing
        self.enqueued: list[IngestionJob] = []

    async def enqueue(self, job: IngestionJob) -> IngestionJob:
        self.enqueued.append(job)
        if self.job is None:
            self.job = job
        return self.job


def build_use_case(
    *,
    repository: Repository,
    storage: Storage,
    job_queue: JobQueue | None = None,
    clock: Clock | None = None,
) -> CompleteImageUpload:
    return CompleteImageUpload(
        repository=repository,
        job_queue=job_queue or JobQueue(),
        storage=storage,
        id_generator=IdGenerator(),
        clock=clock or Clock(),
    )


def valid_stored_object(**overrides: object) -> StoredUploadObject:
    values = {
        "size_bytes": 4096,
        "media_type": "application/dicom",
        "sha256": "e" * 64,
        "upload_id": UPLOAD_ID,
        "uploaded_at": NOW + timedelta(minutes=1),
    }
    values.update(overrides)
    return StoredUploadObject(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_complete_image_upload_verifies_and_quarantines_object() -> None:
    repository = Repository(make_upload())
    storage = Storage(valid_stored_object())
    job_queue = JobQueue()
    use_case = build_use_case(repository=repository, storage=storage, job_queue=job_queue)

    result = await use_case.execute(
        UPLOAD_ID,
        TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
    )

    assert result.upload.status == ImageUploadStatus.QUARANTINED
    assert result.upload.completed_at == NOW + timedelta(minutes=3)
    assert result.ingestion_job.status == IngestionJobStatus.QUEUED
    assert result.ingestion_job.upload_id == UPLOAD_ID
    assert repository.saved == [result.upload]
    assert job_queue.enqueued == [result.ingestion_job]
    assert storage.inspections == 1


@pytest.mark.asyncio
async def test_complete_image_upload_is_idempotent() -> None:
    repository = Repository(make_upload(quarantined=True))
    storage = Storage(None)
    existing_job = IngestionJob.schedule(
        job_id=JOB_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        image_id=IMAGE_ID,
        upload_id=UPLOAD_ID,
        scheduled_at=NOW,
    )
    job_queue = JobQueue(existing_job)
    use_case = build_use_case(repository=repository, storage=storage, job_queue=job_queue)

    result = await use_case.execute(
        UPLOAD_ID,
        TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
    )

    assert result.upload.status == ImageUploadStatus.QUARANTINED
    assert result.ingestion_job == existing_job
    assert storage.inspections == 0
    assert repository.saved == []
    assert len(job_queue.enqueued) == 1


@pytest.mark.asyncio
async def test_complete_image_upload_hides_other_tenant() -> None:
    use_case = build_use_case(
        repository=Repository(make_upload()),
        storage=Storage(valid_stored_object()),
    )

    with pytest.raises(ImageUploadNotFoundError):
        await use_case.execute(
            UPLOAD_ID,
            TenantContext(tenant_id=OTHER_TENANT_ID, actor_id=ACTOR_ID),
        )


@pytest.mark.asyncio
async def test_complete_image_upload_reports_expired_missing_object() -> None:
    use_case = build_use_case(
        repository=Repository(make_upload()),
        storage=Storage(None),
        clock=Clock(NOW + timedelta(minutes=6)),
    )

    with pytest.raises(ImageUploadExpiredError):
        await use_case.execute(
            UPLOAD_ID,
            TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
        )


@pytest.mark.asyncio
async def test_complete_image_upload_reports_missing_object_before_expiration() -> None:
    use_case = build_use_case(
        repository=Repository(make_upload()),
        storage=Storage(None),
        clock=Clock(NOW + timedelta(minutes=2)),
    )

    with pytest.raises(ImageUploadObjectInvalidError) as error:
        await use_case.execute(
            UPLOAD_ID,
            TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
        )

    assert error.value.reason == "object_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"size_bytes": 1024}, "size_mismatch"),
        ({"media_type": "image/png"}, "media_type_mismatch"),
        ({"sha256": "f" * 64}, "checksum_mismatch"),
        ({"upload_id": OTHER_TENANT_ID}, "upload_id_mismatch"),
        ({"uploaded_at": NOW - timedelta(minutes=1)}, "uploaded_before_session"),
    ],
)
async def test_complete_image_upload_rejects_divergent_object(
    overrides: dict[str, object],
    reason: str,
) -> None:
    use_case = build_use_case(
        repository=Repository(make_upload()),
        storage=Storage(valid_stored_object(**overrides)),
    )

    with pytest.raises(ImageUploadObjectInvalidError) as error:
        await use_case.execute(
            UPLOAD_ID,
            TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
        )

    assert error.value.reason == reason
