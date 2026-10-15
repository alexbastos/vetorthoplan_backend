from uuid import UUID

from fastapi import APIRouter

from vetorthoplan.api.dependencies import (
    GetImageDependency,
    GetImagePreviewDependency,
    GetIngestionJobDependency,
    ListCaseImagesDependency,
    TenantContextDependency,
)
from vetorthoplan.api.schemas import (
    ErrorResponse,
    ImageListResponse,
    ImagePreviewResponse,
    ImageResponse,
    IngestionJobResponse,
)

router = APIRouter(prefix="/api/v1")


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
    tags=["Ingestion jobs"],
    summary="Consultar processamento de imagem",
    responses={404: {"model": ErrorResponse, "description": "Job não encontrado"}},
)
async def get_ingestion_job(
    job_id: UUID,
    context: TenantContextDependency,
    use_case: GetIngestionJobDependency,
) -> IngestionJobResponse:
    return IngestionJobResponse.from_domain(await use_case.execute(job_id, context))


@router.get(
    "/cases/{case_id}/images",
    response_model=ImageListResponse,
    tags=["Images"],
    summary="Listar imagens do caso",
    responses={404: {"model": ErrorResponse, "description": "Caso não encontrado"}},
)
async def list_case_images(
    case_id: UUID,
    context: TenantContextDependency,
    use_case: ListCaseImagesDependency,
) -> ImageListResponse:
    images = await use_case.execute(case_id, context)
    return ImageListResponse(items=[ImageResponse.from_domain(image) for image in images])


@router.get(
    "/images/{image_id}",
    response_model=ImageResponse,
    tags=["Images"],
    summary="Consultar imagem",
    responses={404: {"model": ErrorResponse, "description": "Imagem não encontrada"}},
)
async def get_image(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetImageDependency,
) -> ImageResponse:
    return ImageResponse.from_domain(await use_case.execute(image_id, context))


@router.get(
    "/images/{image_id}/preview",
    response_model=ImagePreviewResponse,
    tags=["Images"],
    summary="Obter acesso temporário à prévia da imagem",
    responses={
        404: {"model": ErrorResponse, "description": "Imagem não encontrada"},
        409: {"model": ErrorResponse, "description": "Prévia ainda indisponível"},
    },
)
async def get_image_preview(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetImagePreviewDependency,
) -> ImagePreviewResponse:
    preview = await use_case.execute(image_id, context)
    return ImagePreviewResponse(**{
        field: getattr(preview, field) for field in ImagePreviewResponse.model_fields
    })
