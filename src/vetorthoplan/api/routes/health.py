from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.infrastructure.database.session import get_database_session

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    summary="Verificar processo",
    description="Confirma que o processo HTTP está ativo; não consulta dependências externas.",
)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Verificar prontidão da API",
    description="Confirma que o processo pode consultar o PostgreSQL; distinto de /health/live.",
)
async def ready(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "dependency": "database"},
        ) from exc
    return {"status": "ready", "database": "ok"}

