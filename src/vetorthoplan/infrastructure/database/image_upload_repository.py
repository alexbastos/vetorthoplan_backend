from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus
from vetorthoplan.infrastructure.database.models import ImageUploadModel


class SqlAlchemyImageUploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, upload: ImageUpload) -> ImageUpload:
        model = ImageUploadModel(
            id=upload.id,
            image_id=upload.image_id,
            tenant_id=upload.tenant_id,
            case_id=upload.case_id,
            original_filename=upload.original_filename,
            kind=upload.kind.value,
            media_type=upload.media_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            object_key=upload.object_key,
            status=upload.status.value,
            created_by=upload.created_by,
            created_at=upload.created_at,
            expires_at=upload.expires_at,
            completed_at=upload.completed_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None:
        statement = select(ImageUploadModel).where(
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.id == upload_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> ImageUpload | None:
        statement = select(ImageUploadModel).where(
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.image_id == image_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def list_for_case(self, tenant_id: UUID, case_id: UUID) -> list[ImageUpload]:
        statement = (
            select(ImageUploadModel)
            .where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.case_id == case_id,
            )
            .order_by(ImageUploadModel.created_at.desc(), ImageUploadModel.id.desc())
        )
        models = (await self._session.scalars(statement)).all()
        return [self._to_domain(model) for model in models]

    async def save(self, upload: ImageUpload) -> ImageUpload:
        statement = (
            update(ImageUploadModel)
            .where(
                ImageUploadModel.tenant_id == upload.tenant_id,
                ImageUploadModel.id == upload.id,
            )
            .values(
                status=upload.status.value,
                completed_at=upload.completed_at,
                detected_media_type=upload.detected_media_type,
                width_px=upload.width_px,
                height_px=upload.height_px,
                rejection_code=upload.rejection_code,
                processed_at=upload.processed_at,
                image_metadata=upload.metadata,
                preview_object_key=upload.preview_object_key,
                preview_media_type=upload.preview_media_type,
                preview_width_px=upload.preview_width_px,
                preview_height_px=upload.preview_height_px,
            )
        )
        await self._session.execute(statement)
        await self._session.flush()
        return upload

    async def count_active_for_case(
        self,
        tenant_id: UUID,
        case_id: UUID,
        now: datetime,
    ) -> int:
        statement = select(func.count()).select_from(ImageUploadModel).where(
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.case_id == case_id,
            ImageUploadModel.expires_at > now,
            ImageUploadModel.status == ImageUploadStatus.PENDING_UPLOAD.value,
        )
        return int((await self._session.scalar(statement)) or 0)

    @staticmethod
    def _to_domain(model: ImageUploadModel) -> ImageUpload:
        return ImageUpload(
            id=model.id,
            image_id=model.image_id,
            tenant_id=model.tenant_id,
            case_id=model.case_id,
            original_filename=model.original_filename,
            kind=ImageKind(model.kind),
            media_type=model.media_type,
            size_bytes=model.size_bytes,
            sha256=model.sha256,
            object_key=model.object_key,
            status=ImageUploadStatus(model.status),
            created_by=model.created_by,
            created_at=model.created_at,
            expires_at=model.expires_at,
            completed_at=model.completed_at,
            detected_media_type=model.detected_media_type,
            width_px=model.width_px,
            height_px=model.height_px,
            rejection_code=model.rejection_code,
            processed_at=model.processed_at,
            metadata=model.image_metadata,
            preview_object_key=model.preview_object_key,
            preview_media_type=model.preview_media_type,
            preview_width_px=model.preview_width_px,
            preview_height_px=model.preview_height_px,
        )
