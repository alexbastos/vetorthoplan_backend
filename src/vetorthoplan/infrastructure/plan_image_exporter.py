from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageDraw


class PlanImageExporter:
    """Rasterize a plan over the source preview without modifying stored originals."""

    def render_png(
        self,
        *,
        preview_png: bytes,
        document: dict[str, Any],
        implant_previews: dict[str, bytes],
        image_dimensions_px: tuple[int, int],
    ) -> bytes:
        with Image.open(io.BytesIO(preview_png)) as source:
            image = source.convert("RGBA")

        transform = document.get("image_transform") or {}
        crop = transform.get("crop") or {"x": 0, "y": 0, "width": 1, "height": 1}
        preview_width, preview_height = image.size
        crop_box = (
            round(float(crop["x"]) * preview_width),
            round(float(crop["y"]) * preview_height),
            round((float(crop["x"]) + float(crop["width"])) * preview_width),
            round((float(crop["y"]) + float(crop["height"])) * preview_height),
        )
        crop_box = (
            crop_box[0], crop_box[1],
            min(preview_width, max(crop_box[0] + 1, crop_box[2])),
            min(preview_height, max(crop_box[1] + 1, crop_box[3])),
        )
        image = image.crop(crop_box)
        rotation = float(transform.get("rotation_degrees", 0))
        crop_width, crop_height = image.size
        radians = math.radians(rotation)
        cosine, sine = math.cos(radians), math.sin(radians)
        output_width = max(1, math.ceil(abs(crop_width * cosine) + abs(crop_height * sine)))
        output_height = max(1, math.ceil(abs(crop_height * cosine) + abs(crop_width * sine)))
        center_x = (crop_box[0] + crop_box[2]) / 2
        center_y = (crop_box[1] + crop_box[3]) / 2
        matrix = [
            [cosine, sine, output_width / 2 - cosine * center_x - sine * center_y],
            [-sine, cosine, output_height / 2 + sine * center_x - cosine * center_y],
        ]
        if rotation:
            image = image.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)

        draw = ImageDraw.Draw(image, "RGBA")
        width, height = preview_width, preview_height
        original_width, original_height = image_dimensions_px
        for item in document.get("objects", []):
            if not isinstance(item, dict) or item.get("visible", True) is False:
                continue
            kind = item.get("type")
            if kind == "IMPLANT":
                self._draw_implant(image, item, implant_previews, matrix, width, height)
            elif kind == "LINE":
                self._line(draw, item.get("start"), item.get("end"), matrix, width, height)
            elif kind == "ANGLE":
                self._line(draw, item.get("start"), item.get("vertex"), matrix, width, height)
                self._line(draw, item.get("vertex"), item.get("end"), matrix, width, height)
            elif kind in {"CIRCLE", "TPLO"}:
                self._circle(draw, item.get("center"), item.get("edge"), matrix, width, height)
                fragment = item.get("fragment") or {}
                points = fragment.get("points") or []
                if kind == "TPLO" and len(points) >= 3:
                    simulation = item.get("simulation") or {}
                    transformed = simulation.get("transformed_fragment_points_px") or []
                    polygon = [
                        self._map_pixel(
                            point["x"] * width / original_width,
                            point["y"] * height / original_height,
                            matrix,
                        )
                        for point in transformed
                    ] if transformed else [
                        self._map(point, matrix, width, height) for point in points
                    ]
                    draw.line(polygon + [polygon[0]], fill=(220, 38, 38, 230), width=3)

        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _map_pixel(x: float, y: float, matrix: list[list[float]]) -> tuple[float, float]:
        return (
            matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
            matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
        )

    @classmethod
    def _map(
        cls,
        point: dict[str, float],
        matrix: list[list[float]],
        width: int,
        height: int,
    ) -> tuple[float, float]:
        return cls._map_pixel(point["x"] * width, point["y"] * height, matrix)

    @classmethod
    def _line(
        cls,
        draw: ImageDraw.ImageDraw,
        start: object,
        end: object,
        matrix: list[list[float]],
        width: int,
        height: int,
    ) -> None:
        if isinstance(start, dict) and isinstance(end, dict):
            draw.line(
                [cls._map(start, matrix, width, height), cls._map(end, matrix, width, height)],
                fill=(220, 38, 38, 230),
                width=3,
            )

    @classmethod
    def _circle(
        cls,
        draw: ImageDraw.ImageDraw,
        center: object,
        edge: object,
        matrix: list[list[float]],
        width: int,
        height: int,
    ) -> None:
        if not isinstance(center, dict) or not isinstance(edge, dict):
            return
        cx, cy = cls._map(center, matrix, width, height)
        ex, ey = cls._map(edge, matrix, width, height)
        radius = math.hypot(ex - cx, ey - cy)
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            outline=(37, 99, 235, 230),
            width=3,
        )

    @classmethod
    def _draw_implant(
        cls,
        canvas: Image.Image,
        item: dict[str, Any],
        implant_previews: dict[str, bytes],
        matrix: list[list[float]],
        width: int,
        height: int,
    ) -> None:
        asset_bytes = implant_previews.get(str(item.get("catalog_item_id")))
        position = item.get("position")
        if asset_bytes is None or not isinstance(position, dict):
            return
        with Image.open(io.BytesIO(asset_bytes)) as source:
            asset = source.convert("RGBA")
        scale = float(item.get("scale", 1))
        size = (max(1, round(asset.width * scale)), max(1, round(asset.height * scale)))
        asset = asset.resize(size, Image.Resampling.LANCZOS)
        global_rotation = math.degrees(math.atan2(-matrix[1][0], matrix[0][0]))
        asset = asset.rotate(
            -(float(item.get("rotation_degrees", 0)) + global_rotation),
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        opacity = max(0.0, min(1.0, float(item.get("opacity", 1))))
        alpha = asset.getchannel("A").point(lambda value: round(value * opacity))
        asset.putalpha(alpha)
        center_x, center_y = cls._map(position, matrix, width, height)
        canvas.alpha_composite(
            asset,
            dest=(round(center_x - asset.width / 2), round(center_y - asset.height / 2)),
        )
