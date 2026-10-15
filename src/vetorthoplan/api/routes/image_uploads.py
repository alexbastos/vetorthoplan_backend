from uuid import UUID

from fastapi import APIRouter

from vetorthoplan.api.dependencies import (
    CompleteImageUploadDependency,
    TenantContextDependency,
)
from vetorthoplan.api.schemas import CompletedImageUploadResponse, ErrorResponse

router = APIRouter(prefix="/api/v1/image-uploads", tags=["Image uploads"])


@router.post(
    "/{upload_id}/complete",
    status_code=202,
    response_model=CompletedImageUploadResponse,
    summary="Confirmar upload de radiografia",
    description=(
        "Confere no object storage o tamanho, tipo, checksum SHA-256, metadado da sessão "
        "e horário do envio. Quando todos os valores correspondem, promove a sessão para "
        "QUARANTINED e agenda um job durável de ingestão. A operação e o agendamento "
        "são idempotentes; o processamento clínico ocorre de forma assíncrona."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Sessão não encontrada no tenant ativo"},
        409: {
            "model": ErrorResponse,
            "description": "Objeto ausente, expirado ou divergente",
        },
    },
)
async def complete_image_upload(
    upload_id: UUID,
    context: TenantContextDependency,
    use_case: CompleteImageUploadDependency,
) -> CompletedImageUploadResponse:
    result = await use_case.execute(upload_id, context)
    upload = result.upload
    assert upload.completed_at is not None
    return CompletedImageUploadResponse(
        upload_id=upload.id,
        image_id=upload.image_id,
        case_id=upload.case_id,
        kind=upload.kind,
        media_type=upload.media_type,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        status=upload.status,
        completed_at=upload.completed_at,
        job_id=result.ingestion_job.id,
        job_status=result.ingestion_job.status,
    )
