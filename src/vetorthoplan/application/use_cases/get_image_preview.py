from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import ImageNotFoundError, ImagePreviewUnavailableError
from vetorthoplan.application.ports import Clock, ImageUploadRepository, UploadStorage
from vetorthoplan.domain.imaging import ImageUploadStatus


@dataclass(frozen=True, slots=True)
class ImagePreview:
    url: str
    media_type: str
    width_px: int
    height_px: int
    expires_at: datetime


class GetImagePreview:
    def __init__(
        self,
        repository: ImageUploadRepository,
        storage: UploadStorage,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._clock = clock

    async def execute(self, image_id: UUID, context: TenantContext) -> ImagePreview:
        image = await self._repository.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if (
            image.status != ImageUploadStatus.READY
            or image.preview_object_key is None
            or image.preview_media_type is None
            or image.preview_width_px is None
            or image.preview_height_px is None
        ):
            raise ImagePreviewUnavailableError(image_id)
        target = self._storage.create_presigned_get(image.preview_object_key, self._clock.now())
        return ImagePreview(
            url=target.url,
            media_type=image.preview_media_type,
            width_px=image.preview_width_px,
            height_px=image.preview_height_px,
            expires_at=target.expires_at,
        )
