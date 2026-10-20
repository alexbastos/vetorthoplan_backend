from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, status

from vetorthoplan.api.dependencies import (
    CreateCaseDependency,
    CreateImageUploadDependency,
    GetCaseDependency,
    ListCasesDependency,
    TenantContextDependency,
)
from vetorthoplan.api.pagination import decode_case_cursor, encode_case_cursor
from vetorthoplan.api.schemas import (
    CaseListItemResponse,
    CaseListResponse,
    CaseResponse,
    CreateCaseRequest,
    CreateCaseValidationErrorResponse,
    CreateImageUploadRequest,
    ErrorResponse,
    IdempotencyKeyConflictResponse,
    ImageUploadResponse,
    PresignedPostResponse,
)
from vetorthoplan.application.use_cases import (
    CreateCaseCommand,
    CreateImageUploadCommand,
    ListCasesQuery,
)
from vetorthoplan.domain.cases import CaseStatus

router = APIRouter(prefix="/api/v1/cases", tags=["Cases"])


@router.get(
    "",
    response_model=CaseListResponse,
    summary="Listar casos clínicos",
    description=(
        "Lista somente os casos do tenant ativo, em ordem decrescente de criação. "
        "Aceita busca textual, filtro por status e paginação por cursor opaco."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "Parâmetros ou cursor inválidos"},
    },
)
async def list_cases(
    context: TenantContextDependency,
    use_case: ListCasesDependency,
    limit: Annotated[int, Query(ge=1, le=100, description="Itens por página")] = 20,
    cursor: Annotated[
        str | None,
        Query(max_length=512, description="Cursor opaco devolvido na página anterior"),
    ] = None,
    case_status: Annotated[
        CaseStatus | None,
        Query(alias="status", description="Filtrar pelo estado do caso"),
    ] = None,
    search: Annotated[
        str | None,
        Query(max_length=200, description="Buscar por título, animal, espécie ou raça"),
    ] = None,
) -> CaseListResponse:
    page = await use_case.execute(
        ListCasesQuery(
            limit=limit,
            cursor=decode_case_cursor(cursor),
            status=case_status,
            search=search,
        ),
        context,
    )
    return CaseListResponse(
        items=[CaseListItemResponse.from_domain(case) for case in page.items],
        next_cursor=encode_case_cursor(page.next_cursor),
        status_counts={
            case_status: page.status_counts.get(case_status, 0)
            for case_status in CaseStatus
        },
    )


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
    summary="Consultar caso clínico",
    description="Retorna um caso somente quando ele pertence ao tenant ativo.",
    responses={
        404: {"model": ErrorResponse, "description": "Caso não encontrado no tenant ativo"},
        422: {"model": ErrorResponse, "description": "Identificador inválido"},
    },
)
async def get_case(
    case_id: UUID,
    context: TenantContextDependency,
    use_case: GetCaseDependency,
) -> CaseResponse:
    case = await use_case.execute(case_id, context)
    return CaseResponse.from_domain(case)


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar caso clínico",
    description=(
        "Cria um caso no tenant ativo, inicialmente no estado DRAFT. "
        "No ambiente local, tenant e usuário são fornecidos por um adapter temporário; "
        "eles nunca são aceitos no corpo da requisição. Com Idempotency-Key, repetir a mesma "
        "operação e o mesmo corpo devolve o caso original. A chave é vinculada ao tenant/ator, "
        "não expira e não pode ser reutilizada com outro corpo."
    ),
    responses={
        409: {
            "model": IdempotencyKeyConflictResponse,
            "description": "A chave de idempotência foi reutilizada com dados diferentes",
        },
        422: {
            "model": CreateCaseValidationErrorResponse,
            "description": "Entrada inválida ou violação de regra do caso",
        }
    },
)
async def create_case(
    request: CreateCaseRequest,
    context: TenantContextDependency,
    use_case: CreateCaseDependency,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            description="Chave estável para repetir esta operação sem criar outro caso",
        ),
    ] = None,
) -> CaseResponse:
    case = await use_case.execute(
        CreateCaseCommand(
            title=request.title,
            animal_name=request.animal_name,
            species=request.species,
            breed=request.breed,
            sex=request.sex,
            birth_date=request.birth_date,
            approximate_age_months=request.approximate_age_months,
            weight_kg=request.weight_kg,
            clinical_notes=request.clinical_notes,
        ),
        context,
        idempotency_key=idempotency_key,
    )
    return CaseResponse.from_domain(case)


@router.post(
    "/{case_id}/image-uploads",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar sessão de upload de radiografia",
    description=(
        "Valida os metadados do arquivo, registra uma sessão PENDING_UPLOAD em quarentena "
        "e devolve um formulário POST pré-assinado. O binário deve ser enviado diretamente "
        "ao object storage; esta resposta ainda não significa que a imagem foi ingerida. "
        "Idempotency-Key é obrigatório: a mesma chave e os mesmos metadados recuperam a sessão."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Caso não encontrado no tenant ativo"},
        409: {
            "model": ErrorResponse,
            "description": "Limite ativo atingido ou chave de idempotência reutilizada com outros dados",
        },
        422: {"model": ErrorResponse, "description": "Arquivo ou metadados inválidos"},
    },
)
async def create_image_upload(
    case_id: UUID,
    request: CreateImageUploadRequest,
    context: TenantContextDependency,
    use_case: CreateImageUploadDependency,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            description="Chave estável para recuperar a mesma sessão após falha de rede",
        ),
    ],
) -> ImageUploadResponse:
    result = await use_case.execute(
        case_id,
        CreateImageUploadCommand(
            original_filename=request.original_filename,
            media_type=request.media_type,
            size_bytes=request.size_bytes,
            sha256=request.sha256,
        ),
        context,
        idempotency_key=idempotency_key,
    )
    return ImageUploadResponse(
        upload_id=result.upload.id,
        image_id=result.upload.image_id,
        case_id=result.upload.case_id,
        kind=result.upload.kind,
        media_type=result.upload.media_type,
        size_bytes=result.upload.size_bytes,
        sha256=result.upload.sha256,
        status=result.upload.status,
        upload=PresignedPostResponse(
            method=result.target.method,
            url=result.target.url,
            fields=result.target.fields,
            expires_at=result.target.expires_at,
        ),
    )
