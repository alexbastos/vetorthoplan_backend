from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.api.dependencies import (
    FinalizeImagePlanDependency,
    GetFinalizedImagePlanDependency,
    GetImageDependency,
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
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.infrastructure.database.models import ImplantCatalogImportModel
from vetorthoplan.infrastructure.database.session import get_database_session
from vetorthoplan.infrastructure.plan_image_exporter import PlanImageExporter
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage

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
    "/images/{image_id}/plan/export",
    response_class=Response,
    tags=["Planning"],
    summary="Exportar radiografia com ROI, rotação e próteses compostas",
    responses={
        200: {
            "description": "Imagem PNG composta para download.",
            "content": {"image/png": {}},
        },
        404: {"model": ErrorResponse, "description": "Imagem ou ativo de prótese não encontrado"},
        409: {"model": ErrorResponse, "description": "Prévia da imagem indisponível"},
        422: {"model": ErrorResponse, "description": "Ativo de prótese não renderizável"},
    },
)
async def export_image_plan(
    image_id: UUID,
    context: TenantContextDependency,
    image_reader: GetImageDependency,
    plan_reader: GetImagePlanDependency,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    image = await image_reader.execute(image_id, context)
    if (
        image.status != ImageUploadStatus.READY
        or image.preview_object_key is None
        or image.preview_width_px is None
        or image.preview_height_px is None
        or image.width_px is None
        or image.height_px is None
    ):
        raise HTTPException(status_code=409, detail={"code": "IMAGE_PREVIEW_UNAVAILABLE"})

    plan = await plan_reader.execute(image_id, context)
    document = plan.document
    implant_objects = [
        item for item in document.get("objects", [])
        if isinstance(item, dict) and item.get("type") == "IMPLANT" and item.get("visible", True)
    ]
    implant_ids = {UUID(str(item["catalog_item_id"])) for item in implant_objects}
    catalog_rows: dict[UUID, ImplantCatalogImportModel] = {}
    if implant_ids:
        rows = await session.scalars(
            select(ImplantCatalogImportModel).where(
                ImplantCatalogImportModel.id.in_(implant_ids),
                ImplantCatalogImportModel.tenant_id == context.tenant_id,
                ImplantCatalogImportModel.status == "APPROVED",
            )
        )
        catalog_rows = {row.id: row for row in rows}
        if set(catalog_rows) != implant_ids:
            raise HTTPException(status_code=404, detail={"code": "IMPLANT_NOT_AVAILABLE"})
        if any(row.preview_object_key is None for row in catalog_rows.values()):
            raise HTTPException(status_code=422, detail={"code": "IMPLANT_PREVIEW_UNAVAILABLE"})

    storage = S3PresignedPostStorage(
        bucket=settings.storage_bucket,
        region=settings.storage_region,
        endpoint_url=settings.storage_endpoint_url,
        presign_endpoint_url=settings.storage_public_endpoint_url,
        expires_in_seconds=settings.preview_url_expires_seconds,
    )
    preview_png = await storage.read_object(image.preview_object_key)
    implant_previews = {
        str(item_id): await storage.read_object(row.preview_object_key)
        for item_id, row in catalog_rows.items()
        if row.preview_object_key is not None
    }
    try:
        png = PlanImageExporter().render_png(
            preview_png=preview_png,
            document=document,
            implant_previews=implant_previews,
            image_dimensions_px=(image.width_px, image.height_px),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "PLAN_RASTER_EXPORT_FAILED"},
        ) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="plan-{image_id}.png"'},
    )


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
    session: Annotated[AsyncSession, Depends(get_database_session)],
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
                detail={
                    "code": "IMPLANT_NOT_AVAILABLE",
                    "message": "O implante não está aprovado ou não pertence à organização.",
                },
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
