from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import ImageNotFoundError
from vetorthoplan.application.ports import Clock, FinalizedPlanRepository, ImagePlanRepository, ImageUploadRepository
from vetorthoplan.application.ports.implant_catalog_repository import ImplantCatalogRepository
from vetorthoplan.domain.imaging import ImageUploadStatus


@dataclass(frozen=True, slots=True)
class PlanValidationIssue:
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ImagePlanValidationView:
    image_id: UUID
    plan_revision: int
    status: str
    checks: dict[str, str]
    blocking_errors: list[PlanValidationIssue]
    warnings: list[PlanValidationIssue]
    validated_at: datetime


class ValidateImagePlan:
    """Run non-mutating structural and consistency checks on the saved plan."""

    _QUALITY_CRITERIA = (
        "true_lateral",
        "femoral_condyles_superimposed",
        "stifle_and_tarsus_included",
        "tibial_axis_centered",
        "tibial_plateau_visible",
    )
    _LANDMARKS = (
        "plateau_cranial",
        "plateau_caudal",
        "intercondylar_midpoint",
        "talus_center",
    )

    def __init__(
        self,
        *,
        plans: ImagePlanRepository,
        images: ImageUploadRepository,
        finalized_plans: FinalizedPlanRepository,
        implant_catalog: ImplantCatalogRepository,
        clock: Clock,
    ) -> None:
        self._plans = plans
        self._images = images
        self._finalized_plans = finalized_plans
        self._implant_catalog = implant_catalog
        self._clock = clock

    async def execute(
        self,
        image_id: UUID,
        context: TenantContext,
        *,
        base_revision: int | None = None,
    ) -> ImagePlanValidationView:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        plan = await self._plans.get(context.tenant_id, image_id)
        revision = plan.revision if plan is not None else 0
        document = plan.document if plan is not None else {}
        errors: list[PlanValidationIssue] = []
        warnings: list[PlanValidationIssue] = []
        checks = {key: "NOT_CHECKED" for key in (
            "image_status", "image_dimensions", "plan_revision", "calibration",
            "radiographic_quality", "anatomical_landmarks", "tpa", "osteotomy",
            "fragment", "rotation_table", "implant_references", "finalization",
            "clinical_homologation",
        )}

        def block(code: str, message: str, field: str | None = None) -> None:
            errors.append(PlanValidationIssue(code, message, field))

        def warn(code: str, message: str, field: str | None = None) -> None:
            warnings.append(PlanValidationIssue(code, message, field))

        if image.status == ImageUploadStatus.READY:
            checks["image_status"] = "PASS"
        else:
            checks["image_status"] = "FAIL"
            block("IMAGE_NOT_READY", "A radiografia ainda não está pronta para planejamento.", "image")

        has_dimensions = bool(image.width_px and image.height_px and image.width_px > 0 and image.height_px > 0)
        checks["image_dimensions"] = "PASS" if has_dimensions else "FAIL"
        if not has_dimensions:
            block("IMAGE_DIMENSIONS_REQUIRED", "As dimensões da imagem original não estão disponíveis.", "image")

        if plan is None:
            checks["plan_revision"] = "FAIL"
            block("PLAN_NOT_SAVED", "Salve um plano antes de solicitar a pré-validação.", "plan")
        elif base_revision is not None and base_revision != revision:
            checks["plan_revision"] = "FAIL"
            block("PLAN_REVISION_CONFLICT", "A revisão enviada não corresponde à revisão atual do plano.", "base_revision")
        else:
            checks["plan_revision"] = "PASS"

        calibration = document.get("calibration")
        calibration_result = calibration.get("result") if isinstance(calibration, dict) else None
        calibrated = (
            has_dimensions
            and isinstance(calibration_result, dict)
            and isinstance(calibration_result.get("calibration_id"), str)
            and isinstance(calibration_result.get("mm_per_pixel"), (int, float))
            and calibration_result["mm_per_pixel"] > 0
        )
        checks["calibration"] = "PASS" if calibrated else "FAIL"
        if not calibrated:
            block("CALIBRATION_REQUIRED", "A calibração da imagem precisa estar calculada.", "calibration")

        tplo = document.get("tplo") if isinstance(document.get("tplo"), dict) else None
        quality = document.get("radiographic_quality")
        quality_pass = (
            isinstance(quality, dict)
            and all(quality.get(criterion) == "PASS" for criterion in self._QUALITY_CRITERIA)
            and tplo is not None
            and tplo.get("eligibility") == "ELIGIBLE"
            and tplo.get("projection") == "MEDIOLATERAL"
        )
        checks["radiographic_quality"] = "PASS" if quality_pass else "FAIL"
        if not quality_pass:
            block(
                "RADIOGRAPHIC_QUALITY_INCOMPLETE",
                "A elegibilidade TPLO exige incidência mediolateral e todos os critérios de qualidade aprovados.",
                "radiographic_quality",
            )

        landmarks = document.get("tplo_landmarks")
        landmarks_present = isinstance(landmarks, dict) and all(
            isinstance(landmarks.get(name), dict) for name in self._LANDMARKS
        )
        checks["anatomical_landmarks"] = "PASS" if landmarks_present else "FAIL"
        if not landmarks_present:
            block("TPLO_LANDMARKS_REQUIRED", "Informe os quatro marcos anatômicos usados no cálculo do TPA.", "tplo_landmarks")

        tpa = document.get("tplo_measurement")
        tpa_calculated = isinstance(tpa, dict) and tpa.get("status") == "CALCULATED" and isinstance(tpa.get("tpa_degrees"), (int, float))
        checks["tpa"] = "PASS" if tpa_calculated else "FAIL"
        if not tpa_calculated:
            block("TPA_NOT_CALCULATED", "O TPA precisa estar calculado a partir dos marcos anatômicos.", "tplo_measurement")

        objects = document.get("objects")
        objects = objects if isinstance(objects, list) else []
        osteotomies = [item for item in objects if isinstance(item, dict) and item.get("type") == "TPLO"]
        checks["osteotomy"] = "PASS" if osteotomies else "FAIL"
        if not osteotomies:
            block("OSTEOTOMY_REQUIRED", "Defina ao menos uma geometria de osteotomia TPLO.", "objects")
        fragments_complete = bool(osteotomies) and all(
            isinstance(item.get("fragment"), dict)
            and isinstance(item["fragment"].get("points"), list)
            and len(item["fragment"]["points"]) >= 3
            and isinstance(item.get("simulation"), dict)
            and item["simulation"].get("status") == "SIMULATED"
            for item in osteotomies
        )
        checks["fragment"] = "PASS" if fragments_complete else "FAIL"
        if not fragments_complete:
            block("FRAGMENT_SIMULATION_REQUIRED", "Cada osteotomia precisa de contorno e simulação geométrica calculada.", "objects")

        correction = document.get("tplo_correction")
        has_blade = tplo is not None and isinstance(tplo.get("blade_diameter_mm"), (int, float))
        correction_pass = isinstance(correction, dict) and correction.get("status") == "CALCULATED" and correction.get("acceptance") == "PASS"
        if has_blade:
            checks["rotation_table"] = "PASS" if correction_pass else "FAIL"
            if not correction_pass:
                block("TPLO_CORRECTION_UNAVAILABLE", "A combinação de TPA e diâmetro da lâmina não possui correção tabelada aceita.", "tplo_correction")
        else:
            checks["rotation_table"] = "NOT_APPLICABLE"
            warn("BLADE_DIAMETER_NOT_SELECTED", "Nenhum diâmetro de lâmina foi selecionado; a correção tabelada não foi calculada.", "tplo.blade_diameter_mm")

        implant_objects = [item for item in objects if isinstance(item, dict) and item.get("type") == "IMPLANT"]
        item_ids = {item["catalog_item_id"] for item in implant_objects if isinstance(item.get("catalog_item_id"), UUID)}
        # Persisted JSON uses string UUIDs; parse only canonical UUID values.
        for item in implant_objects:
            try:
                item_ids.add(UUID(str(item.get("catalog_item_id"))))
            except (ValueError, TypeError, AttributeError):
                pass
        catalog_metadata = await self._implant_catalog.approved_metadata(context.tenant_id, item_ids)
        implants_valid = bool(implant_objects) == bool(catalog_metadata) and len(item_ids) == len(catalog_metadata)
        if implants_valid:
            for item in implant_objects:
                try:
                    item_id = UUID(str(item.get("catalog_item_id")))
                except (ValueError, TypeError, AttributeError):
                    implants_valid = False
                    break
                metadata = catalog_metadata.get(item_id)
                if metadata is None:
                    implants_valid = False
                    break
                if item.get("variant") is not None and item["variant"] not in metadata.get("variants", []):
                    implants_valid = False
                    break
                if item.get("view") is not None and item["view"] not in metadata.get("views", []):
                    implants_valid = False
                    break
        if implant_objects:
            checks["implant_references"] = "PASS" if implants_valid else "FAIL"
            if not implants_valid:
                block("IMPLANT_REFERENCE_INVALID", "Há implante não aprovado, de outro tenant, ou com variante/vista inválida.", "objects")
        else:
            checks["implant_references"] = "NOT_APPLICABLE"

        finalized = await self._finalized_plans.latest(context.tenant_id, image_id)
        checks["finalization"] = "FAIL" if finalized is not None else "PASS"
        if finalized is not None:
            block("PLAN_ALREADY_FINALIZED", "O plano já foi finalizado e não aceita uma nova pré-validação para edição.", "finalization")

        checks["clinical_homologation"] = "PENDING"
        warn(
            "CLINICAL_VALIDATION_PENDING",
            "Os critérios e cálculos ainda precisam de homologação pelo médico veterinário.",
            "clinical_homologation",
        )
        return ImagePlanValidationView(
            image_id=image_id,
            plan_revision=revision,
            status="READY_FOR_CLINICAL_REVIEW" if not errors else "INCOMPLETE",
            checks=checks,
            blocking_errors=errors,
            warnings=warnings,
            validated_at=self._clock.now(),
        )
