import asyncio
import base64
import binascii
import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from vetorthoplan.application.ports import (
    PresignedReadTarget,
    PresignedUploadTarget,
    StoredPreviewObject,
    StoredUploadObject,
)
from vetorthoplan.domain.imaging import ImageUpload


class S3PresignedPostStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        presign_endpoint_url: str | None = None,
        expires_in_seconds: int,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - packaging failure, not a domain branch
            raise RuntimeError("A dependência boto3 é necessária para assinar uploads.") from exc

        self._bucket = bucket
        self._expires_in_seconds = expires_in_seconds
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        self._presign_client = (
            boto3.client(
                "s3",
                region_name=region,
                endpoint_url=presign_endpoint_url,
                config=Config(signature_version="s3v4"),
            )
            if presign_endpoint_url and presign_endpoint_url != endpoint_url
            else self._client
        )

    def create_presigned_post(
        self,
        upload: ImageUpload,
        *,
        expires_in_seconds: int | None = None,
    ) -> PresignedUploadTarget:
        checksum_base64 = base64.b64encode(bytes.fromhex(upload.sha256)).decode("ascii")
        fields = {
            "Content-Type": upload.media_type,
            "x-amz-checksum-sha256": checksum_base64,
            "x-amz-meta-upload-id": str(upload.id),
        }
        conditions: list[object] = [
            {"Content-Type": upload.media_type},
            {"x-amz-checksum-sha256": checksum_base64},
            {"x-amz-meta-upload-id": str(upload.id)},
            ["content-length-range", upload.size_bytes, upload.size_bytes],
        ]
        signed = self._presign_client.generate_presigned_post(
            Bucket=self._bucket,
            Key=upload.object_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires_in_seconds or self._expires_in_seconds,
        )
        return PresignedUploadTarget(
            method="POST",
            url=signed["url"],
            fields=signed["fields"],
            expires_at=upload.expires_at,
        )

    async def inspect_uploaded_object(self, upload: ImageUpload) -> StoredUploadObject | None:
        try:
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=upload.object_key,
                ChecksumMode="ENABLED",
            )
        except self._client.exceptions.ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

        checksum = self._decode_checksum(response.get("ChecksumSHA256"))
        if not checksum:
            # Alguns S3 compatíveis, incluindo versões locais do RustFS, não
            # devolvem ChecksumSHA256 no HEAD. Calcule o digest do objeto para
            # manter a mesma validação de integridade do fluxo AWS S3.
            body_response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket,
                Key=upload.object_key,
            )
            body = body_response["Body"]
            try:
                content = await asyncio.to_thread(body.read)
            finally:
                body.close()
            checksum = hashlib.sha256(content).hexdigest()
        upload_id = self._parse_uuid(response.get("Metadata", {}).get("upload-id"))
        return StoredUploadObject(
            size_bytes=int(response["ContentLength"]),
            media_type=str(response.get("ContentType", "")).lower(),
            sha256=checksum,
            upload_id=upload_id,
            uploaded_at=response["LastModified"],
        )

    async def read_uploaded_object(self, upload: ImageUpload) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=upload.object_key,
        )
        body = response["Body"]
        try:
            content = await asyncio.to_thread(body.read)
        finally:
            body.close()
        if not isinstance(content, bytes):  # pragma: no cover - contrato do SDK
            raise RuntimeError("O storage devolveu conteúdo binário inválido.")
        return content

    async def store_preview(
        self,
        upload: ImageUpload,
        content: bytes,
        media_type: str,
    ) -> StoredPreviewObject:
        object_key = (
            f"derived/{upload.tenant_id}/{upload.case_id}/{upload.image_id}/preview.png"
        )
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=object_key,
            Body=content,
            ContentType=media_type,
            CacheControl="private, max-age=300",
            Metadata={"source-upload-id": str(upload.id), "source-sha256": upload.sha256},
        )
        return StoredPreviewObject(object_key=object_key, media_type=media_type)

    def create_presigned_get(self, object_key: str, now: datetime) -> PresignedReadTarget:
        url = self._presign_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=self._expires_in_seconds,
        )
        return PresignedReadTarget(
            url=url,
            expires_at=now + timedelta(seconds=self._expires_in_seconds),
        )

    async def delete_object(self, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=object_key,
        )

    @staticmethod
    def _decode_checksum(value: object) -> str:
        if not isinstance(value, str):
            return ""
        try:
            return base64.b64decode(value, validate=True).hex()
        except (binascii.Error, ValueError):
            return ""

    @staticmethod
    def _parse_uuid(value: object) -> UUID | None:
        if not isinstance(value, str):
            return None
        try:
            return UUID(value)
        except ValueError:
            return None
