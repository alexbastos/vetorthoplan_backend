from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ImageDeletionConflictError,
    ImageNotFoundError,
)
from vetorthoplan.application.ports import (
    Clock,
    FinalizedPlanRepository,
    ImagePlanRepository,
    ImageUploadRepository,
    IngestionJobQueue,
    UploadStorage,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJobStatus


class DeleteImage:
    def __init__(
        self,
        *,
        images: ImageUploadRepository,
        plans: ImagePlanRepository,
        jobs: IngestionJobQueue,
        storage: UploadStorage,
        clock: Clock,
        finalized_plans: FinalizedPlanRepository | None = None,
    ) -> None:
        self._images = images
        self._plans = plans
        self._jobs = jobs
        self._storage = storage
        self._clock = clock
        self._finalized_plans = finalized_plans

    async def execute(self, image_id: UUID, context: TenantContext) -> None:
        lock_case = getattr(self._images, "lock_case_for_image", None)
        if lock_case is not None and not await lock_case(context.tenant_id, image_id):
            raise ImageNotFoundError(image_id)
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        job = await self._jobs.lock_by_image_id(context.tenant_id, image_id)
        if job is not None and job.status in {
            IngestionJobStatus.QUEUED,
            IngestionJobStatus.PROCESSING,
        }:
            raise ImageDeletionConflictError(image_id)
        if (
            image.status in {ImageUploadStatus.PENDING_UPLOAD, ImageUploadStatus.CANCELLED}
            and image.expires_at > self._clock.now()
        ):
            raise ImageDeletionConflictError(image_id)
        if self._finalized_plans is not None:
            for finalized in await self._finalized_plans.list_for_image(context.tenant_id, image_id):
                await self._storage.delete_object(finalized.report_png_key)
                await self._storage.delete_object(finalized.report_pdf_key)
        if image.preview_object_key:
            await self._storage.delete_object(image.preview_object_key)
        await self._storage.delete_object(image.object_key)
        await self._plans.delete(context.tenant_id, image_id)
        await self._images.delete(context.tenant_id, image.id)
