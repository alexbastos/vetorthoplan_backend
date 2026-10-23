from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import ImageNotFoundError
from vetorthoplan.application.ports import ImageUploadRepository
from vetorthoplan.domain.imaging import ImageUpload


class RenameImage:
    def __init__(self, images: ImageUploadRepository) -> None:
        self._images = images

    async def execute(
        self, image_id: UUID, display_name: str, context: TenantContext
    ) -> ImageUpload:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        return await self._images.save(image.rename(display_name))
