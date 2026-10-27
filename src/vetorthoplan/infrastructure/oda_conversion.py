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

MAX_SVG_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_BYTES = 20 * 1024 * 1024
logger = logging.getLogger("vetorthoplan.oda_conversion")


async def process_next_oda_conversion(
    session: AsyncSession, *, settings: Settings, storage: S3PresignedPostStorage
) -> bool:
    if not settings.oda_conversion_service_url:
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
            or not source.startswith(b"AC10")
        ):
            raise ValueError("SOURCE_INTEGRITY_CHECK_FAILED")
        headers = {"Content-Type": "application/acad", "X-Source-SHA256": digest}
        if settings.oda_conversion_service_token:
            headers["Authorization"] = f"Bearer {settings.oda_conversion_service_token}"
        async with httpx.AsyncClient(timeout=settings.oda_conversion_timeout_seconds) as client:
            response = await client.post(settings.oda_conversion_service_url, content=source, headers=headers)
            response.raise_for_status()
        result = response.json()
        svg = _decode_result(result.get("svg_base64"), MAX_SVG_BYTES, "SVG_OUTPUT_INVALID")
        preview = _decode_result(
            result.get("preview_png_base64"), MAX_PREVIEW_BYTES, "PREVIEW_OUTPUT_INVALID"
        )
        _validate_svg(svg)
        if not preview.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PREVIEW_OUTPUT_INVALID")
        converter_version = result.get("converter_version")
        if not isinstance(converter_version, str) or not converter_version.strip():
            raise ValueError("CONVERTER_VERSION_MISSING")
        conversion_metadata = result.get("drawing_metadata", {})
        if not isinstance(conversion_metadata, dict):
            raise ValueError("CONVERSION_METADATA_INVALID")
        svg_key = f"implant-catalog/derived/{row.id}/{digest}.svg"
        preview_key = f"implant-catalog/derived/{row.id}/{digest}-preview.png"
        await storage.store_object(svg_key, svg, "image/svg+xml", metadata={"source-sha256": digest})
        await storage.store_object(preview_key, preview, "image/png", metadata={"source-sha256": digest})
        row.svg_object_key = svg_key
        row.preview_object_key = preview_key
        row.converter_version = converter_version[:100]
        row.conversion_metadata = conversion_metadata
        row.status = "REVIEW_REQUIRED"
        row.error_code = None
    except Exception:
        logger.exception("Falha ao converter importação de prótese %s", row.id)
        row.status = "FAILED"
        row.error_code = "ODA_CONVERSION_FAILED"
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
