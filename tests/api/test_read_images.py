from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from vetorthoplan.api.dependencies import (
    get_image,
    get_ingestion_job,
    get_list_case_images,
    get_tenant_context,
)
from vetorthoplan.application.context import TenantContext
from vetorthoplan.bootstrap import create_app
from vetorthoplan.domain.imaging import ImageUpload
from vetorthoplan.domain.jobs import IngestionJob

NOW = datetime(2026, 9, 18, 11, 0, tzinfo=UTC)
TENANT_ID = UUID("00000000-0000-4000-8000-000000000501")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000502")
CASE_ID = UUID("00000000-0000-4000-8000-000000000503")
UPLOAD_ID = UUID("00000000-0000-4000-8000-000000000504")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000505")
JOB_ID = UUID("00000000-0000-4000-8000-000000000506")


def ready_image() -> ImageUpload:
    upload = ImageUpload.create(
        upload_id=UPLOAD_ID,
        image_id=IMAGE_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        actor_id=ACTOR_ID,
        original_filename="imagem.png",
        media_type="image/png",
        size_bytes=32,
        sha256="a" * 64,
        object_key="quarantine/test/image.png",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return upload.confirm(completed_at=NOW).start_processing().mark_ready(
        detected_media_type="image/png",
        width_px=640,
        height_px=480,
        metadata={},
        preview_object_key="derived/test/preview.png",
        preview_media_type="image/png",
        preview_width_px=640,
        preview_height_px=480,
        processed_at=NOW,
    )


def succeeded_job() -> IngestionJob:
    job = IngestionJob.schedule(
        job_id=JOB_ID,
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        image_id=IMAGE_ID,
        upload_id=UPLOAD_ID,
        scheduled_at=NOW,
    )
    return job.start(started_at=NOW).succeed(finished_at=NOW)


class StubListImages:
    async def execute(self, case_id: UUID, context: TenantContext) -> list[ImageUpload]:
        assert case_id == CASE_ID
        assert context.tenant_id == TENANT_ID
        return [ready_image()]


class StubGetImage:
    async def execute(self, image_id: UUID, context: TenantContext) -> ImageUpload:
        assert image_id == IMAGE_ID
        return ready_image()


class StubGetJob:
    async def execute(self, job_id: UUID, context: TenantContext) -> IngestionJob:
        assert job_id == JOB_ID
        return succeeded_job()


def build_app():
    app = create_app()
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TENANT_ID, ACTOR_ID)
    app.dependency_overrides[get_list_case_images] = lambda: StubListImages()
    app.dependency_overrides[get_image] = lambda: StubGetImage()
    app.dependency_overrides[get_ingestion_job] = lambda: StubGetJob()
    return app


@pytest.mark.asyncio
async def test_list_case_images_returns_processing_metadata() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/cases/{CASE_ID}/images")

    assert response.status_code == 200
    image = response.json()["items"][0]
    assert image["id"] == str(IMAGE_ID)
    assert image["status"] == "READY"
    assert (image["width_px"], image["height_px"]) == (640, 480)


@pytest.mark.asyncio
async def test_get_job_returns_terminal_state() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/jobs/{JOB_ID}")

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCEEDED"


def test_openapi_documents_img_02_queries() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/v1/jobs/{job_id}" in paths
    assert "/api/v1/cases/{case_id}/images" in paths
    assert "/api/v1/images/{image_id}" in paths
