from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.config.settings import Settings
from vetorthoplan.infrastructure.database.models import ImplantCatalogImportModel
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage

MAX_EDITABLE_ASSET_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_BYTES = 20 * 1024 * 1024
logger = logging.getLogger("vetorthoplan.implant_catalog_conversion")


async def process_next_catalog_conversion(
    session: AsyncSession, *, settings: Settings, storage: S3PresignedPostStorage
) -> bool:
    service_url = settings.implant_catalog_conversion_service_url or settings.oda_conversion_service_url
    service_token = settings.implant_catalog_conversion_service_token or settings.oda_conversion_service_token
    timeout = (
        settings.implant_catalog_conversion_timeout_seconds
        if settings.implant_catalog_conversion_service_url
        else settings.oda_conversion_timeout_seconds
    )
    if not service_url:
        return False
    row = await session.scalar(
        select(ImplantCatalogImportModel)
        .where(
            ImplantCatalogImportModel.status.in_(["QUEUED", "WAITING_FOR_CONVERTER"]),
            ImplantCatalogImportModel.source_object_key.is_not(None),
        )
        .order_by(ImplantCatalogImportModel.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return False

    row.status = "PROCESSING"
    await session.flush()
    try:
        source = await storage.read_object(row.source_object_key)
        digest = hashlib.sha256(source).hexdigest()
        if (
            len(source) != row.source_size_bytes
            or digest != row.source_sha256
        ):
            raise ValueError("SOURCE_INTEGRITY_CHECK_FAILED")
        headers = {
            "Content-Type": row.source_media_type or (
                "application/acad" if settings.oda_conversion_service_url else "application/octet-stream"
            ),
            "X-Source-SHA256": digest,
            "X-Original-Filename": row.original_filename or "implant-source",
        }
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(service_url, content=source, headers=headers)
            response.raise_for_status()
        result = response.json()
        # Accept the legacy converter response while the selected source format and
        # canonical editing representation are being finalized.
        asset_value = result.get("editable_asset_base64", result.get("svg_base64"))
        asset = _decode_result(asset_value, MAX_EDITABLE_ASSET_BYTES, "EDITABLE_ASSET_INVALID")
        asset_media_type = result.get("editable_asset_media_type", "image/svg+xml")
        if not isinstance(asset_media_type, str) or "/" not in asset_media_type or len(asset_media_type) > 160:
            raise ValueError("EDITABLE_ASSET_MEDIA_TYPE_INVALID")
        preview = _decode_result(
            result.get("preview_png_base64"), MAX_PREVIEW_BYTES, "PREVIEW_OUTPUT_INVALID"
        )
        if asset_media_type.lower() == "image/svg+xml":
            _validate_svg(asset)
        if not preview.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PREVIEW_OUTPUT_INVALID")
        converter_version = result.get("converter_version")
        if not isinstance(converter_version, str) or not converter_version.strip():
            raise ValueError("CONVERTER_VERSION_MISSING")
        conversion_metadata = result.get("drawing_metadata", {})
        if not isinstance(conversion_metadata, dict):
            raise ValueError("CONVERSION_METADATA_INVALID")
        extension = "svg" if asset_media_type.lower() == "image/svg+xml" else "asset"
        asset_key = f"implant-catalog/derived/{row.id}/{digest}.{extension}"
        preview_key = f"implant-catalog/derived/{row.id}/{digest}-preview.png"
        await storage.store_object(asset_key, asset, asset_media_type, metadata={"source-sha256": digest})
        await storage.store_object(preview_key, preview, "image/png", metadata={"source-sha256": digest})
        row.editable_asset_object_key = asset_key
        row.editable_asset_media_type = asset_media_type.lower()
        row.svg_object_key = asset_key if asset_media_type.lower() == "image/svg+xml" else None
        row.preview_object_key = preview_key
        row.converter_version = converter_version[:100]
        row.conversion_metadata = conversion_metadata
        row.status = "REVIEW_REQUIRED"
        row.error_code = None
    except Exception:
        logger.exception("Falha ao converter importação de prótese %s", row.id)
        row.status = "FAILED"
        row.error_code = "CATALOG_CONVERSION_FAILED"
    await session.flush()
    return True


def _decode_result(value: object, max_bytes: int, error: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(error)
    try:
        content = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(error) from exc
    if not content or len(content) > max_bytes:
        raise ValueError(error)
    return content


def _validate_svg(content: bytes) -> None:
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("SVG_OUTPUT_INVALID")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("SVG_OUTPUT_INVALID") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError("SVG_OUTPUT_INVALID")
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() in {"script", "foreignobject", "iframe", "object"}:
            raise ValueError("SVG_OUTPUT_INVALID")
        for name, value in element.attrib.items():
            local_name = name.rsplit("}", 1)[-1].lower()
            normalized = value.strip().lower()
            if local_name.startswith("on") or (
                local_name in {"href", "src"} and normalized and not normalized.startswith("#")
            ):
                raise ValueError("SVG_OUTPUT_INVALID")
