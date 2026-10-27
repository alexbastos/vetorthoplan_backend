from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.api.dependencies import get_tenant_context
from vetorthoplan.application.context import TenantContext
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.infrastructure.database.models import ImplantCatalogImportModel
from vetorthoplan.infrastructure.database.session import get_database_session
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage

router = APIRouter(prefix="/api/v1/implant-catalog", tags=["Implant catalog"])
MAX_DWG_BYTES = 50 * 1024 * 1024


class CreateCatalogImportRequest(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=160)
    product_name: str = Field(min_length=1, max_length=200)
    product_code: str | None = Field(default=None, max_length=100)
    family: str = Field(min_length=1, max_length=120)
    catalog_version: str = Field(min_length=1, max_length=100)
    units: Literal["MM", "INCH", "UNITLESS"]
    source_reference: str | None = Field(default=None, max_length=1000)
    clinical_indication: str | None = Field(default=None, max_length=500)


class ReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class CatalogImportResponse(BaseModel):
    id: UUID
    metadata: dict[str, object]
    status: str
    original_filename: str | None
    source_sha256: str | None
    source_size_bytes: int | None
    converter_version: str | None
    conversion_metadata: dict[str, object] | None
    svg_url: str | None = None
    preview_url: str | None = None
    reviewed_at: datetime | None
    review_note: str | None
    error_code: str | None
    created_at: datetime


async def require_catalog_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    supplied_token: Annotated[str | None, Header(alias="X-Catalog-Admin-Token")] = None,
) -> None:
    expected = settings.implant_catalog_admin_token
    if not expected or not supplied_token or not hmac.compare_digest(expected, supplied_token):
        raise HTTPException(status_code=403, detail="Acesso administrativo ao catálogo não habilitado.")


def _storage(settings: Settings) -> S3PresignedPostStorage:
    return S3PresignedPostStorage(
        bucket=settings.storage_bucket,
        region=settings.storage_region,
        endpoint_url=settings.storage_endpoint_url,
        presign_endpoint_url=settings.storage_public_endpoint_url,
        expires_in_seconds=settings.preview_url_expires_seconds,
    )


def _response(row: ImplantCatalogImportModel, settings: Settings) -> CatalogImportResponse:
    storage = _storage(settings)
    now = datetime.now(UTC)
    return CatalogImportResponse(
        id=row.id,
        metadata=row.metadata_json,
        status=row.status,
        original_filename=row.original_filename,
        source_sha256=row.source_sha256,
        source_size_bytes=row.source_size_bytes,
        converter_version=row.converter_version,
        conversion_metadata=row.conversion_metadata,
        svg_url=(storage.create_presigned_get(row.svg_object_key, now).url if row.svg_object_key else None),
        preview_url=(
            storage.create_presigned_get(row.preview_object_key, now).url if row.preview_object_key else None
        ),
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
        error_code=row.error_code,
        created_at=row.created_at,
    )


