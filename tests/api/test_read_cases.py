from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import get_case, get_list_cases, get_tenant_context
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.ports import CaseCursor, CasePage
from vetorthoplan.application.use_cases import GetCase, ListCases
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.cases import Case, CaseStatus

TENANT_ID = UUID("00000000-0000-4000-8000-000000000061")
OTHER_TENANT_ID = UUID("00000000-0000-4000-8000-000000000062")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000063")
FIRST_CASE_ID = UUID("00000000-0000-4000-8000-000000000064")
SECOND_CASE_ID = UUID("00000000-0000-4000-8000-000000000065")
OTHER_CASE_ID = UUID("00000000-0000-4000-8000-000000000066")
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def make_case(case_id: UUID, tenant_id: UUID, title: str, created_at: datetime) -> Case:
    return Case.create(
        case_id=case_id,
        tenant_id=tenant_id,
        actor_id=ACTOR_ID,
        title=title,
        animal_name=f"Animal {case_id.int % 100}",
        species="Canina",
        now=created_at,
    )


class InMemoryReadCaseRepository:
    def __init__(self) -> None:
        self.cases = [
            make_case(FIRST_CASE_ID, TENANT_ID, "TPLO joelho direito", NOW),
            make_case(SECOND_CASE_ID, TENANT_ID, "Controle pós-operatório", NOW - timedelta(days=1)),
            make_case(OTHER_CASE_ID, OTHER_TENANT_ID, "Caso de outro tenant", NOW + timedelta(days=1)),
        ]

    async def add(self, case: Case) -> Case:
        self.cases.append(case)
        return case

    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None:
        return next(
            (case for case in self.cases if case.tenant_id == tenant_id and case.id == case_id),
            None,
        )

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: CaseCursor | None,
        status: CaseStatus | None,
        search: str | None,
    ) -> CasePage:
        cases = [case for case in self.cases if case.tenant_id == tenant_id]
        if status is not None:
            cases = [case for case in cases if case.status == status]
        if search is not None:
            needle = search.casefold()
            cases = [
                case
                for case in cases
                if needle
                in " ".join(
                    value
                    for value in (case.title, case.animal_name, case.species, case.breed)
                    if value
                ).casefold()
            ]

        cases.sort(key=lambda case: (case.created_at, case.id.int), reverse=True)
        if cursor is not None:
            cases = [
                case
                for case in cases
                if case.created_at < cursor.created_at
                or (case.created_at == cursor.created_at and case.id.int < cursor.case_id.int)
            ]

        page_cases = cases[:limit]
        next_cursor = None
        if len(cases) > limit:
            last_case = page_cases[-1]
            next_cursor = CaseCursor(created_at=last_case.created_at, case_id=last_case.id)
        return CasePage(items=tuple(page_cases), next_cursor=next_cursor)


def build_app():
    app = create_app()
    repository = InMemoryReadCaseRepository()
    app.dependency_overrides[get_list_cases] = lambda: ListCases(repository)
    app.dependency_overrides[get_case] = lambda: GetCase(repository)
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    return app


@pytest.mark.asyncio
async def test_get_cases_paginates_with_opaque_cursor_and_hides_other_tenants() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        first_page = await client.get("/api/v1/cases", params={"limit": 1})
        cursor = first_page.json()["next_cursor"]
        second_page = await client.get(
            "/api/v1/cases",
            params={"limit": 1, "cursor": cursor},
        )

    assert first_page.status_code == 200
    assert [item["id"] for item in first_page.json()["items"]] == [str(FIRST_CASE_ID)]
    assert cursor is not None
    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["items"]] == [str(SECOND_CASE_ID)]
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_cases_filters_by_status_and_search() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/cases",
            params={"status": "DRAFT", "search": "joelho"},
        )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(FIRST_CASE_ID)]


@pytest.mark.asyncio
async def test_get_case_returns_details_for_active_tenant() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/cases/{FIRST_CASE_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == str(FIRST_CASE_ID)
    assert response.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_get_case_returns_same_not_found_for_absent_or_other_tenant_case() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/cases/{OTHER_CASE_ID}")

    assert response.status_code == 404
    assert response.json() == {
        "code": "CASE_NOT_FOUND",
        "message": "Caso clínico não encontrado.",
        "details": {"case_id": str(OTHER_CASE_ID)},
        "trace_id": None,
    }


@pytest.mark.asyncio
async def test_get_cases_rejects_invalid_cursor() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/cases", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CURSOR"


@pytest.mark.asyncio
async def test_openapi_documents_case_read_endpoints() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    list_operation = schema["paths"]["/api/v1/cases"]["get"]
    detail_operation = schema["paths"]["/api/v1/cases/{case_id}"]["get"]
    assert list_operation["summary"] == "Listar casos clínicos"
    assert {parameter["name"] for parameter in list_operation["parameters"]} == {
        "limit",
        "cursor",
        "status",
        "search",
    }
    assert "200" in list_operation["responses"]
    assert detail_operation["summary"] == "Consultar caso clínico"
    assert "404" in detail_operation["responses"]
