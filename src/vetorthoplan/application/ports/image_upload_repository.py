from datetime import datetime
from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.imaging import ImageUpload


class ImageUploadRepository(Protocol):
    async def add(self, upload: ImageUpload) -> ImageUpload: ...

    async def add_idempotently(
        self,
        upload: ImageUpload,
        *,
        key_hash: str,
        request_hash: str,
    ) -> ImageUpload: ...

    async def get_by_idempotency_key(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        key_hash: str,
    ) -> ImageUpload | None: ...

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None: ...

    async def lock_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None: ...

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> ImageUpload | None: ...

    async def lock_case_for_upload(self, tenant_id: UUID, upload_id: UUID) -> bool: ...

    async def lock_case_for_image(self, tenant_id: UUID, image_id: UUID) -> bool: ...

    async def list_for_case(
        self, tenant_id: UUID, case_id: UUID, *, include_cancelled: bool = False
    ) -> list[ImageUpload]: ...

    async def save(self, upload: ImageUpload) -> ImageUpload: ...

    async def delete(self, tenant_id: UUID, upload_id: UUID) -> None: ...

    async def list_expired(self, now: datetime, *, limit: int = 500) -> list[ImageUpload]: ...

    async def count_active_for_case(
        self,
        tenant_id: UUID,
        case_id: UUID,
        now: datetime,
    ) -> int: ...
