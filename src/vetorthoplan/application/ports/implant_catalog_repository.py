from typing import Protocol
from uuid import UUID


class ImplantCatalogRepository(Protocol):
    async def approved_metadata(
        self, tenant_id: UUID, item_ids: set[UUID]
    ) -> dict[UUID, dict[str, object]]: ...
