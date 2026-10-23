from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.application.errors import ImageUploadIdempotencyConflictError
from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus
from vetorthoplan.infrastructure.database.models import CaseModel, ImageUploadModel


class SqlAlchemyImageUploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, upload: ImageUpload) -> ImageUpload:
        model = ImageUploadModel(**self._values(upload))
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    @staticmethod
    def _values(upload: ImageUpload) -> dict[str, object]:
        return dict(
            id=upload.id,
            image_id=upload.image_id,
            tenant_id=upload.tenant_id,
            case_id=upload.case_id,
            original_filename=upload.original_filename,
            display_name=upload.display_name,
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
            idempotency_key_hash=upload.idempotency_key_hash,
            request_hash=upload.request_hash,
        )

    async def add_idempotently(
        self,
        upload: ImageUpload,
        *,
        key_hash: str,
        request_hash: str,
    ) -> ImageUpload:
        values = self._values(upload)
        values.update(idempotency_key_hash=key_hash, request_hash=request_hash)
        statement = (
            pg_insert(ImageUploadModel)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_image_uploads_idempotency_scope")
            .returning(ImageUploadModel)
        )
        model = await self._session.scalar(statement)
        if model is None:
            model = await self._session.scalar(
                select(ImageUploadModel).where(
                    ImageUploadModel.tenant_id == upload.tenant_id,
                    ImageUploadModel.created_by == upload.created_by,
                    ImageUploadModel.idempotency_key_hash == key_hash,
                )
            )
            if model is None:
                raise RuntimeError("Não foi possível recuperar a sessão de upload idempotente.")
            if model.request_hash != request_hash:
                raise ImageUploadIdempotencyConflictError
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_idempotency_key(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        key_hash: str,
    ) -> ImageUpload | None:
        model = await self._session.scalar(
            select(ImageUploadModel).where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.created_by == actor_id,
                ImageUploadModel.idempotency_key_hash == key_hash,
            )
        )
        return self._to_domain(model) if model else None

    async def get_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None:
        statement = select(ImageUploadModel).where(
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.id == upload_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def lock_by_id(self, tenant_id: UUID, upload_id: UUID) -> ImageUpload | None:
        model = await self._session.scalar(
            select(ImageUploadModel)
            .where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.id == upload_id,
            )
            .with_for_update()
        )
        return self._to_domain(model) if model else None

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> ImageUpload | None:
        statement = select(ImageUploadModel).where(
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.image_id == image_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def find_duplicate_for_case(
        self,
        tenant_id: UUID,
        case_id: UUID,
        sha256: str,
        now: datetime,
    ) -> ImageUpload | None:
        model = await self._session.scalar(
            select(ImageUploadModel)
            .where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.case_id == case_id,
                ImageUploadModel.sha256 == sha256,
                ImageUploadModel.status != ImageUploadStatus.CANCELLED.value,
                or_(
                    ImageUploadModel.completed_at.is_not(None),
                    ImageUploadModel.expires_at > now,
                ),
            )
            .order_by(ImageUploadModel.created_at, ImageUploadModel.id)
            .limit(1)
        )
        return self._to_domain(model) if model else None

    async def lock_case_for_upload(self, tenant_id: UUID, upload_id: UUID) -> bool:
        case_id = await self._session.scalar(
            select(ImageUploadModel.case_id).where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.id == upload_id,
            )
        )
        if case_id is None:
            return False
        model = await self._session.scalar(
            select(CaseModel).where(
                CaseModel.tenant_id == tenant_id,
                CaseModel.id == case_id,
            ).with_for_update()
        )
        return model is not None

    async def lock_case_for_image(self, tenant_id: UUID, image_id: UUID) -> bool:
        upload_id = await self._session.scalar(
            select(ImageUploadModel.id).where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.image_id == image_id,
            )
        )
        if upload_id is None:
            return False
        return await self.lock_case_for_upload(tenant_id, upload_id)

    async def list_for_case(
        self, tenant_id: UUID, case_id: UUID, *, include_cancelled: bool = False
    ) -> list[ImageUpload]:
        filters = [
            ImageUploadModel.tenant_id == tenant_id,
            ImageUploadModel.case_id == case_id,
        ]
        if not include_cancelled:
            filters.append(ImageUploadModel.status != ImageUploadStatus.CANCELLED.value)
        statement = (
            select(ImageUploadModel)
            .where(*filters)
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
                display_name=upload.display_name,
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

    async def delete(self, tenant_id: UUID, upload_id: UUID) -> None:
        await self._session.execute(
            delete(ImageUploadModel).where(
                ImageUploadModel.tenant_id == tenant_id,
                ImageUploadModel.id == upload_id,
            )
        )
        await self._session.flush()

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

    async def list_expired(self, now: datetime, *, limit: int = 500) -> list[ImageUpload]:
        statement = (
            select(ImageUploadModel)
            .where(
                ImageUploadModel.status.in_(
                    [ImageUploadStatus.PENDING_UPLOAD.value, ImageUploadStatus.CANCELLED.value]
                ),
                ImageUploadModel.expires_at <= now,
            )
            .order_by(ImageUploadModel.expires_at, ImageUploadModel.id)
            .limit(limit)
        )
        models = (await self._session.scalars(statement)).all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: ImageUploadModel) -> ImageUpload:
        return ImageUpload(
            id=model.id,
            image_id=model.image_id,
            tenant_id=model.tenant_id,
            case_id=model.case_id,
            original_filename=model.original_filename,
            display_name=model.display_name,
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
            idempotency_key_hash=model.idempotency_key_hash,
            request_hash=model.request_hash,
        )
