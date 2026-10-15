from dataclasses import dataclass
from typing import Protocol

from vetorthoplan.domain.imaging import ImageKind


@dataclass(frozen=True, slots=True)
class InspectedImageContent:
    kind: ImageKind
    media_type: str
    width_px: int | None
    height_px: int | None
    metadata: dict[str, str]
    preview_content: bytes
    preview_media_type: str
    preview_width_px: int
    preview_height_px: int


class ImageContentInspector(Protocol):
    def inspect(
        self,
        content: bytes,
        *,
        expected_kind: ImageKind,
        expected_sha256: str,
    ) -> InspectedImageContent: ...
