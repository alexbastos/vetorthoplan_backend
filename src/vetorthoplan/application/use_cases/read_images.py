from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseNotFoundError, ImageNotFoundError
from vetorthoplan.application.ports import CaseRepository, ImageUploadRepository
from vetorthoplan.domain.imaging import ImageUpload


class ListCaseImages:
    def __init__(
        self,
        *,
        case_repository: CaseRepository,
        image_repository: ImageUploadRepository,
    ) -> None:
        self._case_repository = case_repository
        self._image_repository = image_repository

    async def execute(self, case_id: UUID, context: TenantContext) -> list[ImageUpload]:
        case = await self._case_repository.get_by_id(context.tenant_id, case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return await self._image_repository.list_for_case(context.tenant_id, case_id)


class GetImage:
    def __init__(self, repository: ImageUploadRepository) -> None:
        self._repository = repository

    async def execute(self, image_id: UUID, context: TenantContext) -> ImageUpload:
        image = await self._repository.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        return image
