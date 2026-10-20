from dataclasses import dataclass

from vetorthoplan.application.errors import ImageContentRejectedError
from vetorthoplan.application.ports import (
    Clock,
    ImageContentInspector,
    ImageUploadRepository,
    IngestionJobQueue,
    UploadStorage,
)
from vetorthoplan.domain.imaging import ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob


@dataclass(frozen=True, slots=True)
class ProcessedImageIngestion:
    job: IngestionJob
    image: ImageUpload | None


class ProcessNextImageIngestion:
    def __init__(
        self,
        *,
        job_queue: IngestionJobQueue,
        upload_repository: ImageUploadRepository,
        storage: UploadStorage,
        inspector: ImageContentInspector,
        clock: Clock,
    ) -> None:
        self._job_queue = job_queue
        self._upload_repository = upload_repository
        self._storage = storage
        self._inspector = inspector
        self._clock = clock

    async def execute(self) -> ProcessedImageIngestion | None:
        job = await self._job_queue.claim_next(self._clock.now())
        if job is None:
            return None

        upload = await self._upload_repository.get_by_id(job.tenant_id, job.upload_id)
        if upload is None:
            failed = job.fail(finished_at=self._clock.now(), error_code="upload_not_found")
            return ProcessedImageIngestion(job=await self._job_queue.save(failed), image=None)

        try:
            if upload.status == ImageUploadStatus.QUARANTINED:
                upload = await self._upload_repository.save(upload.start_processing())
            content = await self._storage.read_uploaded_object(upload)
            inspected = self._inspector.inspect(
                content,
                expected_kind=upload.kind,
                expected_sha256=upload.sha256,
            )
            preview = await self._storage.store_preview(
                upload,
                inspected.preview_content,
                inspected.preview_media_type,
            )
        except ImageContentRejectedError as exc:
            rejected_image = upload.reject(
                rejection_code=exc.code,
                processed_at=self._clock.now(),
            )
            rejected_job = job.reject(finished_at=self._clock.now(), error_code=exc.code)
            return ProcessedImageIngestion(
                job=await self._job_queue.save(rejected_job),
                image=await self._upload_repository.save(rejected_image),
            )
        except Exception:
            failed = job.fail(finished_at=self._clock.now(), error_code="processing_failed")
            failed_image = upload.fail(processed_at=self._clock.now())
            return ProcessedImageIngestion(
                job=await self._job_queue.save(failed),
                image=await self._upload_repository.save(failed_image),
            )

        ready_image = upload.mark_ready(
            detected_media_type=inspected.media_type,
            width_px=inspected.width_px,
            height_px=inspected.height_px,
            metadata=inspected.metadata,
            preview_object_key=preview.object_key,
            preview_media_type=preview.media_type,
            preview_width_px=inspected.preview_width_px,
            preview_height_px=inspected.preview_height_px,
            processed_at=self._clock.now(),
        )
        succeeded_job = job.succeed(finished_at=self._clock.now())
        return ProcessedImageIngestion(
            job=await self._job_queue.save(succeeded_job),
            image=await self._upload_repository.save(ready_image),
        )
