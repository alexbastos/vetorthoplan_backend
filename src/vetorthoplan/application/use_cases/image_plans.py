from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ClinicalValidationError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImagePlanFinalizedError,
    PlanRevisionConflictError,
)
from vetorthoplan.application.ports import (
    Clock,
    FinalizedPlanRepository,
    IdGenerator,
    ImagePlanRepository,
    ImageUploadRepository,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.planning import ImagePlan
from vetorthoplan.domain.planning.clinical_protocol import TploClinicalProtocol
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
                    "tplo_landmarks": None,
                    "tplo_measurement": None,
                    "radiographic_quality": None,
                    "additional_measurements_input": {"landmarks": {}, "reference_values": {}},
                    "additional_measurements": [],
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
        clinical_protocol: TploClinicalProtocol | None = None,
        finalized_plans: FinalizedPlanRepository | None = None,
    ) -> None:
        self._plans = plans
        self._images = images
        self._id_generator = id_generator
        self._clock = clock
        self._clinical_protocol = clinical_protocol
        self._finalized_plans = finalized_plans

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
        if self._finalized_plans is not None:
            finalized = await self._finalized_plans.latest(context.tenant_id, image_id)
            if finalized is not None:
                raise ImagePlanFinalizedError(image_id, finalized.version)
        document = derive_plan_measurements(
            document,
            width_px=image.width_px,
            height_px=image.height_px,
            clinical_protocol=self._clinical_protocol,
        )
        current = await self._plans.get(context.tenant_id, image_id)
        now = self._clock.now()
        document = _record_clinical_review(
            document,
            previous_document=current.document if current is not None else None,
            actor_id=context.actor_id,
            reviewed_at=now,
            protocol_version=(
                self._clinical_protocol.version
                if self._clinical_protocol is not None
                else "TPLO_CLINICAL_REVIEW_V1"
            ),
        )
        _validate_clinical_review(
            document,
            previous_document=current.document if current is not None else None,
        )
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
                    now=now,
                )
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        else:
            if current.revision != base_revision:
                raise PlanRevisionConflictError(current.revision)
            saved = await self._plans.save(
                current.revise(document, now),
                expected_revision=base_revision,
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        return ImagePlanView(saved.image_id, saved.revision, saved.document, saved.updated_at)


def _record_clinical_review(
    document: dict[str, object],
    *,
    previous_document: dict[str, object] | None,
    actor_id: UUID,
    reviewed_at: datetime,
    protocol_version: str,
) -> dict[str, object]:
    """Build review audit on the server; client supplied audit entries are discarded."""
    validation = document.get("clinical_validation")
    if not isinstance(validation, dict):
        return document

    previous_validation = (
        previous_document.get("clinical_validation") if previous_document is not None else None
    )
    previous_status = previous_validation.get("status") if isinstance(previous_validation, dict) else None
    status = validation.get("status")
    old_audit = previous_validation.get("audit", []) if isinstance(previous_validation, dict) else []
    audit = list(old_audit) if isinstance(old_audit, list) else []
    validation["audit"] = audit

    if status not in {"APPROVED", "REJECTED"} or status == previous_status:
        return document

    measurement = document.get("tplo_measurement")
    calibration = document.get("calibration")
    calibration_result = calibration.get("result") if isinstance(calibration, dict) else None
    validation["audit"].append(
        {
            "decision": status,
            "actor_id": str(actor_id),
            "reviewed_at": reviewed_at.isoformat(),
            "protocol_version": protocol_version,
            "measurement_method": measurement.get("method") if isinstance(measurement, dict) else None,
            "calibration_id": (
                calibration_result.get("calibration_id") if isinstance(calibration_result, dict) else None
            ),
        }
    )
    return document


def _validate_clinical_review(
    document: dict[str, object], *, previous_document: dict[str, object] | None = None
) -> None:
    tplo = document.get("tplo")
    if isinstance(tplo, dict) and tplo.get("eligibility") == "ELIGIBLE":
        quality = document.get("radiographic_quality")
        criteria = (
            "true_lateral",
            "femoral_condyles_superimposed",
            "stifle_and_tarsus_included",
            "tibial_axis_centered",
            "tibial_plateau_visible",
        )
        if not isinstance(quality, dict) or any(quality.get(name) != "PASS" for name in criteria):
            raise ClinicalValidationError(
                "Imagem TPLO elegível requer todos os critérios de qualidade radiográfica aprovados"
            )
    validation = document.get("clinical_validation")
    if not isinstance(validation, dict) or validation.get("status") != "APPROVED":
        return
    previous_validation = (
        previous_document.get("clinical_validation") if previous_document is not None else None
    )
    previous_status = previous_validation.get("status") if isinstance(previous_validation, dict) else None
    if previous_status not in {"READY_FOR_REVIEW", "APPROVED"}:
        raise ClinicalValidationError(
            "O plano precisa estar em READY_FOR_REVIEW antes da aprovação clínica"
        )
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
        "TPA": measurement.get("tpa_degrees") is not None
        and measurement.get("acceptance") == "PASS",
        "PLATEAU_AXIS": measurement.get("plateau_length_mm") is not None,
        "TIBIAL_AXIS": measurement.get("tibial_axis_length_mm") is not None,
    }
    additional = document.get("additional_measurements")
    if isinstance(additional, list):
        available.update(
            {
                item.get("id"): item.get("acceptance") == "PASS"
                for item in additional
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        )
    missing = [name for name in required if not available.get(name, False)]
    if missing:
        raise ClinicalValidationError(
            "As medidas obrigatórias precisam estar identificadas no plano: " + ", ".join(missing)
        )
