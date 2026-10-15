from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import IngestionJobNotFoundError
from vetorthoplan.application.ports import IngestionJobQueue
from vetorthoplan.domain.jobs import IngestionJob


class GetIngestionJob:
    def __init__(self, repository: IngestionJobQueue) -> None:
        self._repository = repository

    async def execute(self, job_id: UUID, context: TenantContext) -> IngestionJob:
        job = await self._repository.get_by_id(context.tenant_id, job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)
        return job
