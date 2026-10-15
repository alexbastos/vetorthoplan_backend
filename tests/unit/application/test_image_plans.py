from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import PlanRevisionConflictError
from vetorthoplan.application.use_cases import SaveImagePlan
from vetorthoplan.domain.imaging import ImageUpload
from vetorthoplan.domain.planning import ImagePlan

NOW = datetime(2026, 9, 18, 20, 0, tzinfo=UTC)
TENANT_ID = UUID("00000000-0000-4000-8000-000000000701")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000702")
CASE_ID = UUID("00000000-0000-4000-8000-000000000703")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000704")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000705")
PLAN_ID = UUID("00000000-0000-4000-8000-000000000706")
DOCUMENT = {"schema_version": 1, "calibration": None, "objects": []}


def ready_image() -> ImageUpload:
    image = ImageUpload.create(
        upload_id=UPLOAD_ID,
        image_id=IMAGE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        actor_id=ACTOR_ID,
        original_filename="image.png",
        media_type="image/png",
        size_bytes=10,
        sha256="a" * 64,
        object_key="quarantine/test/image.png",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return image.confirm(completed_at=NOW).start_processing().mark_ready(
        detected_media_type="image/png",
        width_px=10,
        height_px=10,
        metadata={},
        preview_object_key="derived/test/preview.png",
        preview_media_type="image/png",
        preview_width_px=10,
        preview_height_px=10,
        processed_at=NOW,
    )


class Images:
    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID):
        return ready_image() if tenant_id == TENANT_ID and image_id == IMAGE_ID else None


class Plans:
    def __init__(self) -> None:
        self.plan: ImagePlan | None = None

    async def get(self, tenant_id: UUID, image_id: UUID):
        return self.plan if tenant_id == TENANT_ID and image_id == IMAGE_ID else None

    async def add(self, plan: ImagePlan):
        self.plan = plan
        return plan

    async def save(self, plan: ImagePlan, expected_revision: int):
        if not self.plan or self.plan.revision != expected_revision:
            return None
        self.plan = plan
        return plan


class IdGenerator:
    def new(self) -> UUID:
        return PLAN_ID


class Clock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_plan_is_created_and_revised_with_optimistic_revision() -> None:
    plans = Plans()
    use_case = SaveImagePlan(plans=plans, images=Images(), id_generator=IdGenerator(), clock=Clock())
    context = TenantContext(TENANT_ID, ACTOR_ID)

    created = await use_case.execute(IMAGE_ID, 0, DOCUMENT, context)
    revised = await use_case.execute(IMAGE_ID, 1, {**DOCUMENT, "objects": [{"type": "LINE"}]}, context)

    assert created.revision == 1
    assert revised.revision == 2


@pytest.mark.asyncio
async def test_plan_rejects_stale_revision() -> None:
    plans = Plans()
    use_case = SaveImagePlan(plans=plans, images=Images(), id_generator=IdGenerator(), clock=Clock())
    context = TenantContext(TENANT_ID, ACTOR_ID)
    await use_case.execute(IMAGE_ID, 0, DOCUMENT, context)

    with pytest.raises(PlanRevisionConflictError) as error:
        await use_case.execute(IMAGE_ID, 0, DOCUMENT, context)

    assert error.value.current_revision == 1
