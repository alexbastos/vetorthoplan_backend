from datetime import datetime
from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.imaging import ImageUpload


class ImageUploadRepository(Protocol):
    async def add(self, upload: ImageUpload) -> ImageUpload: ...

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None: ...

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> ImageUpload | None: ...

    async def list_for_case(self, tenant_id: UUID, case_id: UUID) -> list[ImageUpload]: ...

    async def save(self, upload: ImageUpload) -> ImageUpload: ...

    async def count_active_for_case(
        self,
        tenant_id: UUID,
        case_id: UUID,
        now: datetime,
    ) -> int: ...
