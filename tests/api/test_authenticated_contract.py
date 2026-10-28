from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import (
    get_database_session,
    get_save_image_plan,
    get_tenant_context,
    get_validate_image_plan,
)
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import ValidateImagePlan
from vetorthoplan.bootstrap import create_app
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.domain.imaging import ImageUploadStatus

TENANT_ID = UUID("00000000-0000-4000-8000-000000000901")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000902")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000903")
CATALOG_ITEM_ID = UUID("00000000-0000-4000-8000-000000000904")


class EmptyScalarResult:
    def all(self):
        return []

    def __iter__(self):
        return iter(())


class EmptySession:
    async def scalars(self, _statement):
        return EmptyScalarResult()


class CatalogSession:
    async def scalars(self, _statement):
        return EmptyScalarResultWithRows(
            [SimpleNamespace(id=CATALOG_ITEM_ID, metadata_json={"variants": ["small"], "views": ["lateral"]})]
        )


class EmptyScalarResultWithRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class SaveShouldNotRun:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("O plano não deve ser salvo quando a referência de implante é inválida")


class ContractImages:
    async def get_by_image_id(self, _tenant_id, image_id):
        if image_id != IMAGE_ID:
            return None
        return SimpleNamespace(
            status=ImageUploadStatus.READY,
            width_px=640,
            height_px=480,
        )


class ContractPlans:
    def __init__(self, document):
        self.plan = SimpleNamespace(revision=3, document=document)

    async def get(self, _tenant_id, _image_id):
        return self.plan


class ContractFinalizations:
    def __init__(self, finalized=False):
        self.finalized = finalized

    async def latest(self, _tenant_id, _image_id):
        return object() if self.finalized else None


class EmptyImplantCatalog:
    async def approved_metadata(self, _tenant_id, _item_ids):
        return {}


class ContractClock:
    def now(self):
        return datetime(2026, 10, 28, tzinfo=UTC)


async def _empty_database_session():
    yield EmptySession()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Bearer not-a-jwt"])
async def test_protected_api_rejects_missing_or_invalid_bearer(authorization: str | None) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        identity_mode="jwt",
        jwt_issuer="https://identity.example",
        jwks_url="https://identity.example/jwks",
    )
    app.dependency_overrides[get_database_session] = _empty_database_session
    headers = {"Authorization": authorization} if authorization else {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/cases", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_catalog_admin_requires_authorization_even_for_authenticated_tenant() -> None:
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test", implant_catalog_admin_token=None
    )
    app.dependency_overrides[get_database_session] = _empty_database_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/implant-catalog/imports",
            json={
                "manufacturer": "Fabricante teste",
                "product_name": "Placa teste",
                "family": "TPLO",
                "catalog_version": "v1",
                "units": "MM",
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_plan_rejects_implant_not_approved_for_active_tenant() -> None:
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_database_session] = _empty_database_session
    app.dependency_overrides[get_save_image_plan] = lambda: SaveShouldNotRun()
    document = {
        "schema_version": 1,
        "calibration": None,
        "tplo": None,
        "tplo_landmarks": None,
        "tplo_measurement": None,
        "radiographic_quality": None,
        "additional_measurements_input": {"landmarks": {}, "reference_values": {}},
        "additional_measurements": [],
        "clinical_validation": None,
        "objects": [
            {
                "id": str(UUID("00000000-0000-4000-8000-000000000905")),
                "type": "IMPLANT",
                "catalog_item_id": str(CATALOG_ITEM_ID),
                "position": {"x": 0.5, "y": 0.5},
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/images/{IMAGE_ID}/plan",
            json={"base_revision": 0, "document": document},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "IMPLANT_NOT_AVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice_field", "choice", "expected_code"),
    [("variant", "large", "IMPLANT_VARIANT_INVALID"), ("view", "cranial", "IMPLANT_VIEW_INVALID")],
)
async def test_plan_rejects_implant_variant_or_view_outside_catalog(
    choice_field: str, choice: str, expected_code: str
) -> None:
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_database_session] = _catalog_database_session
    app.dependency_overrides[get_save_image_plan] = lambda: SaveShouldNotRun()
    implant = {
        "id": str(UUID("00000000-0000-4000-8000-000000000905")),
        "type": "IMPLANT",
        "catalog_item_id": str(CATALOG_ITEM_ID),
        "position": {"x": 0.5, "y": 0.5},
        choice_field: choice,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/images/{IMAGE_ID}/plan",
            json={"base_revision": 0, "document": _plan_document(implant)},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected_code


def _plan_document(implant: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "calibration": None,
        "tplo": None,
        "tplo_landmarks": None,
        "tplo_measurement": None,
        "radiographic_quality": None,
        "additional_measurements_input": {"landmarks": {}, "reference_values": {}},
        "additional_measurements": [],
        "clinical_validation": None,
        "objects": [implant],
    }


async def _catalog_database_session():
    yield CatalogSession()


@pytest.mark.asyncio
async def test_plan_validation_reports_ineligible_image_as_blocking() -> None:
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_validate_image_plan] = lambda: ValidateImagePlan(
        plans=ContractPlans({"tplo": {"eligibility": "INELIGIBLE"}}),
        images=ContractImages(),
        finalized_plans=ContractFinalizations(),
        implant_catalog=EmptyImplantCatalog(),
        clock=ContractClock(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/images/{IMAGE_ID}/plan/validate", json={"base_revision": 3})

    assert response.status_code == 200
    assert response.json()["status"] == "INCOMPLETE"
    assert any(issue["code"] == "IMAGE_NOT_ELIGIBLE" for issue in response.json()["blocking_errors"])


@pytest.mark.asyncio
async def test_plan_validation_reports_finalized_plan_as_blocking() -> None:
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_validate_image_plan] = lambda: ValidateImagePlan(
        plans=ContractPlans({}),
        images=ContractImages(),
        finalized_plans=ContractFinalizations(finalized=True),
        implant_catalog=EmptyImplantCatalog(),
        clock=ContractClock(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/images/{IMAGE_ID}/plan/validate", json={"base_revision": 3})

    assert response.status_code == 200
    assert response.json()["checks"]["finalization"] == "FAIL"
    assert any(issue["code"] == "PLAN_ALREADY_FINALIZED" for issue in response.json()["blocking_errors"])
