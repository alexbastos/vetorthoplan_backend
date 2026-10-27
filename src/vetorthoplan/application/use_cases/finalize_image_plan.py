from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ClinicalValidationError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImagePlanFinalizationNotFoundError,
    PlanRevisionConflictError,
)
from vetorthoplan.application.ports import (
    Clock,
    FinalizedPlanRepository,
    IdGenerator,
    ImagePlanRepository,
    ImageUploadRepository,
    PlanReportRenderer,
    UploadStorage,
)
from vetorthoplan.application.ports.plan_report_renderer import (
    REPORT_TEMPLATE_VERSION,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.planning.finalized_plan import FinalizedPlan


@dataclass(frozen=True, slots=True)
class FinalizedReportLink:
    format: str
    sha256: str
    download_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class FinalizedPlanView:
    image_id: UUID
    version: int
    plan_revision: int
    snapshot: dict[str, object]
    snapshot_sha256: str
    report_template_version: str
    finalized_by: UUID
    finalized_at: datetime
    reports: tuple[FinalizedReportLink, ...]


class FinalizeImagePlan:
    def __init__(
        self,
        *,
        plans: ImagePlanRepository,
        finalized_plans: FinalizedPlanRepository,
        images: ImageUploadRepository,
        storage: UploadStorage,
        id_generator: IdGenerator,
        clock: Clock,
        renderer: PlanReportRenderer,
        report_url_expires_seconds: int,
    ) -> None:
        self._plans = plans
        self._finalized_plans = finalized_plans
        self._images = images
        self._storage = storage
        self._id_generator = id_generator
        self._clock = clock
        self._renderer = renderer
        self._report_url_expires_seconds = report_url_expires_seconds

    async def execute(
        self,
        image_id: UUID,
        base_revision: int,
        context: TenantContext,
    ) -> FinalizedPlanView:
        lock_case = getattr(self._images, "lock_case_for_image", None)
        if lock_case is not None and not await lock_case(context.tenant_id, image_id):
            raise ImageNotFoundError(image_id)
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)

        existing = await self._finalized_plans.latest(context.tenant_id, image_id)
        if existing is not None:
            if existing.plan_revision != base_revision:
                raise PlanRevisionConflictError(existing.plan_revision)
            return self._view(existing)

        plan = await self._plans.get(context.tenant_id, image_id)
        if plan is None:
            raise ClinicalValidationError("Crie e complete o plano antes de finalizá-lo")
        if plan.revision != base_revision:
            raise PlanRevisionConflictError(plan.revision)
        _validate_finalization(plan.document)
        if not image.preview_object_key:
            raise ImageNotReadyError(image_id)

        now = self._clock.now()
        snapshot = json.loads(
            json.dumps(plan.document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        snapshot_bytes = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        finalization_id = self._id_generator.new()
        version = 1
        prefix = (
            f"derived/{context.tenant_id}/{image.case_id}/{image_id}"
            f"/finalizations/v{version}/{finalization_id}"
        )
        png_key, pdf_key = f"{prefix}/report.png", f"{prefix}/report.pdf"

        preview = await self._storage.read_object(image.preview_object_key)
        reports = self._renderer.render(
            preview_png=preview,
            snapshot=snapshot,
            case_id=image.case_id,
            image_id=image_id,
            plan_revision=plan.revision,
            finalization_version=version,
            finalized_by=context.actor_id,
            finalized_at=now.isoformat(),
        )
        png_sha256 = hashlib.sha256(reports.png).hexdigest()
        pdf_sha256 = hashlib.sha256(reports.pdf).hexdigest()
        stored_keys: list[str] = []
        try:
            await self._storage.store_object(
                png_key,
                reports.png,
                "image/png",
                metadata={"finalization-id": str(finalization_id), "sha256": png_sha256},
            )
            stored_keys.append(png_key)
            await self._storage.store_object(
                pdf_key,
                reports.pdf,
                "application/pdf",
                metadata={"finalization-id": str(finalization_id), "sha256": pdf_sha256},
            )
            stored_keys.append(pdf_key)

            finalized = FinalizedPlan(
                id=finalization_id,
                tenant_id=context.tenant_id,
                case_id=image.case_id,
                image_id=image_id,
                version=version,
                plan_revision=plan.revision,
                snapshot=snapshot,
                snapshot_sha256=snapshot_sha256,
                report_template_version=REPORT_TEMPLATE_VERSION,
                report_png_key=png_key,
                report_png_sha256=png_sha256,
                report_pdf_key=pdf_key,
                report_pdf_sha256=pdf_sha256,
                finalized_by=context.actor_id,
                finalized_at=now,
            )
            added = await self._finalized_plans.add(finalized)
            if not added:
                await self._delete_objects(stored_keys)
                latest = await self._finalized_plans.latest(context.tenant_id, image_id)
                if latest is None:
                    raise PlanRevisionConflictError(plan.revision)
                return self._view(latest)
            return self._view(finalized)
        except Exception:
            await self._delete_objects(stored_keys)
            raise

    async def _delete_objects(self, keys: list[str]) -> None:
        for key in keys:
            try:
                await self._storage.delete_object(key)
            except Exception:
                # The deterministic ownership prefix allows later storage cleanup.
                continue

    def _view(self, finalized: FinalizedPlan) -> FinalizedPlanView:
        now = self._clock.now()
        png = self._storage.create_presigned_get(
            finalized.report_png_key,
            now,
            expires_in_seconds=self._report_url_expires_seconds,
        )
        pdf = self._storage.create_presigned_get(
            finalized.report_pdf_key,
            now,
            expires_in_seconds=self._report_url_expires_seconds,
        )
        return FinalizedPlanView(
            image_id=finalized.image_id,
            version=finalized.version,
            plan_revision=finalized.plan_revision,
            snapshot=finalized.snapshot,
            snapshot_sha256=finalized.snapshot_sha256,
            report_template_version=finalized.report_template_version,
            finalized_by=finalized.finalized_by,
            finalized_at=finalized.finalized_at,
            reports=(
                FinalizedReportLink("PNG", finalized.report_png_sha256, png.url, png.expires_at),
                FinalizedReportLink("PDF", finalized.report_pdf_sha256, pdf.url, pdf.expires_at),
            ),
        )


class GetFinalizedImagePlan:
    def __init__(
        self,
        *,
        finalized_plans: FinalizedPlanRepository,
        images: ImageUploadRepository,
        storage: UploadStorage,
        clock: Clock,
        report_url_expires_seconds: int,
    ) -> None:
        self._finalized_plans = finalized_plans
        self._images = images
        self._storage = storage
        self._clock = clock
        self._report_url_expires_seconds = report_url_expires_seconds

    async def execute(self, image_id: UUID, context: TenantContext) -> FinalizedPlanView:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        finalized = await self._finalized_plans.latest(context.tenant_id, image_id)
        if finalized is None:
            raise ImagePlanFinalizationNotFoundError(image_id)
        now = self._clock.now()
        png = self._storage.create_presigned_get(
            finalized.report_png_key,
            now,
            expires_in_seconds=self._report_url_expires_seconds,
        )
        pdf = self._storage.create_presigned_get(
            finalized.report_pdf_key,
            now,
            expires_in_seconds=self._report_url_expires_seconds,
        )
        return FinalizedPlanView(
            image_id=finalized.image_id,
            version=finalized.version,
            plan_revision=finalized.plan_revision,
            snapshot=finalized.snapshot,
            snapshot_sha256=finalized.snapshot_sha256,
            report_template_version=finalized.report_template_version,
            finalized_by=finalized.finalized_by,
            finalized_at=finalized.finalized_at,
            reports=(
                FinalizedReportLink("PNG", finalized.report_png_sha256, png.url, png.expires_at),
                FinalizedReportLink("PDF", finalized.report_pdf_sha256, pdf.url, pdf.expires_at),
            ),
        )


def _validate_finalization(document: dict[str, Any]) -> None:
    tplo = document.get("tplo")
    if not isinstance(tplo, dict) or tplo.get("eligibility") != "ELIGIBLE":
        raise ClinicalValidationError("A imagem TPLO precisa estar elegível para finalizar o plano")

    quality = document.get("radiographic_quality")
    required_quality = (
        "true_lateral",
        "femoral_condyles_superimposed",
        "stifle_and_tarsus_included",
        "tibial_axis_centered",
        "tibial_plateau_visible",
    )
    if not isinstance(quality, dict) or any(quality.get(key) != "PASS" for key in required_quality):
        raise ClinicalValidationError("Todos os critérios de qualidade radiográfica devem estar aprovados")

    calibration = document.get("calibration")
    if not isinstance(calibration, dict) or not isinstance(calibration.get("result"), dict):
        raise ClinicalValidationError("A calibração precisa estar calculada antes da finalização")

    measurement = document.get("tplo_measurement")
    if (
        not isinstance(measurement, dict)
        or measurement.get("status") != "CALCULATED"
        or measurement.get("tpa_degrees") is None
    ):
        raise ClinicalValidationError("O TPA precisa estar calculado antes da finalização")

    validation = document.get("clinical_validation")
    if not isinstance(validation, dict) or validation.get("status") != "APPROVED":
        raise ClinicalValidationError("A revisão clínica precisa estar aprovada antes da finalização")
    if not all(
        validation.get(field) is True
        for field in (
            "orientation_confirmed",
            "image_quality_confirmed",
            "calibration_confirmed",
            "anatomical_references_confirmed",
        )
    ):
        raise ClinicalValidationError("Todos os itens do checklist clínico devem estar confirmados")

    required_measurements = validation.get("required_measurements")
    if not isinstance(required_measurements, list) or not required_measurements:
        raise ClinicalValidationError("Informe as medidas obrigatórias antes da finalização")
    if "TPA" not in required_measurements:
        raise ClinicalValidationError("TPA precisa constar entre as medidas obrigatórias da finalização")
    has_blade = isinstance(tplo.get("blade_diameter_mm"), (int, float))
    if has_blade and "TPLO_CORRECTION" not in required_measurements:
        raise ClinicalValidationError(
            "TPLO_CORRECTION precisa constar entre as medidas obrigatórias quando houver lâmina selecionada"
        )
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
    for item in document.get("additional_measurements", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            available[item["id"]] = item.get("acceptance") == "PASS"
    missing = [name for name in required_measurements if not available.get(name, False)]
    if missing:
        raise ClinicalValidationError(
            "As medidas obrigatórias precisam estar calculadas e aceitas: " + ", ".join(missing)
        )
