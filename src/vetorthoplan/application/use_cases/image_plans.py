from copy import deepcopy
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
from vetorthoplan.application.ports.tplo_rotation_table_repository import TploRotationTableRepository
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.planning import ImagePlan
from vetorthoplan.domain.planning.clinical_protocol import TploClinicalProtocol
from vetorthoplan.domain.planning.measurements import derive_plan_measurements
from vetorthoplan.domain.planning.rotation_table import TploRotationTable


@dataclass(frozen=True, slots=True)
class ImagePlanView:
    image_id: UUID
    revision: int
    document: dict[str, object]
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReviewImagePlanCommand:
    status: str
    orientation_confirmed: bool | None = None
    image_quality_confirmed: bool | None = None
    calibration_confirmed: bool | None = None
    anatomical_references_confirmed: bool | None = None
    required_measurements: list[str] | None = None
    reviewer_notes: str | None = None
    rejection_reason: str | None = None


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
        rotation_table: TploRotationTable | None = None,
        rotation_table_repository: TploRotationTableRepository | None = None,
        finalized_plans: FinalizedPlanRepository | None = None,
    ) -> None:
        self._plans = plans
        self._images = images
        self._id_generator = id_generator
        self._clock = clock
        self._clinical_protocol = clinical_protocol
        self._rotation_table = rotation_table
        self._rotation_table_repository = rotation_table_repository
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
        rotation_table = self._rotation_table
        if rotation_table is None and self._rotation_table_repository is not None:
            rotation_table = await self._rotation_table_repository.get_active()
        document = derive_plan_measurements(
            document,
            width_px=image.width_px,
            height_px=image.height_px,
            clinical_protocol=self._clinical_protocol,
            rotation_table=rotation_table,
        )
        current = await self._plans.get(context.tenant_id, image_id)
        _validate_locked_plan_objects(
            current.document if current is not None else None,
            document,
        )
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
            rotation_table_version=rotation_table.version if rotation_table is not None else None,
            clinical_protocol_source=(
                self._clinical_protocol.source if self._clinical_protocol is not None else None
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


def _validate_locked_plan_objects(
    previous_document: dict[str, object] | None,
    document: dict[str, object],
) -> None:
    """Prevent geometry edits or deletion while an object is locked.

    Unlocking is an explicit save that only changes the lock state (visibility may
    also change); a later revision can then edit or remove the object.
    """
    if previous_document is None:
        return
    previous_objects = previous_document.get("objects", [])
    next_objects = document.get("objects", [])
    if not isinstance(previous_objects, list) or not isinstance(next_objects, list):
        return
    next_by_id = {
        str(item.get("id")): item
        for item in next_objects
        if isinstance(item, dict) and item.get("id") is not None
    }
    derived_fields = {"measurement", "simulation", "transform"}
    mutable_lock_fields = {"locked", "visible"}
    for previous in previous_objects:
        if not isinstance(previous, dict) or not previous.get("locked", False):
            continue
        object_id = str(previous.get("id"))
        current = next_by_id.get(object_id)
        if current is None:
            raise ClinicalValidationError(f"O objeto bloqueado {object_id} não pode ser removido")
        previous_geometry = {
            key: value for key, value in previous.items()
            if key not in derived_fields | mutable_lock_fields
        }
        current_geometry = {
            key: value for key, value in current.items()
            if key not in derived_fields | mutable_lock_fields
        }
        if previous_geometry != current_geometry:
            raise ClinicalValidationError(f"O objeto bloqueado {object_id} não pode ser editado")


class ReviewImagePlan:
    """Apply a clinical review decision to the persisted plan candidate.

    The review endpoint deliberately loads the current document and only changes
    decision metadata. The geometry, derived measurements and correction therefore
    remain the exact candidate that was submitted with ``READY_FOR_REVIEW``.
    """

    def __init__(
        self,
        *,
        plans: ImagePlanRepository,
        images: ImageUploadRepository,
        saver: SaveImagePlan,
    ) -> None:
        self._plans = plans
        self._images = images
        self._saver = saver

    async def execute(
        self,
        image_id: UUID,
        base_revision: int,
        command: ReviewImagePlanCommand,
        context: TenantContext,
    ) -> ImagePlanView:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)
        current = await self._plans.get(context.tenant_id, image_id)
        if current is None:
            raise ClinicalValidationError("Crie o plano antes de iniciar a revisão clínica")
        document = deepcopy(current.document)
        validation = document.get("clinical_validation")
        if not isinstance(validation, dict):
            validation = {}
        validation["status"] = command.status
        for field in (
            "orientation_confirmed",
            "image_quality_confirmed",
            "calibration_confirmed",
            "anatomical_references_confirmed",
            "required_measurements",
            "reviewer_notes",
            "rejection_reason",
        ):
            value = getattr(command, field)
            if value is not None:
                validation[field] = value
        document["clinical_validation"] = validation
        return await self._saver.execute(image_id, base_revision, document, context)


