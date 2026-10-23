from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ImageUploadCancelledError,
    ImageUploadExpiredError,
    ImageUploadNotFoundError,
    ImageUploadObjectInvalidError,
)
from vetorthoplan.application.ports import (
    Clock,
    IdGenerator,
    ImageUploadRepository,
    IngestionJobQueue,
    UploadStorage,
)
from vetorthoplan.domain.imaging import ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob


@dataclass(frozen=True, slots=True)
class CompletedImageUpload:
    upload: ImageUpload
    ingestion_job: IngestionJob


class CompleteImageUpload:
    def __init__(
        self,
        *,
        repository: ImageUploadRepository,
        job_queue: IngestionJobQueue,
        storage: UploadStorage,
        id_generator: IdGenerator,
        clock: Clock,
        storage_clock_skew_seconds: float = 5.0,
    ) -> None:
        self._repository = repository
        self._job_queue = job_queue
        self._storage = storage
        self._id_generator = id_generator
        self._clock = clock
        self._storage_clock_skew = timedelta(seconds=storage_clock_skew_seconds)

    async def execute(self, upload_id: UUID, context: TenantContext) -> CompletedImageUpload:
        lock_case = getattr(self._repository, "lock_case_for_upload", None)
        if lock_case is not None and not await lock_case(context.tenant_id, upload_id):
            raise ImageUploadNotFoundError(upload_id)
        upload = await self._repository.lock_by_id(context.tenant_id, upload_id)
        if upload is None:
            raise ImageUploadNotFoundError(upload_id)
        if upload.status == ImageUploadStatus.CANCELLED:
            raise ImageUploadCancelledError(upload_id)

        if upload.status == ImageUploadStatus.PENDING_UPLOAD:
            stored = await self._storage.inspect_uploaded_object(upload)
            if stored is None:
                if self._clock.now() >= upload.expires_at:
                    raise ImageUploadExpiredError(upload_id)
                raise ImageUploadObjectInvalidError(upload_id, "object_not_found")

            if stored.uploaded_at < upload.created_at - self._storage_clock_skew:
                raise ImageUploadObjectInvalidError(upload_id, "uploaded_before_session")
            if stored.size_bytes != upload.size_bytes:
                raise ImageUploadObjectInvalidError(upload_id, "size_mismatch")
            if stored.media_type.lower() != upload.media_type:
                raise ImageUploadObjectInvalidError(upload_id, "media_type_mismatch")
            if stored.sha256.lower() != upload.sha256:
                raise ImageUploadObjectInvalidError(upload_id, "checksum_mismatch")
            if stored.upload_id != upload.id:
                raise ImageUploadObjectInvalidError(upload_id, "upload_id_mismatch")

            upload = await self._repository.save(upload.confirm(completed_at=self._clock.now()))

        job = IngestionJob.schedule(
            job_id=self._id_generator.new(),
            tenant_id=upload.tenant_id,
            case_id=upload.case_id,
            image_id=upload.image_id,
            upload_id=upload.id,
            scheduled_at=self._clock.now(),
        )
        scheduled_job = await self._job_queue.enqueue(job)
        return CompletedImageUpload(upload=upload, ingestion_job=scheduled_job)
