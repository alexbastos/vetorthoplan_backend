from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from vetorthoplan.application.errors import ImageContentRejectedError
from vetorthoplan.application.ports import InspectedImageContent
from vetorthoplan.domain.imaging import ImageKind

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_DIMENSION = 65_535
MAX_IMAGE_PIXELS = 100_000_000
PREVIEW_MAX_DIMENSION = 1_600
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
SUPPORTED_TRANSFER_SYNTAXES = {EXPLICIT_VR_LITTLE_ENDIAN, IMPLICIT_VR_LITTLE_ENDIAN}
LONG_VALUE_REPRESENTATIONS = {
    b"OB", b"OD", b"OF", b"OL", b"OV", b"OW", b"SQ", b"UC", b"UN", b"UR", b"UT"
}


@dataclass(frozen=True, slots=True)
class _DicomDataset:
    columns: int
    rows: int
    bits_allocated: int
    bits_stored: int
    pixel_representation: int
    photometric_interpretation: str
    pixel_data: bytes
    transfer_syntax_uid: str
    metadata: dict[str, str]
    window_center: float | None
    window_width: float | None
    rescale_intercept: float
    rescale_slope: float


class BasicImageContentInspector:
    """Valida o original e produz uma prévia PNG segura para uso no navegador."""

    def inspect(
        self,
        content: bytes,
        *,
        expected_kind: ImageKind,
        expected_sha256: str,
    ) -> InspectedImageContent:
        if not content:
            raise ImageContentRejectedError("empty_content", "O arquivo está vazio.")
        if hashlib.sha256(content).hexdigest() != expected_sha256.lower():
            raise ImageContentRejectedError(
                "checksum_mismatch", "O conteúdo não corresponde ao checksum confirmado."
            )

        detected_kind = self._detect_kind(content)
        if detected_kind is None or detected_kind != expected_kind:
            raise ImageContentRejectedError(
                "format_mismatch", "O formato real do arquivo não corresponde ao formato declarado."
            )

        if detected_kind == ImageKind.DICOM:
            dataset = self._parse_dicom(content)
            width, height = dataset.columns, dataset.rows
            source = self._render_dicom(dataset)
            media_type = "application/dicom"
            metadata = dataset.metadata
        else:
            source = self._decode_raster(content)
            width, height = source.size
            media_type = "image/png" if detected_kind == ImageKind.PNG else "image/jpeg"
            metadata = {}

        self._validate_dimensions(width, height)
        preview_content, preview_width, preview_height = self._create_preview(source)
        return InspectedImageContent(
            kind=detected_kind,
            media_type=media_type,
            width_px=width,
            height_px=height,
            metadata=metadata,
            preview_content=preview_content,
            preview_media_type="image/png",
            preview_width_px=preview_width,
            preview_height_px=preview_height,
        )

    @staticmethod
    def _detect_kind(content: bytes) -> ImageKind | None:
        if content.startswith(PNG_SIGNATURE):
            return ImageKind.PNG
        if content.startswith(b"\xff\xd8"):
            return ImageKind.JPEG
        if len(content) >= 132 and content[128:132] == b"DICM":
            return ImageKind.DICOM
        return None

    @staticmethod
    def _decode_raster(content: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(content))
            image.load()
            return ImageOps.exif_transpose(image).convert("L")
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageContentRejectedError(
                "malformed_image", "A imagem não pôde ser decodificada."
            ) from exc

    @staticmethod
    def _validate_dimensions(width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ImageContentRejectedError("malformed_image", "A imagem possui dimensões inválidas.")
        if (
            width > MAX_IMAGE_DIMENSION
            or height > MAX_IMAGE_DIMENSION
            or width * height > MAX_IMAGE_PIXELS
        ):
            raise ImageContentRejectedError(
                "dimensions_exceeded", "As dimensões da imagem excedem o limite permitido."
            )

    @staticmethod
    def _create_preview(source: Image.Image) -> tuple[bytes, int, int]:
        preview = source.copy()
        preview.thumbnail((PREVIEW_MAX_DIMENSION, PREVIEW_MAX_DIMENSION), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        preview.save(output, format="PNG", optimize=True)
        return output.getvalue(), preview.width, preview.height

    def _parse_dicom(self, content: bytes) -> _DicomDataset:
        position = 132
        transfer_syntax_uid = ""
        while position + 8 <= len(content):
            group, element = struct.unpack_from("<HH", content, position)
            if group != 0x0002:
                break
            value, position = self._read_element(content, position, explicit_vr=True)
            if element == 0x0010:
                transfer_syntax_uid = self._decode_text(value)

        if transfer_syntax_uid not in SUPPORTED_TRANSFER_SYNTAXES:
            raise ImageContentRejectedError(
                "unsupported_transfer_syntax",
                "A sintaxe de transferência DICOM não é suportada neste recorte.",
            )

        explicit_vr = transfer_syntax_uid == EXPLICIT_VR_LITTLE_ENDIAN
        values: dict[tuple[int, int], bytes] = {}
        wanted_tags = {
            (0x0008, 0x0020), (0x0008, 0x0060), (0x0018, 0x0015), (0x0020, 0x0060),
            (0x0028, 0x0002), (0x0028, 0x0004), (0x0028, 0x0008), (0x0028, 0x0010),
            (0x0020, 0x0037), (0x0028, 0x0011), (0x0028, 0x0030),
            (0x0018, 0x1164), (0x0028, 0x0100), (0x0028, 0x0101), (0x0028, 0x0103),
            (0x0028, 0x1050), (0x0028, 0x1051), (0x0028, 0x1052), (0x0028, 0x1053),
            (0x7FE0, 0x0010),
        }
        while position + 8 <= len(content):
            group, element = struct.unpack_from("<HH", content, position)
            value, position = self._read_element(content, position, explicit_vr=explicit_vr)
            tag = (group, element)
            if tag in wanted_tags:
                values[tag] = value
            if tag == (0x7FE0, 0x0010):
                break

        rows = self._read_unsigned_short(values, (0x0028, 0x0010), "Rows")
        columns = self._read_unsigned_short(values, (0x0028, 0x0011), "Columns")
        bits_allocated = self._read_unsigned_short(values, (0x0028, 0x0100), "Bits Allocated")
        bits_stored = self._read_unsigned_short(values, (0x0028, 0x0101), "Bits Stored")
        pixel_representation = self._read_unsigned_short(
            values, (0x0028, 0x0103), "Pixel Representation"
        )
        samples_per_pixel = self._read_unsigned_short(values, (0x0028, 0x0002), "Samples per Pixel")
        frames = self._read_int_text(values.get((0x0028, 0x0008)), default=1)
        photometric = self._decode_text(values.get((0x0028, 0x0004), b""))
        pixel_data = values.get((0x7FE0, 0x0010), b"")

        if samples_per_pixel != 1 or frames != 1 or photometric not in {"MONOCHROME1", "MONOCHROME2"}:
            raise ImageContentRejectedError(
                "unsupported_dicom_pixels",
                "A prévia suporta somente imagens DICOM monocromáticas de quadro único.",
            )
        if bits_allocated not in {8, 16} or not 1 <= bits_stored <= bits_allocated:
            raise ImageContentRejectedError(
                "unsupported_dicom_pixels", "A profundidade DICOM não é suportada."
            )
        expected_bytes = rows * columns * (bits_allocated // 8)
        if len(pixel_data) < expected_bytes:
            raise ImageContentRejectedError("malformed_dicom", "O Pixel Data DICOM está incompleto.")

        metadata = {
            "transfer_syntax_uid": transfer_syntax_uid,
            "photometric_interpretation": photometric,
            "bits_allocated": str(bits_allocated),
            "bits_stored": str(bits_stored),
        }
        for key, tag in {
            "study_date": (0x0008, 0x0020),
            "modality": (0x0008, 0x0060),
            "body_part_examined": (0x0018, 0x0015),
            "laterality": (0x0020, 0x0060),
            "pixel_spacing": (0x0028, 0x0030),
            "imager_pixel_spacing": (0x0018, 0x1164),
            "image_orientation_patient": (0x0020, 0x0037),
        }.items():
            value = self._decode_text(values.get(tag, b""))
            if value:
                metadata[key] = value[:128]

        return _DicomDataset(
            columns=columns,
            rows=rows,
            bits_allocated=bits_allocated,
            bits_stored=bits_stored,
            pixel_representation=pixel_representation,
            photometric_interpretation=photometric,
            pixel_data=pixel_data[:expected_bytes],
            transfer_syntax_uid=transfer_syntax_uid,
            metadata=metadata,
            window_center=self._read_float_text(values.get((0x0028, 0x1050))),
            window_width=self._read_float_text(values.get((0x0028, 0x1051))),
            rescale_intercept=self._read_float_text(values.get((0x0028, 0x1052)), default=0.0) or 0.0,
            rescale_slope=self._read_float_text(values.get((0x0028, 0x1053)), default=1.0) or 1.0,
        )

    @staticmethod
    def _read_element(content: bytes, position: int, *, explicit_vr: bool) -> tuple[bytes, int]:
        if position + 8 > len(content):
            raise ImageContentRejectedError("malformed_dicom", "Elemento DICOM truncado.")
        if explicit_vr:
            vr = content[position + 4 : position + 6]
            if vr in LONG_VALUE_REPRESENTATIONS:
                if position + 12 > len(content):
                    raise ImageContentRejectedError("malformed_dicom", "Elemento DICOM truncado.")
                length = struct.unpack_from("<I", content, position + 8)[0]
                value_start = position + 12
            else:
                length = struct.unpack_from("<H", content, position + 6)[0]
                value_start = position + 8
        else:
            length = struct.unpack_from("<I", content, position + 4)[0]
            value_start = position + 8
        if length == 0xFFFFFFFF or value_start + length > len(content):
            raise ImageContentRejectedError(
                "unsupported_dicom_structure",
                "O DICOM contém sequência indefinida ou truncada não suportada.",
            )
        return content[value_start : value_start + length], value_start + length

    @staticmethod
    def _read_unsigned_short(
        values: dict[tuple[int, int], bytes], tag: tuple[int, int], name: str
    ) -> int:
        value = values.get(tag)
        if value is None or len(value) < 2:
            raise ImageContentRejectedError("malformed_dicom", f"O DICOM não informa {name}.")
        return struct.unpack_from("<H", value)[0]

    @staticmethod
    def _decode_text(value: bytes) -> str:
        return value.decode("ascii", errors="ignore").strip(" \x00")

    @classmethod
    def _read_float_text(cls, value: bytes | None, default: float | None = None) -> float | None:
        if not value:
            return default
        try:
            return float(cls._decode_text(value).split("\\", 1)[0])
        except ValueError:
            return default

    @classmethod
    def _read_int_text(cls, value: bytes | None, default: int) -> int:
        if not value:
            return default
        try:
            return int(cls._decode_text(value).split("\\", 1)[0])
        except ValueError:
            return default

    @staticmethod
    def _render_dicom(dataset: _DicomDataset) -> Image.Image:
        if dataset.bits_allocated == 16:
            dtype = np.dtype("<i2" if dataset.pixel_representation else "<u2")
        else:
            dtype = np.dtype("i1" if dataset.pixel_representation else "u1")
        pixels = np.frombuffer(dataset.pixel_data, dtype=dtype).reshape(
            dataset.rows, dataset.columns
        ).astype(np.float32)
        pixels = pixels * dataset.rescale_slope + dataset.rescale_intercept
        if (
            dataset.window_center is not None
            and dataset.window_width is not None
            and dataset.window_width > 1
        ):
            lower = dataset.window_center - dataset.window_width / 2
            upper = dataset.window_center + dataset.window_width / 2
        else:
            lower, upper = np.percentile(pixels, (1.0, 99.0))
        if upper <= lower:
            upper = lower + 1.0
        normalized = np.clip((pixels - lower) * (255.0 / (upper - lower)), 0, 255).astype(np.uint8)
        if dataset.photometric_interpretation == "MONOCHROME1":
            normalized = 255 - normalized
        return Image.fromarray(normalized)
