from dataclasses import dataclass

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.ports import CaseCursor, CasePage, CaseRepository
from vetorthoplan.domain.cases import CaseStatus


@dataclass(frozen=True, slots=True)
class ListCasesQuery:
    limit: int = 20
    cursor: CaseCursor | None = None
    status: CaseStatus | None = None
    search: str | None = None


class ListCases:
    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    async def execute(self, query: ListCasesQuery, context: TenantContext) -> CasePage:
        if not 1 <= query.limit <= 100:
            raise ValueError("limit deve estar entre 1 e 100.")

        normalized_search = query.search.strip() if query.search else None
        return await self._repository.list_by_tenant(
            context.tenant_id,
            limit=query.limit,
            cursor=query.cursor,
            status=query.status,
            search=normalized_search or None,
        )
