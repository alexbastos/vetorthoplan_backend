from datetime import UTC, datetime
from uuid import UUID

import pytest

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import CaseNotFoundError, ImageUploadLimitExceededError
from vetorthoplan.application.ports import PresignedUploadTarget
from vetorthoplan.application.use_cases import CreateImageUpload, CreateImageUploadCommand
from vetorthoplan.domain.cases import BiologicalSex, Case
from vetorthoplan.domain.imaging import ImageUpload

UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000111")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000112")
CASE_ID = UUID("00000000-0000-4000-8000-000000000113")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000114")
OTHER_TENANT_ID = UUID("00000000-0000-4000-8000-000000000115")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000116")
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


class CaseRepository:
    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None:
        if tenant_id != TENANT_ID or case_id != CASE_ID:
            return None
        return Case.create(
            case_id=CASE_ID,
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            title="TPLO",
            animal_name="Paciente sintético",
            species="Canina",
            sex=BiologicalSex.UNKNOWN,
            now=NOW,
        )


class UploadRepository:
    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.uploads: list[ImageUpload] = []

    async def count_active_for_case(
        self,
        tenant_id: UUID,
        case_id: UUID,
        now: datetime,
    ) -> int:
        return self.count

    async def get_by_idempotency_key(self, tenant_id, actor_id, key_hash):
        return None

    async def add_idempotently(self, upload, *, key_hash, request_hash):
        self.uploads.append(upload)
        return upload

    async def add(self, upload: ImageUpload) -> ImageUpload:
        self.uploads.append(upload)
        return upload


class Storage:
    def create_presigned_post(
        self, upload: ImageUpload, *, expires_in_seconds: int = 300
    ) -> PresignedUploadTarget:
        return PresignedUploadTarget(
            method="POST",
            url="https://storage.example/upload",
            fields={"key": upload.object_key},
            expires_at=upload.expires_at,
        )


class IdGenerator:
    def __init__(self) -> None:
        self.ids = iter((UPLOAD_ID, IMAGE_ID))

    def new(self) -> UUID:
        return next(self.ids)


class Clock:
    def now(self) -> datetime:
        return NOW


def build_use_case(upload_repository: UploadRepository) -> CreateImageUpload:
    return CreateImageUpload(
        case_repository=CaseRepository(),
        upload_repository=upload_repository,
        storage=Storage(),
        id_generator=IdGenerator(),
        clock=Clock(),
        environment="test",
    )


def command() -> CreateImageUploadCommand:
    return CreateImageUploadCommand(
        original_filename="joelho.dcm",
        media_type="application/dicom",
        size_bytes=2048,
        sha256="b" * 64,
    )


@pytest.mark.asyncio
async def test_create_image_upload_is_tenant_scoped_and_uses_quarantine_key() -> None:
    repository = UploadRepository()
    result = await build_use_case(repository).execute(
        CASE_ID,
        command(),
        TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
        idempotency_key="create-upload-1",
    )

    assert result.upload.id == UPLOAD_ID
    assert result.upload.image_id == IMAGE_ID
    assert result.upload.object_key.startswith(f"quarantine/test/{TENANT_ID}/{CASE_ID}/")
    assert result.target.method == "POST"
    assert repository.uploads == [result.upload]


@pytest.mark.asyncio
async def test_create_image_upload_hides_case_from_other_tenant() -> None:
    with pytest.raises(CaseNotFoundError):
        await build_use_case(UploadRepository()).execute(
            CASE_ID,
            command(),
            TenantContext(tenant_id=OTHER_TENANT_ID, actor_id=ACTOR_ID),
            idempotency_key="create-upload-2",
        )


@pytest.mark.asyncio
async def test_create_image_upload_enforces_case_limit() -> None:
    with pytest.raises(ImageUploadLimitExceededError):
        await build_use_case(UploadRepository(count=20)).execute(
            CASE_ID,
            command(),
            TenantContext(tenant_id=TENANT_ID, actor_id=ACTOR_ID),
            idempotency_key="create-upload-3",
        )
