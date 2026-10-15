import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from botocore.stub import Stubber

from vetorthoplan.domain.imaging import ImageUpload
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage


def test_s3_presigned_post_pins_key_type_checksum_and_exact_size(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret-key")
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    upload = ImageUpload.create(
        upload_id=UUID("00000000-0000-4000-8000-000000000131"),
        image_id=UUID("00000000-0000-4000-8000-000000000132"),
        tenant_id=UUID("00000000-0000-4000-8000-000000000133"),
        case_id=UUID("00000000-0000-4000-8000-000000000134"),
        actor_id=UUID("00000000-0000-4000-8000-000000000135"),
        original_filename="imagem.png",
        media_type="image/png",
        size_bytes=4096,
        sha256="d" * 64,
        object_key="quarantine/test/imagem.png",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    storage = S3PresignedPostStorage(
        bucket="synthetic-private-bucket",
        region="us-east-1",
        endpoint_url=None,
        expires_in_seconds=300,
    )

    target = storage.create_presigned_post(upload)

    assert target.method == "POST"
    assert target.url == "https://synthetic-private-bucket.s3.amazonaws.com/"
    assert target.fields["key"] == upload.object_key
    assert target.fields["Content-Type"] == upload.media_type
    assert target.fields["x-amz-meta-upload-id"] == str(upload.id)
    assert "x-amz-signature" in target.fields
    policy = json.loads(base64.b64decode(target.fields["policy"]))
    assert ["content-length-range", 4096, 4096] in policy["conditions"]
    assert {"x-amz-checksum-sha256": target.fields["x-amz-checksum-sha256"]} in policy[
        "conditions"
    ]


@pytest.mark.asyncio
async def test_s3_head_converts_verified_object_metadata(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret-key")
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    upload = ImageUpload.create(
        upload_id=UUID("00000000-0000-4000-8000-000000000141"),
        image_id=UUID("00000000-0000-4000-8000-000000000142"),
        tenant_id=UUID("00000000-0000-4000-8000-000000000143"),
        case_id=UUID("00000000-0000-4000-8000-000000000144"),
        actor_id=UUID("00000000-0000-4000-8000-000000000145"),
        original_filename="imagem.png",
        media_type="image/png",
        size_bytes=4096,
        sha256="a" * 64,
        object_key="quarantine/test/imagem.png",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    storage = S3PresignedPostStorage(
        bucket="synthetic-private-bucket",
        region="us-east-1",
        endpoint_url=None,
        expires_in_seconds=300,
    )
    checksum = base64.b64encode(bytes.fromhex(upload.sha256)).decode("ascii")
    with Stubber(storage._client) as stubber:  # noqa: SLF001
        stubber.add_response(
            "head_object",
            {
                "ContentLength": upload.size_bytes,
                "ContentType": upload.media_type,
                "ChecksumSHA256": checksum,
                "Metadata": {"upload-id": str(upload.id)},
                "LastModified": now + timedelta(minutes=1),
            },
            {
                "Bucket": "synthetic-private-bucket",
                "Key": upload.object_key,
                "ChecksumMode": "ENABLED",
            },
        )

        stored = await storage.inspect_uploaded_object(upload)

    assert stored is not None
    assert stored.size_bytes == upload.size_bytes
    assert stored.media_type == upload.media_type
    assert stored.sha256 == upload.sha256
    assert stored.upload_id == upload.id
    assert stored.uploaded_at == now + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_s3_head_returns_none_when_object_does_not_exist(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret-key")
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    upload = ImageUpload.create(
        upload_id=UUID("00000000-0000-4000-8000-000000000151"),
        image_id=UUID("00000000-0000-4000-8000-000000000152"),
        tenant_id=UUID("00000000-0000-4000-8000-000000000153"),
        case_id=UUID("00000000-0000-4000-8000-000000000154"),
        actor_id=UUID("00000000-0000-4000-8000-000000000155"),
        original_filename="imagem.jpeg",
        media_type="image/jpeg",
        size_bytes=2048,
        sha256="b" * 64,
        object_key="quarantine/test/imagem.jpeg",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    storage = S3PresignedPostStorage(
        bucket="synthetic-private-bucket",
        region="us-east-1",
        endpoint_url=None,
        expires_in_seconds=300,
    )
    with Stubber(storage._client) as stubber:  # noqa: SLF001
        stubber.add_client_error(
            "head_object",
            service_error_code="NoSuchKey",
            service_message="Not found",
            http_status_code=404,
            expected_params={
                "Bucket": "synthetic-private-bucket",
                "Key": upload.object_key,
                "ChecksumMode": "ENABLED",
            },
        )

        stored = await storage.inspect_uploaded_object(upload)

    assert stored is None
