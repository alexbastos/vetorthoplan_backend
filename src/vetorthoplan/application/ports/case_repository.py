from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.cases import Case, CaseStatus


@dataclass(frozen=True, slots=True)
class CaseCursor:
    created_at: datetime
    case_id: UUID


@dataclass(frozen=True, slots=True)
class CasePage:
    items: tuple[Case, ...]
    next_cursor: CaseCursor | None


class CaseRepository(Protocol):
    async def add(self, case: Case) -> Case: ...

    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None: ...

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: CaseCursor | None,
        status: CaseStatus | None,
        search: str | None,
    ) -> CasePage: ...
