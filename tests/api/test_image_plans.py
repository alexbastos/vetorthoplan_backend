from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import get_image_plan, get_save_image_plan, get_tenant_context
from vetorthoplan.api.schemas import PlanDocument
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import GetImagePlan, SaveImagePlan
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.imaging import ImageUpload
from vetorthoplan.domain.planning import ImagePlan

TENANT_ID = UUID("00000000-0000-4000-8000-000000000801")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000802")
CASE_ID = UUID("00000000-0000-4000-8000-000000000803")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000804")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000805")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
DOCUMENT = {
    "schema_version": 1,
    "calibration": None,
    "tplo": None,
    "tplo_landmarks": None,
    "tplo_measurement": None,
    "radiographic_quality": None,
    "additional_measurements_input": {"landmarks": {}, "reference_values": {}},
    "additional_measurements": [],
    "clinical_validation": None,
    "objects": [],
}


def ready_image() -> ImageUpload:
    image = ImageUpload.create(
        upload_id=UPLOAD_ID,
        image_id=IMAGE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        actor_id=ACTOR_ID,
        original_filename="radiografia.png",
        media_type="image/png",
        size_bytes=32,
        sha256="a" * 64,
        object_key="quarantine/test/radiografia.png",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return image.confirm(completed_at=NOW).start_processing().mark_ready(
        detected_media_type="image/png",
        width_px=640,
        height_px=480,
        metadata={},
        preview_object_key="derived/test/preview.png",
        preview_media_type="image/png",
        preview_width_px=640,
        preview_height_px=480,
        processed_at=NOW,
    )


class Images:
    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID):
        return ready_image() if (tenant_id, image_id) == (TENANT_ID, IMAGE_ID) else None


class Plans:
    def __init__(self) -> None:
        self.plan: ImagePlan | None = None

    async def get(self, tenant_id: UUID, image_id: UUID):
        if (tenant_id, image_id) != (TENANT_ID, IMAGE_ID):
            return None
        return self.plan

    async def add(self, plan: ImagePlan):
        self.plan = plan
        return plan

    async def save(self, plan: ImagePlan, expected_revision: int):
        if self.plan is None or self.plan.revision != expected_revision:
            return None
        self.plan = plan
        return plan


class IdGenerator:
    def new(self) -> UUID:
        return UUID("00000000-0000-4000-8000-000000000806")


class Clock:
    def now(self) -> datetime:
        return NOW


def build_app():
    app = create_app()
    plans = Plans()
    images = Images()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_image_plan] = lambda: GetImagePlan(plans=plans, images=images)
    app.dependency_overrides[get_save_image_plan] = lambda: SaveImagePlan(
        plans=plans,
        images=images,
        id_generator=IdGenerator(),
        clock=Clock(),
    )
    return app


@pytest.mark.asyncio
async def test_image_plan_get_put_and_revision_conflict() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        initial = await client.get(f"/api/v1/images/{IMAGE_ID}/plan")
        saved = await client.put(
            f"/api/v1/images/{IMAGE_ID}/plan",
            json={"base_revision": 0, "document": DOCUMENT},
        )
        fetched = await client.get(f"/api/v1/images/{IMAGE_ID}/plan")
        stale = await client.put(
            f"/api/v1/images/{IMAGE_ID}/plan",
            json={"base_revision": 0, "document": DOCUMENT},
        )

    assert initial.status_code == 200
    assert initial.json()["revision"] == 0
    assert initial.json()["document"] == DOCUMENT
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    assert fetched.json()["revision"] == 1
    assert stale.status_code == 409
    assert stale.json()["code"] == "PLAN_REVISION_CONFLICT"


def test_openapi_documents_get_and_put_plan_contracts() -> None:
    paths = create_app().openapi()["paths"]
    plan_path = paths["/api/v1/images/{image_id}/plan"]

    assert "200" in plan_path["get"]["responses"]
    assert "200" in plan_path["put"]["responses"]
    assert "409" in plan_path["put"]["responses"]


def test_plan_calibration_accepts_reference_circle_and_rejects_missing_diameter() -> None:
    document = PlanDocument.model_validate(
        {
            "schema_version": 1,
            "calibration": {
                "kind": "REFERENCE_CIRCLE",
                "center": {"x": 0.5, "y": 0.5},
                "edge": {"x": 0.6, "y": 0.5},
                "known_diameter_mm": 25,
            },
            "objects": [],
        }
    )
    assert document.calibration.kind == "REFERENCE_CIRCLE"

    with pytest.raises(ValueError):
        PlanDocument.model_validate(
            {
                "schema_version": 1,
                "calibration": {
                    "kind": "REFERENCE_CIRCLE",
                    "center": {"x": 0.5, "y": 0.5},
                    "edge": {"x": 0.6, "y": 0.5},
                },
                "objects": [],
            }
        )
