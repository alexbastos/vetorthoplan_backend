from datetime import UTC, datetime
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import CreateCase, CreateCaseCommand
from vetorthoplan.domain.cases import Case

CASE_ID = UUID("00000000-0000-4000-8000-000000000020")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000021")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000022")
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class InMemoryCaseRepository:
    def __init__(self) -> None:
        self.cases: list[Case] = []

    async def add(self, case: Case) -> Case:
        self.cases.append(case)
        return case


class FixedIdGenerator:
    def new(self) -> UUID:
        return CASE_ID


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_create_case_uses_context_instead_of_command_for_tenant_and_actor() -> None:
    repository = InMemoryCaseRepository()
    use_case = CreateCase(repository, FixedIdGenerator(), FixedClock())

    case = await use_case.execute(
        CreateCaseCommand(
            title="Planejamento TPLO",
            animal_name="Paciente sintético",
            species="Canina",
        ),
        TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
    )

    assert repository.cases == [case]
    assert case.id == CASE_ID
    assert case.tenant_id == TENANT_ID
    assert case.created_by == ACTOR_ID
