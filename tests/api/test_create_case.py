from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import get_create_case, get_tenant_context
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import CreateCase
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.cases import Case

CASE_ID = UUID("00000000-0000-4000-8000-000000000030")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000031")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000032")
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


def build_app():
    app = create_app()
    repository = InMemoryCaseRepository()
    use_case = CreateCase(repository, FixedIdGenerator(), FixedClock())
    app.dependency_overrides[get_create_case] = lambda: use_case
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    return app


@pytest.mark.asyncio
async def test_post_case_returns_created_case_and_context_ids() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/cases",
            json={
                "title": "Planejamento TPLO — joelho direito",
                "animal_name": "Paciente sintético 01",
                "species": "Canina",
                "approximate_age_months": 72,
                "weight_kg": 31.4,
            },
        )

    assert response.status_code == 201
    assert response.json()["tenant_id"] == str(TENANT_ID)
    assert response.json()["created_by"] == str(ACTOR_ID)
    assert response.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_post_case_rejects_birth_date_and_approximate_age_together() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/cases",
            json={
                "title": "Planejamento TPLO",
                "animal_name": "Paciente sintético",
                "species": "Canina",
                "birth_date": "2020-01-01",
                "approximate_age_months": 72,
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "code": "CASE_VALIDATION_ERROR",
        "message": "Informe birth_date ou approximate_age_months, não ambos.",
        "details": {"field": "approximate_age_months"},
        "trace_id": None,
    }


@pytest.mark.asyncio
async def test_post_case_uses_standard_error_for_invalid_request() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/cases",
            json={
                "title": "Planejamento TPLO",
                "animal_name": "Paciente sintético",
                "species": "Canina",
                "weight_kg": -1,
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["details"]["errors"] == [
        {"field": "weight_kg", "type": "greater_than"}
    ]


@pytest.mark.asyncio
async def test_openapi_documents_case_creation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    operation = schema["paths"]["/api/v1/cases"]["post"]
    assert operation["summary"] == "Criar caso clínico"
    assert "201" in operation["responses"]
    assert "422" in operation["responses"]
