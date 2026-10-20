import hashlib
import io
import struct

import pytest
from PIL import Image

from vetorthoplan.application.errors import ImageContentRejectedError
from vetorthoplan.domain.imaging import ImageKind
from vetorthoplan.infrastructure.image_content import BasicImageContentInspector


def png_content(*, width: int = 640, height: int = 480) -> bytes:
    output = io.BytesIO()
    Image.new("L", (width, height), color=127).save(output, format="PNG")
    return output.getvalue()


def explicit_element(group: int, element: int, vr: bytes, value: bytes) -> bytes:
    if len(value) % 2:
        value += b"\x00"
    if vr in {b"OB", b"OW"}:
        return struct.pack("<HH2sHI", group, element, vr, 0, len(value)) + value
    return struct.pack("<HH2sH", group, element, vr, len(value)) + value


def dicom_content() -> bytes:
    pixels = bytes([0, 64, 128, 255])
    return (
        bytes(128)
        + b"DICM"
        + explicit_element(0x0002, 0x0010, b"UI", b"1.2.840.10008.1.2.1\x00")
        + explicit_element(0x0008, 0x0060, b"CS", b"DX")
        + explicit_element(0x0028, 0x0002, b"US", struct.pack("<H", 1))
        + explicit_element(0x0028, 0x0004, b"CS", b"MONOCHROME2")
        + explicit_element(0x0020, 0x0037, b"DS", b"1\\0\\0\\0\\1\\0")
        + explicit_element(0x0018, 0x1164, b"DS", b"0.14\\0.14")
        + explicit_element(0x0028, 0x0010, b"US", struct.pack("<H", 2))
        + explicit_element(0x0028, 0x0011, b"US", struct.pack("<H", 2))
        + explicit_element(0x0028, 0x0030, b"DS", b"0.15\\0.16")
        + explicit_element(0x0028, 0x0100, b"US", struct.pack("<H", 8))
        + explicit_element(0x0028, 0x0101, b"US", struct.pack("<H", 8))
        + explicit_element(0x0028, 0x0103, b"US", struct.pack("<H", 0))
        + explicit_element(0x7FE0, 0x0010, b"OB", pixels)
    )


def test_inspector_detects_png_dimensions_and_generates_preview() -> None:
    content = png_content()
    inspected = BasicImageContentInspector().inspect(
        content,
        expected_kind=ImageKind.PNG,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )
    assert inspected.kind == ImageKind.PNG
    assert (inspected.width_px, inspected.height_px) == (640, 480)
    assert inspected.preview_content.startswith(b"\x89PNG")


def test_inspector_parses_uncompressed_dicom_and_generates_preview() -> None:
    content = dicom_content()
    inspected = BasicImageContentInspector().inspect(
        content,
        expected_kind=ImageKind.DICOM,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )
    assert inspected.media_type == "application/dicom"
    assert (inspected.width_px, inspected.height_px) == (2, 2)
    assert inspected.metadata["modality"] == "DX"
    assert inspected.metadata["pixel_spacing"] == "0.15\\0.16"
    assert inspected.metadata["imager_pixel_spacing"] == "0.14\\0.14"
    assert inspected.metadata["image_orientation_patient"] == "1\\0\\0\\0\\1\\0"
    assert inspected.preview_content.startswith(b"\x89PNG")


def test_inspector_rejects_declared_format_mismatch() -> None:
    content = png_content()
    with pytest.raises(ImageContentRejectedError) as error:
        BasicImageContentInspector().inspect(
            content,
            expected_kind=ImageKind.JPEG,
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )
    assert error.value.code == "format_mismatch"


def test_inspector_rejects_checksum_mismatch() -> None:
    with pytest.raises(ImageContentRejectedError) as error:
        BasicImageContentInspector().inspect(
            png_content(),
            expected_kind=ImageKind.PNG,
            expected_sha256="0" * 64,
        )
    assert error.value.code == "checksum_mismatch"
