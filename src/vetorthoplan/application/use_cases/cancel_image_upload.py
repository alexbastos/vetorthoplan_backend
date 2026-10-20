from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ImageUploadCancellationConflictError,
    ImageUploadNotFoundError,
)
from vetorthoplan.application.ports import ImageUploadRepository, UploadStorage
from vetorthoplan.domain.imaging import ImageUploadStatus


class CancelImageUpload:
    def __init__(self, *, uploads: ImageUploadRepository, storage: UploadStorage) -> None:
        self._uploads = uploads
        self._storage = storage

    async def execute(self, upload_id: UUID, context: TenantContext) -> None:
        upload = await self._uploads.lock_by_id(context.tenant_id, upload_id)
        if upload is None:
            raise ImageUploadNotFoundError(upload_id)
        if upload.status == ImageUploadStatus.CANCELLED:
            await self._storage.delete_object(upload.object_key)
            return
        if upload.status != ImageUploadStatus.PENDING_UPLOAD:
            raise ImageUploadCancellationConflictError(upload_id)
        await self._storage.delete_object(upload.object_key)
        await self._uploads.save(upload.cancel())
