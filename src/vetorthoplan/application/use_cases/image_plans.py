from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ClinicalValidationError,
    ImageNotFoundError,
    ImageNotReadyError,
    PlanRevisionConflictError,
)
from vetorthoplan.application.ports import (
    Clock,
    IdGenerator,
    ImagePlanRepository,
    ImageUploadRepository,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.planning import ImagePlan
from vetorthoplan.domain.planning.measurements import derive_plan_measurements


@dataclass(frozen=True, slots=True)
class ImagePlanView:
    image_id: UUID
    revision: int
    document: dict[str, object]
    updated_at: datetime | None


class GetImagePlan:
    def __init__(self, plans: ImagePlanRepository, images: ImageUploadRepository) -> None:
        self._plans = plans
        self._images = images

    async def execute(self, image_id: UUID, context: TenantContext) -> ImagePlanView:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)
        plan = await self._plans.get(context.tenant_id, image_id)
        if plan is None:
            return ImagePlanView(
                image_id=image_id,
                revision=0,
                document={
                    "schema_version": 1,
                    "calibration": None,
                    "tplo": None,
                    "clinical_validation": None,
                    "objects": [],
                },
                updated_at=None,
            )
        return ImagePlanView(image_id, plan.revision, plan.document, plan.updated_at)


class SaveImagePlan:
    def __init__(
        self,
        *,
        plans: ImagePlanRepository,
        images: ImageUploadRepository,
        id_generator: IdGenerator,
        clock: Clock,
    ) -> None:
        self._plans = plans
        self._images = images
        self._id_generator = id_generator
        self._clock = clock

    async def execute(
        self,
        image_id: UUID,
        base_revision: int,
        document: dict[str, object],
        context: TenantContext,
    ) -> ImagePlanView:
        lock_case = getattr(self._images, "lock_case_for_image", None)
        if lock_case is not None and not await lock_case(context.tenant_id, image_id):
            raise ImageNotFoundError(image_id)
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)
        document = derive_plan_measurements(
            document,
            width_px=image.width_px,
            height_px=image.height_px,
        )
        _validate_clinical_review(document)
        current = await self._plans.get(context.tenant_id, image_id)
        if current is None:
            if base_revision != 0:
                raise PlanRevisionConflictError(0)
            saved = await self._plans.add(
                ImagePlan.create(
                    plan_id=self._id_generator.new(),
                    tenant_id=context.tenant_id,
                    case_id=image.case_id,
                    image_id=image.image_id,
                    document=document,
                    actor_id=context.actor_id,
                    now=self._clock.now(),
                )
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        else:
            if current.revision != base_revision:
                raise PlanRevisionConflictError(current.revision)
            saved = await self._plans.save(
                current.revise(document, self._clock.now()),
                expected_revision=base_revision,
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        return ImagePlanView(saved.image_id, saved.revision, saved.document, saved.updated_at)


def _validate_clinical_review(document: dict[str, object]) -> None:
    validation = document.get("clinical_validation")
    if not isinstance(validation, dict) or validation.get("status") != "APPROVED":
        return
    tplo = document.get("tplo")
    calibration = document.get("calibration")
    if not isinstance(tplo, dict) or tplo.get("eligibility") != "ELIGIBLE":
        raise ClinicalValidationError("A imagem TPLO precisa estar elegível antes da aprovação clínica")
    if not isinstance(calibration, dict) or not isinstance(calibration.get("result"), dict):
        raise ClinicalValidationError(
            "A calibração manual precisa estar calculada antes da aprovação clínica"
        )
    required = validation.get("required_measurements")
    if not isinstance(required, list) or not required:
        raise ClinicalValidationError("Informe ao menos uma medida clínica antes da aprovação")
    measurement = document.get("tplo_measurement")
    if not isinstance(measurement, dict):
        raise ClinicalValidationError("As medidas anatômicas ainda não foram calculadas")
    available = {
        "TPA": measurement.get("tpa_degrees") is not None,
        "PLATEAU_AXIS": measurement.get("plateau_length_mm") is not None,
        "TIBIAL_AXIS": measurement.get("tibial_axis_length_mm") is not None,
    }
    missing = [name for name in required if not available.get(name, False)]
    if missing:
        raise ClinicalValidationError(
            "As medidas obrigatórias precisam estar identificadas no plano: " + ", ".join(missing)
        )