@router.post(
    "/imports",
    status_code=status.HTTP_201_CREATED,
    response_model=CatalogImportResponse,
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Abrir importação de prótese",
    description=(
        "Cria um registro interno versionado. O item não aparece no catálogo até conversão "
        "e aprovação manual."
    ),
)
async def create_import(
    body: CreateCatalogImportRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogImportResponse:
    row = ImplantCatalogImportModel(
        id=uuid4(), tenant_id=context.tenant_id, metadata_json=body.model_dump(), status="AWAITING_SOURCE",
        created_by=context.actor_id, created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return _response(row, settings)


@router.put(
    "/imports/{import_id}/source",
    response_model=CatalogImportResponse,
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Enviar arquivo DWG original",
)
async def upload_source(
    import_id: UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    original_filename: Annotated[str | None, Header(alias="X-Original-Filename")] = None,
) -> CatalogImportResponse:
    row = await session.scalar(
        select(ImplantCatalogImportModel).where(
            ImplantCatalogImportModel.id == import_id,
            ImplantCatalogImportModel.tenant_id == context.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    if row.status != "AWAITING_SOURCE":
        raise HTTPException(status_code=409, detail="Esta importação já recebeu um arquivo.")
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Content-Length inválido.") from exc
    if content_length > MAX_DWG_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo excede o limite de 50 MiB.")
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > MAX_DWG_BYTES:
            raise HTTPException(status_code=413, detail="O arquivo excede o limite de 50 MiB.")
    if not payload:
        raise HTTPException(status_code=400, detail="O arquivo está vazio.")
    data = bytes(payload)
    filename = PurePath((original_filename or "").replace("\\", "/")).name
    if not filename.lower().endswith((".dwg", ".bak")):
        raise HTTPException(status_code=415, detail="Envie um arquivo .dwg ou .bak.")
    if not data.startswith(b"AC10"):
        raise HTTPException(status_code=422, detail="A assinatura do arquivo não corresponde a DWG.")
    digest = hashlib.sha256(data).hexdigest()
    object_key = f"implant-catalog/source/{row.id}/{uuid4()}-{filename}"
    await _storage(settings).store_object(
        object_key, data, "application/acad", metadata={"sha256": digest, "import-id": str(row.id)}
    )
    row.original_filename = filename[:255]
    row.source_object_key = object_key
    row.source_sha256 = digest
    row.source_size_bytes = len(data)
    row.status = "QUEUED" if settings.oda_conversion_service_url else "WAITING_FOR_CONVERTER"
    row.error_code = None
    await session.flush()
    return _response(row, settings)


@router.get(
    "/imports",
    response_model=list[CatalogImportResponse],
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Listar importações para revisão",
)
async def list_imports(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CatalogImportResponse]:
    rows = await session.scalars(
        select(ImplantCatalogImportModel)
        .where(ImplantCatalogImportModel.tenant_id == context.tenant_id)
        .order_by(ImplantCatalogImportModel.created_at.desc())
        .limit(200)
    )
    return [_response(row, settings) for row in rows]


@router.post(
    "/imports/{import_id}/approve",
    response_model=CatalogImportResponse,
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Aprovar item após revisão manual",
)
async def approve_import(
    import_id: UUID,
    body: ReviewRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogImportResponse:
    row = await _find_import(session, import_id, context.tenant_id)
    if row.status != "REVIEW_REQUIRED" or not row.svg_object_key or not row.preview_object_key:
        raise HTTPException(status_code=409, detail="A conversão precisa estar pronta para revisão.")
    row.status = "APPROVED"
    row.reviewed_by = context.actor_id
    row.reviewed_at = datetime.now(UTC)
    row.review_note = body.note
    await session.flush()
    return _response(row, settings)


@router.post(
    "/imports/{import_id}/reject",
    response_model=CatalogImportResponse,
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Rejeitar item na revisão manual",
)
async def reject_import(
    import_id: UUID,
    body: ReviewRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogImportResponse:
    row = await _find_import(session, import_id, context.tenant_id)
    if row.status != "REVIEW_REQUIRED":
        raise HTTPException(status_code=409, detail="Somente itens convertidos podem ser rejeitados.")
    row.status = "REJECTED"
    row.reviewed_by = context.actor_id
    row.reviewed_at = datetime.now(UTC)
    row.review_note = body.note
    await session.flush()
    return _response(row, settings)


@router.post(
    "/imports/{import_id}/retry",
    response_model=CatalogImportResponse,
    dependencies=[Depends(get_tenant_context), Depends(require_catalog_admin)],
    summary="Reenfileirar uma conversão que falhou",
)
async def retry_import(
    import_id: UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogImportResponse:
    row = await _find_import(session, import_id, context.tenant_id)
    if row.status != "FAILED" or not row.source_object_key:
        raise HTTPException(
            status_code=409,
            detail="Somente uma importação com DWG e falha pode ser reenfileirada.",
        )
    row.status = "QUEUED" if settings.oda_conversion_service_url else "WAITING_FOR_CONVERTER"
    row.error_code = None
    await session.flush()
    return _response(row, settings)


@router.get(
    "/items",
    response_model=list[CatalogImportResponse],
    dependencies=[Depends(get_tenant_context)],
    summary="Consultar itens de prótese aprovados",
)
async def list_approved_items(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CatalogImportResponse]:
    rows = await session.scalars(
        select(ImplantCatalogImportModel)
        .where(
            ImplantCatalogImportModel.tenant_id == context.tenant_id,
            ImplantCatalogImportModel.status == "APPROVED",
        )
        .order_by(ImplantCatalogImportModel.created_at.desc())
    )
    return [_response(row, settings) for row in rows]


async def _find_import(session: AsyncSession, import_id: UUID, tenant_id: UUID) -> ImplantCatalogImportModel:
    row = await session.scalar(
        select(ImplantCatalogImportModel).where(
            ImplantCatalogImportModel.id == import_id,
            ImplantCatalogImportModel.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    return row
