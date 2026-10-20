from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import ImageNotFoundError, IngestionJobNotFoundError
from vetorthoplan.application.ports import ImageUploadRepository, IngestionJobQueue
from vetorthoplan.domain.jobs import IngestionJob


class GetIngestionJob:
    def __init__(
        self,
        repository: IngestionJobQueue,
        images: ImageUploadRepository | None = None,
    ) -> None:
        self._repository = repository
        self._images = images

    async def execute(self, job_id: UUID, context: TenantContext) -> IngestionJob:
        job = await self._repository.get_by_id(context.tenant_id, job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)
        return job

    async def execute_for_image(self, image_id: UUID, context: TenantContext) -> IngestionJob | None:
        if self._images is not None:
            image = await self._images.get_by_image_id(context.tenant_id, image_id)
            if image is None:
                raise ImageNotFoundError(image_id)
        return await self._repository.get_by_image_id(context.tenant_id, image_id)
