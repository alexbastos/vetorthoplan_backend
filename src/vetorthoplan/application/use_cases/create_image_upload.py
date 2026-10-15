from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseNotFoundError, ImageUploadLimitExceededError
from vetorthoplan.application.ports import (
    CaseRepository,
    Clock,
    IdGenerator,
    ImageUploadRepository,
    PresignedUploadTarget,
    UploadStorage,
)
from vetorthoplan.domain.imaging import ImageUpload


@dataclass(frozen=True, slots=True)
class CreateImageUploadCommand:
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CreatedImageUpload:
    upload: ImageUpload
    target: PresignedUploadTarget


class CreateImageUpload:
    def __init__(
        self,
        *,
        case_repository: CaseRepository,
        upload_repository: ImageUploadRepository,
        storage: UploadStorage,
        id_generator: IdGenerator,
        clock: Clock,
        expires_in_seconds: int = 300,
        max_uploads_per_case: int = 20,
        environment: str = "local",
    ) -> None:
        self._case_repository = case_repository
        self._upload_repository = upload_repository
        self._storage = storage
        self._id_generator = id_generator
        self._clock = clock
        self._expires_in_seconds = expires_in_seconds
        self._max_uploads_per_case = max_uploads_per_case
        self._environment = environment

    async def execute(
        self,
        case_id: UUID,
        command: CreateImageUploadCommand,
        context: TenantContext,
    ) -> CreatedImageUpload:
        case = await self._case_repository.get_by_id(context.tenant_id, case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        now = self._clock.now()
        upload_count = await self._upload_repository.count_active_for_case(
            context.tenant_id,
            case_id,
            now,
        )
        if upload_count >= self._max_uploads_per_case:
            raise ImageUploadLimitExceededError(case_id, self._max_uploads_per_case)

        upload_id = self._id_generator.new()
        image_id = self._id_generator.new()
        expires_at = now + timedelta(seconds=self._expires_in_seconds)
        suffix = PurePath(command.original_filename.strip()).suffix.lower().lstrip(".") or "bin"
        object_key = (
            f"quarantine/{self._environment}/{context.tenant_id}/{case_id}/"
            f"{upload_id}/{image_id}.{suffix}"
        )
        upload = ImageUpload.create(
            upload_id=upload_id,
            image_id=image_id,
            tenant_id=context.tenant_id,
            case_id=case_id,
            actor_id=context.actor_id,
            original_filename=command.original_filename,
            media_type=command.media_type,
            size_bytes=command.size_bytes,
            sha256=command.sha256,
            object_key=object_key,
            created_at=now,
            expires_at=expires_at,
        )
        persisted = await self._upload_repository.add(upload)
        target = self._storage.create_presigned_post(persisted)
        return CreatedImageUpload(upload=persisted, target=target)
