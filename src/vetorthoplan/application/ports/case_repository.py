from dataclasses import dataclass, field
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
    status_counts: dict[CaseStatus, int] = field(default_factory=dict)


class CaseRepository(Protocol):
    async def add(self, case: Case) -> Case: ...

    async def add_idempotently(
        self,
        case: Case,
        *,
        key_hash: str,
        request_hash: str,
    ) -> Case: ...

    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None: ...

    async def lock_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None: ...

    async def delete(self, tenant_id: UUID, case_id: UUID) -> None: ...

    async def schedule_storage_cleanup(self, object_keys: list[str], cleanup_after) -> None: ...

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: CaseCursor | None,
        status: CaseStatus | None,
        search: str | None,
    ) -> CasePage: ...
