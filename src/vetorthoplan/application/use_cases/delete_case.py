from datetime import timedelta
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseDeletionConflictError, CaseNotFoundError
from vetorthoplan.application.ports import (
    CaseRepository,
    Clock,
    FinalizedPlanRepository,
    ImageUploadRepository,
    IngestionJobQueue,
    UploadStorage,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJobStatus


class DeleteCase:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        images: ImageUploadRepository,
        jobs: IngestionJobQueue,
        storage: UploadStorage,
        clock: Clock,
        finalized_plans: FinalizedPlanRepository | None = None,
    ) -> None:
        self._cases = cases
        self._images = images
        self._jobs = jobs
        self._storage = storage
        self._clock = clock
        self._finalized_plans = finalized_plans

    async def execute(self, case_id: UUID, context: TenantContext) -> None:
        lock_case = getattr(self._cases, "lock_by_id", self._cases.get_by_id)
        case = await lock_case(context.tenant_id, case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        images = await self._images.list_for_case(context.tenant_id, case_id, include_cancelled=True)
        now = self._clock.now()
        for image in images:
            if (
                image.status in {ImageUploadStatus.PENDING_UPLOAD, ImageUploadStatus.CANCELLED}
                and image.expires_at > now
            ):
                raise CaseDeletionConflictError(case_id, "ACTIVE_UPLOAD")

        jobs = await self._jobs.list_for_case(context.tenant_id, case_id)
        if any(job.status == IngestionJobStatus.PROCESSING for job in jobs):
            raise CaseDeletionConflictError(case_id, "ACTIVE_INGESTION")
        if any(job.status == IngestionJobStatus.QUEUED for job in jobs):
            raise CaseDeletionConflictError(case_id, "ACTIVE_INGESTION")

        if self._finalized_plans is not None:
            finalizations = await self._finalized_plans.list_for_case(context.tenant_id, case_id)
            for finalized in finalizations:
                await self._storage.delete_object(finalized.report_png_key)
                await self._storage.delete_object(finalized.report_pdf_key)

        # Keep database rows until every object deletion succeeds. Retrying after a
        # storage or database failure is safe because object deletion is idempotent.
        for image in images:
            if image.preview_object_key:
                await self._storage.delete_object(image.preview_object_key)
            await self._storage.delete_object(image.object_key)
        cleanup_keys = [image.object_key for image in images]
        cleanup_keys.extend(image.preview_object_key for image in images if image.preview_object_key)
        await self._cases.schedule_storage_cleanup(cleanup_keys, now + timedelta(minutes=15))
        await self._cases.delete(context.tenant_id, case_id)
