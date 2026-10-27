from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ClinicalValidationError,
    ImageNotReadyError,
    PlanRevisionConflictError,
)
from vetorthoplan.application.use_cases import GetImagePlan, SaveImagePlan
from vetorthoplan.application.use_cases.image_plans import _validate_clinical_review
from vetorthoplan.domain.imaging import ImageUpload
from vetorthoplan.domain.planning import ImagePlan

NOW = datetime(2026, 9, 18, 20, 0, tzinfo=UTC)
TENANT_ID = UUID("00000000-0000-4000-8000-000000000701")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000702")
CASE_ID = UUID("00000000-0000-4000-8000-000000000703")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000704")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000705")
PLAN_ID = UUID("00000000-0000-4000-8000-000000000706")
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
    def __init__(self, image: ImageUpload | None = None) -> None:
        self.image = image or ready_image()

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID):
        return self.image if tenant_id == TENANT_ID and image_id == IMAGE_ID else None


class Plans:
    def __init__(self) -> None:
        self.plan: ImagePlan | None = None

    async def get(self, tenant_id: UUID, image_id: UUID):
        return self.plan if tenant_id == TENANT_ID and image_id == IMAGE_ID else None

    async def add(self, plan: ImagePlan):
        if self.plan is not None:
            return None
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


@pytest.mark.asyncio
async def test_get_plan_returns_empty_document_before_first_save() -> None:
    use_case = GetImagePlan(plans=Plans(), images=Images())

    result = await use_case.execute(IMAGE_ID, TenantContext(TENANT_ID, ACTOR_ID))

    assert result.revision == 0
    assert result.document == DOCUMENT
    assert result.updated_at is None


@pytest.mark.asyncio
async def test_get_plan_requires_image_to_be_ready() -> None:
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
    use_case = GetImagePlan(plans=Plans(), images=Images(image))

    with pytest.raises(ImageNotReadyError):
        await use_case.execute(IMAGE_ID, TenantContext(TENANT_ID, ACTOR_ID))


@pytest.mark.asyncio
async def test_concurrent_first_save_returns_revision_conflict() -> None:
    # Simulate another request winning the INSERT after this request's initial read.
    competing_plan = ImagePlan.create(
        plan_id=PLAN_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        image_id=IMAGE_ID,
        document=DOCUMENT,
        actor_id=ACTOR_ID,
        now=NOW,
    )

    class ConcurrentPlans(Plans):
        async def add(self, plan: ImagePlan):
            self.plan = competing_plan
            return None

    plans = ConcurrentPlans()
    use_case = SaveImagePlan(plans=plans, images=Images(), id_generator=IdGenerator(), clock=Clock())

    with pytest.raises(PlanRevisionConflictError) as error:
        await use_case.execute(IMAGE_ID, 0, DOCUMENT, TenantContext(TENANT_ID, ACTOR_ID))

    assert error.value.current_revision == 1


def test_clinical_approval_requires_ready_for_review_transition() -> None:
    document = {"clinical_validation": {"status": "APPROVED"}}

    with pytest.raises(ClinicalValidationError, match="READY_FOR_REVIEW"):
        _validate_clinical_review(document, previous_document=None)


def test_clinical_approval_cannot_accept_unconfigured_tpa() -> None:
    document = {
        "tplo": {"eligibility": "ELIGIBLE"},
        "calibration": {"result": {}},
        "radiographic_quality": {
            "true_lateral": "PASS",
            "femoral_condyles_superimposed": "PASS",
            "stifle_and_tarsus_included": "PASS",
            "tibial_axis_centered": "PASS",
            "tibial_plateau_visible": "PASS",
        },
        "clinical_validation": {"status": "APPROVED", "required_measurements": ["TPA"]},
        "tplo_measurement": {"tpa_degrees": 24.0, "acceptance": "NOT_CONFIGURED"},
    }
    previous_document = {"clinical_validation": {"status": "READY_FOR_REVIEW"}}

    with pytest.raises(ClinicalValidationError, match="TPA"):
        _validate_clinical_review(document, previous_document=previous_document)
