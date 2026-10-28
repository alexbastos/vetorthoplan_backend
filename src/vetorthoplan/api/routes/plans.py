from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.api.dependencies import (
    FinalizeImagePlanDependency,
    GetFinalizedImagePlanDependency,
    GetImagePlanDependency,
    ReviewImagePlanDependency,
    SaveImagePlanDependency,
    TenantContextDependency,
    ValidateImagePlanDependency,
    get_tenant_context,
)
from vetorthoplan.api.schemas import (
    ErrorResponse,
    FinalizedImagePlanResponse,
    FinalizeImagePlanRequest,
    ImagePlanResponse,
    ImagePlanValidationResponse,
    ReviewImagePlanRequest,
    SaveImagePlanRequest,
    ValidateImagePlanRequest,
)
from vetorthoplan.application.use_cases.finalize_image_plan import FinalizedPlanView
from vetorthoplan.application.use_cases.image_plans import ReviewImagePlanCommand
from vetorthoplan.infrastructure.database.models import ImplantCatalogImportModel
from vetorthoplan.infrastructure.database.session import get_database_session

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_tenant_context)])


@router.get(
    "/images/{image_id}/plan",
    response_model=ImagePlanResponse,
    tags=["Planning"],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def get_image_plan(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetImagePlanDependency,
) -> ImagePlanResponse:
    plan = await use_case.execute(image_id, context)
    return ImagePlanResponse(**{field: getattr(plan, field) for field in ImagePlanResponse.model_fields})


@router.post(
    "/images/{image_id}/plan/validate",
    response_model=ImagePlanValidationResponse,
    tags=["Planning"],
    summary="Pré-validar tecnicamente um plano TPLO salvo",
    description=(
        "Executa verificações estruturais sem alterar o plano. READY_FOR_CLINICAL_REVIEW indica "
        "consistência técnica para avaliação veterinária e não representa homologação clínica."
    ),
    responses={404: {"model": ErrorResponse}},
)
async def validate_image_plan(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: ValidateImagePlanDependency,
    payload: ValidateImagePlanRequest | None = None,
) -> ImagePlanValidationResponse:
    validation = await use_case.execute(
        image_id,
        context,
        base_revision=payload.base_revision if payload is not None else None,
    )
    return ImagePlanValidationResponse(
        image_id=validation.image_id,
        plan_revision=validation.plan_revision,
        status=validation.status,
        checks=validation.checks,
        blocking_errors=[
            {"code": issue.code, "message": issue.message, "field": issue.field}
            for issue in validation.blocking_errors
        ],
        warnings=[
            {"code": issue.code, "message": issue.message, "field": issue.field}
            for issue in validation.warnings
        ],
        validated_at=validation.validated_at,
    )


@router.put(
    "/images/{image_id}/plan",
    response_model=ImagePlanResponse,
    tags=["Planning"],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def save_image_plan(
    image_id: UUID,
    payload: SaveImagePlanRequest,
    context: TenantContextDependency,
    use_case: SaveImagePlanDependency,
    session: AsyncSession = Depends(get_database_session),
) -> ImagePlanResponse:
    implants = [item for item in payload.document.objects if item.type == "IMPLANT"]
    implant_ids = {item.catalog_item_id for item in implants}
    if implant_ids:
        rows = list(
            await session.scalars(
                select(ImplantCatalogImportModel).where(
                    ImplantCatalogImportModel.id.in_(implant_ids),
                    ImplantCatalogImportModel.tenant_id == context.tenant_id,
                    ImplantCatalogImportModel.status == "APPROVED",
                )
            )
        )
        catalog_items = {row.id: row for row in rows}
        if set(catalog_items) != implant_ids:
            raise HTTPException(
                status_code=422,
                detail={"code": "IMPLANT_NOT_AVAILABLE", "message": "O implante não está aprovado ou não pertence à organização."},
            )
        for implant in implants:
            metadata = catalog_items[implant.catalog_item_id].metadata_json
            if implant.variant is not None and implant.variant not in metadata.get("variants", []):
                raise HTTPException(status_code=422, detail={"code": "IMPLANT_VARIANT_INVALID"})
            if implant.view is not None and implant.view not in metadata.get("views", []):
                raise HTTPException(status_code=422, detail={"code": "IMPLANT_VIEW_INVALID"})
    plan = await use_case.execute(
        image_id,
        payload.base_revision,
        payload.document.model_dump(mode="json"),
        context,
    )
    return ImagePlanResponse(**{field: getattr(plan, field) for field in ImagePlanResponse.model_fields})


@router.post(
    "/images/{image_id}/plan/review",
    response_model=ImagePlanResponse,
    tags=["Planning"],
    summary="Avançar a revisão clínica do plano TPLO",
    description=(
        "Aplica somente a decisão e o checklist clínico ao plano persistido. "
        "A geometria e as medidas não são aceitas no payload desta operação; "
        "a decisão é tomada sobre a revisão enviada para análise."
    ),
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def review_image_plan(
    image_id: UUID,
    payload: ReviewImagePlanRequest,
    context: TenantContextDependency,
    use_case: ReviewImagePlanDependency,
) -> ImagePlanResponse:
    plan = await use_case.execute(
        image_id,
        payload.base_revision,
        ReviewImagePlanCommand(
            status=payload.status,
            orientation_confirmed=payload.orientation_confirmed,
            image_quality_confirmed=payload.image_quality_confirmed,
            calibration_confirmed=payload.calibration_confirmed,
            anatomical_references_confirmed=payload.anatomical_references_confirmed,
            required_measurements=payload.required_measurements,
            reviewer_notes=payload.reviewer_notes,
            rejection_reason=payload.rejection_reason,
        ),
        context,
    )
    return ImagePlanResponse(**{field: getattr(plan, field) for field in ImagePlanResponse.model_fields})


@router.post(
    "/images/{image_id}/plan/finalize",
    response_model=FinalizedImagePlanResponse,
    tags=["Planning"],
    summary="Finalizar plano cirúrgico e gerar relatórios versionados",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def finalize_image_plan(
    image_id: UUID,
    payload: FinalizeImagePlanRequest,
    context: TenantContextDependency,
    use_case: FinalizeImagePlanDependency,
) -> FinalizedImagePlanResponse:
    finalized = await use_case.execute(image_id, payload.base_revision, context)
    return _finalized_response(finalized)


@router.get(
    "/images/{image_id}/plan/finalization",
    response_model=FinalizedImagePlanResponse,
    tags=["Planning"],
    summary="Consultar finalização e obter links atualizados dos relatórios",
    responses={404: {"model": ErrorResponse}},
)
async def get_finalized_image_plan(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetFinalizedImagePlanDependency,
) -> FinalizedImagePlanResponse:
    return _finalized_response(await use_case.execute(image_id, context))


def _finalized_response(finalized: FinalizedPlanView) -> FinalizedImagePlanResponse:
    return FinalizedImagePlanResponse(
        image_id=finalized.image_id,
        version=finalized.version,
        plan_revision=finalized.plan_revision,
        snapshot=finalized.snapshot,
        snapshot_sha256=finalized.snapshot_sha256,
        report_template_version=finalized.report_template_version,
        finalized_by=finalized.finalized_by,
        finalized_at=finalized.finalized_at,
        reports=[
            {
                "format": report.format,
                "sha256": report.sha256,
                "download_url": report.download_url,
                "expires_at": report.expires_at,
            }
            for report in finalized.reports
        ],
    )