def _record_clinical_review(
    document: dict[str, object],
    *,
    previous_document: dict[str, object] | None,
    actor_id: UUID,
    reviewed_at: datetime,
    protocol_version: str,
    rotation_table_version: str | None = None,
    clinical_protocol_source: str | None = None,
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
            "rotation_table_version": rotation_table_version,
            "clinical_protocol_source": clinical_protocol_source,
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
    if not isinstance(validation, dict):
        return
    status = validation.get("status")
    previous_validation = (
        previous_document.get("clinical_validation") if previous_document is not None else None
    )
    previous_status = previous_validation.get("status") if isinstance(previous_validation, dict) else None
    if status in {"APPROVED", "REJECTED"} and status != previous_status:
        if previous_status != "READY_FOR_REVIEW":
            raise ClinicalValidationError(
                "O plano precisa estar em READY_FOR_REVIEW antes da decisão clínica"
            )
        candidate_changed = (
            previous_document is None
            or _review_candidate(document) != _review_candidate(previous_document)
        )
        if candidate_changed:
            raise ClinicalValidationError(
                "A decisão deve revisar a mesma versão enviada em READY_FOR_REVIEW; "
                "alterações exigem nova revisão"
            )
    if status == "READY_FOR_REVIEW":
        if (
            previous_status == "READY_FOR_REVIEW"
            and previous_document is not None
            and _review_candidate(document) != _review_candidate(previous_document)
        ):
            raise ClinicalValidationError(
                "O plano mudou durante a revisão; retorne a DRAFT e submeta a nova versão"
            )
        if not isinstance(tplo, dict) or tplo.get("eligibility") != "ELIGIBLE":
            raise ClinicalValidationError("A imagem TPLO precisa estar elegível para revisão clínica")
        if not isinstance(document.get("calibration"), dict) or not isinstance(
            document["calibration"].get("result"), dict
        ):
            raise ClinicalValidationError("A calibração manual precisa estar calculada para revisão")
        measurement = document.get("tplo_measurement")
        if not isinstance(measurement, dict) or measurement.get("status") != "CALCULATED":
            raise ClinicalValidationError("O TPA precisa estar calculado para revisão clínica")
        return
    if status != "APPROVED":
        return
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
    if "TPA" not in required:
        raise ClinicalValidationError("TPA precisa constar entre as medidas obrigatórias da aprovação")
    if isinstance(tplo.get("blade_diameter_mm"), (int, float)) and "TPLO_CORRECTION" not in required:
        raise ClinicalValidationError(
            "TPLO_CORRECTION precisa constar entre as medidas obrigatórias quando houver lâmina selecionada"
        )
    measurement = document.get("tplo_measurement")
    if not isinstance(measurement, dict):
        raise ClinicalValidationError("As medidas anatômicas ainda não foram calculadas")
    available = {
        "TPA": measurement.get("tpa_degrees") is not None
        and measurement.get("acceptance") == "PASS",
        "PLATEAU_AXIS": measurement.get("plateau_length_mm") is not None,
        "TIBIAL_AXIS": measurement.get("tibial_axis_length_mm") is not None,
    }
    correction = document.get("tplo_correction")
    available["TPLO_CORRECTION"] = (
        isinstance(correction, dict)
        and correction.get("status") == "CALCULATED"
        and correction.get("acceptance") == "PASS"
    )
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


def _review_candidate(document: dict[str, object]) -> dict[str, object]:
    """Return the reviewed plan payload without decision-only fields and server audit."""
    candidate = {key: value for key, value in document.items() if key != "clinical_validation"}
    validation = document.get("clinical_validation")
    if isinstance(validation, dict):
        candidate["clinical_validation"] = {
            key: value
            for key, value in validation.items()
            if key not in {"status", "reviewer_notes", "rejection_reason", "audit"}
        }
    return candidate
