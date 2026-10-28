from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.infrastructure.database.models import ImplantCatalogImportModel


class SqlAlchemyImplantCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approved_metadata(
        self, tenant_id: UUID, item_ids: set[UUID]
    ) -> dict[UUID, dict[str, object]]:
        if not item_ids:
            return {}
        rows = await self._session.scalars(
            select(ImplantCatalogImportModel).where(
                ImplantCatalogImportModel.tenant_id == tenant_id,
                ImplantCatalogImportModel.id.in_(item_ids),
                ImplantCatalogImportModel.status == "APPROVED",
            )
        )
        return {row.id: row.metadata_json for row in rows}
