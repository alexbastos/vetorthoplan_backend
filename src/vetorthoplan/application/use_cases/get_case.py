from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseNotFoundError
from vetorthoplan.application.ports import CaseRepository
from vetorthoplan.domain.cases import Case


class GetCase:
    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    async def execute(self, case_id: UUID, context: TenantContext) -> Case:
        case = await self._repository.get_by_id(context.tenant_id, case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case
