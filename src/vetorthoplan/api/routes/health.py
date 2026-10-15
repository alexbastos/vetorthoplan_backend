from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    summary="Verificar processo",
    description="Confirma que o processo HTTP está ativo; não consulta dependências externas.",
)
async def live() -> dict[str, str]:
    return {"status": "ok"}

