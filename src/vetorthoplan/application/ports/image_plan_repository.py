from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.planning import ImagePlan


class ImagePlanRepository(Protocol):
    async def get(self, tenant_id: UUID, image_id: UUID) -> ImagePlan | None: ...

    async def add(self, plan: ImagePlan) -> ImagePlan | None: ...

    async def save(self, plan: ImagePlan, expected_revision: int) -> ImagePlan | None: ...
