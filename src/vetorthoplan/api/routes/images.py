from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from vetorthoplan.api.dependencies import (
    DeleteImageDependency,
    GetImageDependency,
    GetImagePreviewDependency,
    GetIngestionJobDependency,
    ListCaseImagesDependency,
    RetryIngestionJobDependency,
    TenantContextDependency,
    get_tenant_context,
)
from vetorthoplan.api.schemas import (
    ErrorResponse,
    ImageIngestionJobResponse,
    ImageListResponse,
    ImagePreviewResponse,
    ImageResponse,
    IngestionJobResponse,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_tenant_context)])


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
    "/images/{image_id}/job",
    response_model=ImageIngestionJobResponse,
    tags=["Ingestion jobs"],
    summary="Consultar processamento associado à imagem",
    description="Retorna job nulo se a confirmação do upload ainda não o tiver criado.",
    responses={404: {"model": ErrorResponse, "description": "Imagem não encontrada"}},
)
async def get_image_ingestion_job(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetIngestionJobDependency,
) -> ImageIngestionJobResponse:
    job = await use_case.execute_for_image(image_id, context)
    return ImageIngestionJobResponse(
        job=IngestionJobResponse.from_domain(job) if job is not None else None
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingestion jobs"],
    summary="Reenfileirar job com falha operacional",
    description=(
        "Reaproveita o mesmo job e o mesmo arquivo confirmado. Apenas jobs FAILED podem ser "
        "reenfileirados; rejeições de conteúdo exigem novo upload corrigido."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Job não encontrado"},
        409: {"model": ErrorResponse, "description": "Job não está em FAILED"},
    },
)
async def retry_ingestion_job(
    job_id: UUID,
    context: TenantContextDependency,
    use_case: RetryIngestionJobDependency,
) -> IngestionJobResponse:
    return IngestionJobResponse.from_domain(await use_case.execute(job_id, context))


@router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Images"],
    summary="Excluir imagem",
    description=(
        "Remove original, prévia, plano e registros do job. A exclusão é recusada enquanto "
        "o job estiver QUEUED/PROCESSING ou enquanto uma sessão de upload ainda for válida."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Imagem não encontrada"},
        409: {"model": ErrorResponse, "description": "Upload ou processamento ativo"},
    },
)
async def delete_image(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: DeleteImageDependency,
) -> Response:
    await use_case.execute(image_id, context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    job_reader: GetIngestionJobDependency,
) -> ImageListResponse:
    images = await use_case.execute(case_id, context)
    items = []
    for image in images:
        job = await job_reader.execute_for_image(image.image_id, context)
        items.append(ImageResponse.from_domain(image, job_id=job.id if job else None))
    return ImageListResponse(items=items)


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
    job_reader: GetIngestionJobDependency,
) -> ImageResponse:
    image = await use_case.execute(image_id, context)
    job = await job_reader.execute_for_image(image_id, context)
    return ImageResponse.from_domain(image, job_id=job.id if job else None)


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
