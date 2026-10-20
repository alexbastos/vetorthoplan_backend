from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import IngestionJobNotFoundError, IngestionJobRetryNotAllowedError
from vetorthoplan.application.ports import Clock, ImageUploadRepository, IngestionJobQueue
from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus


class RetryIngestionJob:
    def __init__(
        self,
        *,
        jobs: IngestionJobQueue,
        images: ImageUploadRepository,
        clock: Clock,
    ) -> None:
        self._jobs = jobs
        self._images = images
        self._clock = clock

    async def execute(self, job_id: UUID, context: TenantContext) -> IngestionJob:
        job = await self._jobs.lock_by_id(context.tenant_id, job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)
        if job.status != IngestionJobStatus.FAILED:
            raise IngestionJobRetryNotAllowedError(job_id)
        upload = await self._images.get_by_id(context.tenant_id, job.upload_id)
        if upload is None:
            raise IngestionJobRetryNotAllowedError(job_id)
        await self._images.save(upload.prepare_retry())
        return await self._jobs.save(job.retry(retried_at=self._clock.now()))
