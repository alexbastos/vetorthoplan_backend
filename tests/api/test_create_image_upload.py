from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import get_create_image_upload, get_tenant_context
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.ports import PresignedUploadTarget
from vetorthoplan.application.use_cases import CreateImageUploadCommand
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus

CASE_ID = UUID("00000000-0000-4000-8000-000000000121")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000122")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000123")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000124")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000125")
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


class StubCreateImageUpload:
    async def execute(
        self,
        case_id: UUID,
        command: CreateImageUploadCommand,
        context: TenantContext,
        *,
        idempotency_key: str,
    ):
        assert idempotency_key
        upload = ImageUpload(
            id=UPLOAD_ID,
            image_id=IMAGE_ID,
            tenant_id=context.tenant_id,
            case_id=case_id,
            original_filename=command.original_filename,
            kind=ImageKind.DICOM,
            media_type=command.media_type,
            size_bytes=command.size_bytes,
            sha256=command.sha256,
            object_key="quarantine/test/object.dcm",
            status=ImageUploadStatus.PENDING_UPLOAD,
            created_by=context.actor_id,
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            completed_at=None,
        )
        from vetorthoplan.application.use_cases import CreatedImageUpload

        return CreatedImageUpload(
            upload=upload,
            target=PresignedUploadTarget(
                method="POST",
                url="https://storage.example/upload",
                fields={"key": upload.object_key, "policy": "signed-policy"},
                expires_at=upload.expires_at,
            ),
        )


def build_app():
    app = create_app()
    app.dependency_overrides[get_create_image_upload] = lambda: StubCreateImageUpload()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    return app


@pytest.mark.asyncio
async def test_post_image_upload_returns_presigned_form_without_object_key_metadata() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/cases/{CASE_ID}/image-uploads",
            headers={"Idempotency-Key": "synthetic-upload-1"},
            json={
                "original_filename": "joelho.dcm",
                "media_type": "application/dicom",
                "size_bytes": 2048,
                "sha256": "c" * 64,
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_UPLOAD"
    assert response.json()["upload"]["method"] == "POST"
    assert response.json()["upload"]["url"] == "https://storage.example/upload"
    assert "object_key" not in response.json()


@pytest.mark.asyncio
async def test_post_image_upload_rejects_payload_larger_than_100_mib() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/cases/{CASE_ID}/image-uploads",
            headers={"Idempotency-Key": "synthetic-upload-2"},
            json={
                "original_filename": "joelho.dcm",
                "media_type": "application/dicom",
                "size_bytes": 104_857_601,
                "sha256": "c" * 64,
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_openapi_documents_image_upload_session() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    operation = schema["paths"]["/api/v1/cases/{case_id}/image-uploads"]["post"]
    assert operation["summary"] == "Criar sessão de upload de radiografia"
    assert {"201", "404", "409", "422"}.issubset(operation["responses"])
    assert any(
        parameter["name"] == "Idempotency-Key" and parameter["required"]
        for parameter in operation["parameters"]
    )
