from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.imaging import ImageUpload


@dataclass(frozen=True, slots=True)
class PresignedUploadTarget:
    method: str
    url: str
    fields: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredUploadObject:
    size_bytes: int
    media_type: str
    sha256: str
    upload_id: UUID | None
    uploaded_at: datetime


@dataclass(frozen=True, slots=True)
class StoredPreviewObject:
    object_key: str
    media_type: str


@dataclass(frozen=True, slots=True)
class PresignedReadTarget:
    url: str
    expires_at: datetime


class UploadStorage(Protocol):
    def create_presigned_post(
        self,
        upload: ImageUpload,
        *,
        expires_in_seconds: int | None = None,
    ) -> PresignedUploadTarget: ...

    async def inspect_uploaded_object(self, upload: ImageUpload) -> StoredUploadObject | None: ...

    async def read_uploaded_object(self, upload: ImageUpload) -> bytes: ...

    async def store_preview(
        self,
        upload: ImageUpload,
        content: bytes,
        media_type: str,
    ) -> StoredPreviewObject: ...

    def create_presigned_get(self, object_key: str, now: datetime) -> PresignedReadTarget: ...

    async def delete_object(self, object_key: str) -> None: ...
