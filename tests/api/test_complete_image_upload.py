from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import get_complete_image_upload, get_tenant_context
from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import CompletedImageUpload
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob

UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000221")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000222")
CASE_ID = UUID("00000000-0000-4000-8000-000000000223")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000224")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000225")
JOB_ID = UUID("00000000-0000-4000-8000-000000000226")
NOW = datetime(2026, 9, 17, 13, 0, tzinfo=UTC)


class StubCompleteImageUpload:
    async def execute(self, upload_id: UUID, context: TenantContext) -> CompletedImageUpload:
        upload = ImageUpload(
            id=upload_id,
            image_id=IMAGE_ID,
            tenant_id=context.tenant_id,
            case_id=CASE_ID,
            original_filename="joelho.dcm",
            kind=ImageKind.DICOM,
            media_type="application/dicom",
            size_bytes=4096,
            sha256="f" * 64,
            object_key="quarantine/test/joelho.dcm",
            status=ImageUploadStatus.QUARANTINED,
            created_by=context.actor_id,
            created_at=NOW,
            expires_at=NOW,
            completed_at=NOW,
        )
        job = IngestionJob.schedule(
            job_id=JOB_ID,
            tenant_id=context.tenant_id,
            case_id=CASE_ID,
            image_id=IMAGE_ID,
            upload_id=upload_id,
            scheduled_at=NOW,
        )
        return CompletedImageUpload(upload=upload, ingestion_job=job)


def build_app():
    app = create_app()
    app.dependency_overrides[get_complete_image_upload] = lambda: StubCompleteImageUpload()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    return app


@pytest.mark.asyncio
async def test_complete_image_upload_returns_quarantined_state() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(f"/api/v1/image-uploads/{UPLOAD_ID}/complete")

    assert response.status_code == 202
    assert response.json()["upload_id"] == str(UPLOAD_ID)
    assert response.json()["status"] == "QUARANTINED"
    assert response.json()["completed_at"] == "2026-09-17T13:00:00Z"
    assert response.json()["job_id"] == str(JOB_ID)
    assert response.json()["job_status"] == "QUEUED"


@pytest.mark.asyncio
async def test_openapi_documents_complete_image_upload() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    operation = schema["paths"]["/api/v1/image-uploads/{upload_id}/complete"]["post"]
    assert operation["summary"] == "Confirmar upload de radiografia"
    assert {"202", "404", "409", "422"}.issubset(operation["responses"])
