from datetime import UTC, datetime
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseNotFoundError
from vetorthoplan.application.ports import CaseCursor, CasePage
from vetorthoplan.application.use_cases import GetCase, ListCases, ListCasesQuery
from vetorthoplan.domain.cases import BiologicalSex, Case, CaseStatus

CASE_ID = UUID("00000000-0000-4000-8000-000000000050")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000051")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000052")
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def make_case() -> Case:
    return Case.create(
        case_id=CASE_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        title="Planejamento TPLO",
        animal_name="Paciente sintético",
        species="Canina",
        sex=BiologicalSex.UNKNOWN,
        now=NOW,
    )


class RecordingCaseRepository:
    def __init__(self, case: Case | None = None) -> None:
        self.case = case
        self.list_call: dict[str, object] | None = None
        self.get_call: tuple[UUID, UUID] | None = None

    async def add(self, case: Case) -> Case:
        return case

    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None:
        self.get_call = (tenant_id, case_id)
        return self.case

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: CaseCursor | None,
        status: CaseStatus | None,
        search: str | None,
    ) -> CasePage:
        self.list_call = {
            "tenant_id": tenant_id,
            "limit": limit,
            "cursor": cursor,
            "status": status,
            "search": search,
        }
        return CasePage(items=(self.case,) if self.case else (), next_cursor=None)


@pytest.mark.asyncio
async def test_list_cases_scopes_query_to_tenant_and_normalizes_search() -> None:
    case = make_case()
    repository = RecordingCaseRepository(case)
    cursor = CaseCursor(created_at=NOW, case_id=CASE_ID)
    context = TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID)

    page = await ListCases(repository).execute(
        ListCasesQuery(
            limit=10,
            cursor=cursor,
            status=CaseStatus.DRAFT,
            search="  Paciente  ",
        ),
        context,
    )

    assert page.items == (case,)
    assert repository.list_call == {
        "tenant_id": TENANT_ID,
        "limit": 10,
        "cursor": cursor,
        "status": CaseStatus.DRAFT,
        "search": "Paciente",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_list_cases_rejects_limit_outside_contract(limit: int) -> None:
    repository = RecordingCaseRepository()
    context = TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID)

    with pytest.raises(ValueError, match="limit deve estar entre 1 e 100"):
        await ListCases(repository).execute(ListCasesQuery(limit=limit), context)


@pytest.mark.asyncio
async def test_get_case_scopes_lookup_to_active_tenant() -> None:
    case = make_case()
    repository = RecordingCaseRepository(case)
    context = TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID)

    result = await GetCase(repository).execute(CASE_ID, context)

    assert result == case
    assert repository.get_call == (TENANT_ID, CASE_ID)


@pytest.mark.asyncio
async def test_get_case_raises_not_found_without_leaking_tenant_information() -> None:
    repository = RecordingCaseRepository()
    context = TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID)

    with pytest.raises(CaseNotFoundError, match="Caso clínico não encontrado"):
        await GetCase(repository).execute(CASE_ID, context)
