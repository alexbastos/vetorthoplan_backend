from __future__ import annotations

import io
import math
import unicodedata
from typing import Any
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont, ImageOps

from vetorthoplan.application.ports.plan_report_renderer import (
    REPORT_TEMPLATE_VERSION,
    RenderedPlanReports,
)

PAGE_SIZE = (1600, 2200)
IMAGE_BOX = (1480, 1240)


class TploPlanReportRenderer:
    def render(
        self,
        *,
        preview_png: bytes,
        snapshot: dict[str, Any],
        case_id: UUID,
        image_id: UUID,
        plan_revision: int,
        finalization_version: int,
        finalized_by: UUID,
        finalized_at: str,
    ) -> RenderedPlanReports:
        page = Image.new("RGB", PAGE_SIZE, "white")
        draw = ImageDraw.Draw(page)
        font = ImageFont.load_default(size=26)
        small_font = ImageFont.load_default(size=20)
        title_font = ImageFont.load_default(size=38)

        self._text(draw, (64, 48), "VETORTHOPLAN - FINAL SURGICAL PLAN", font=title_font)
        self._text(
            draw,
            (64, 112),
            (f"Report version: {finalization_version}  |  Template: {REPORT_TEMPLATE_VERSION}"),
            font=font,
        )
        self._text(draw, (64, 156), f"Case: {case_id}  |  Image: {image_id}", font=small_font)
        self._text(
            draw,
            (64, 190),
            f"Plan revision: {plan_revision}  |  Finalized at: {finalized_at}",
            font=small_font,
        )
        self._text(draw, (64, 224), f"Finalized by: {finalized_by}", font=small_font)

        with Image.open(io.BytesIO(preview_png)) as source:
            preview = ImageOps.contain(source.convert("RGB"), IMAGE_BOX)
        self._draw_plan_geometry(preview, snapshot)
        image_x = (PAGE_SIZE[0] - preview.width) // 2
        image_y = 280 + (IMAGE_BOX[1] - preview.height) // 2
        page.paste(preview, (image_x, image_y))
        draw.rectangle(
            (image_x - 1, image_y - 1, image_x + preview.width, image_y + preview.height),
            outline="#9ca3af",
            width=2,
        )

        self._draw_measurements(draw, snapshot, top=1580, font=font, small_font=small_font)
        png_stream = io.BytesIO()
        page.save(png_stream, format="PNG", optimize=True)
        pdf_stream = io.BytesIO()
        detail_pages = self._detail_pages(snapshot)
        page.save(
            pdf_stream,
            format="PDF",
            resolution=150.0,
            save_all=True,
            append_images=detail_pages,
        )
        return RenderedPlanReports(png=png_stream.getvalue(), pdf=pdf_stream.getvalue())

    @staticmethod
    def _detail_pages(snapshot: dict[str, Any]) -> list[Image.Image]:
        rows: list[str] = []
        correction = snapshot.get("tplo_correction") or {}
        rows.append("TPLO calculations are not clinically validated.")
        rows.append(
            f"Correction: {correction.get('status', 'not calculated')}; "
            f"pre-op TPA={correction.get('preoperative_tpa_degrees')} degrees"
        )
        rows.append(
            f"Current slope={correction.get('current_slope_degrees')} degrees; "
            f"target={correction.get('target_slope_degrees')} degrees; "
            f"blade={correction.get('blade_diameter_mm')} mm"
        )
        rows.append(
            f"Rotation={correction.get('rotation_mm')} mm; "
            f"acceptance={correction.get('acceptance', 'NOT_ASSESSED')}"
        )
        rows.append(
            f"Rotation table: {correction.get('table_version', 'not recorded')}; "
            f"source={correction.get('table_source', 'not recorded')}"
        )
        rows.append(f"Rotation table SHA-256: {correction.get('table_entries_sha256', 'not recorded')}")
        for item in snapshot.get("additional_measurements", []):
            if isinstance(item, dict):
                rows.append(
                    f"{item.get('id')}: value={item.get('value')} {item.get('unit')}; "
                    f"reference={item.get('reference_value')}; error={item.get('absolute_error')}; "
                    f"max error={item.get('max_absolute_error')}; acceptance={item.get('acceptance')}"
                )
        for index, item in enumerate(snapshot.get("objects", []), start=1):
            if isinstance(item, dict) and item.get("type") == "LINE":
                values = (item.get("measurement") or {}).get("values") or {}
                rows.append(f"Line object {index}: length={values.get('length')} mm")
            elif isinstance(item, dict) and item.get("type") == "ANGLE":
                values = (item.get("measurement") or {}).get("values") or {}
                rows.append(f"Angle object {index}: angle={values.get('angle')} degrees")
            elif isinstance(item, dict) and item.get("type") == "CIRCLE":
                values = (item.get("measurement") or {}).get("values") or {}
                rows.append(
                    f"Circle object {index}: radius={values.get('radius')} mm; "
                    f"diameter={values.get('diameter')} mm; circumference={values.get('circumference')} mm"
                )
            elif isinstance(item, dict) and item.get("type") == "TPLO":
                measurement = item.get("measurement") or {}
                values = measurement.get("values") or {}
                rows.append(
                    f"TPLO object {index}: radius={values.get('radius')} mm; "
                    f"rotation={values.get('rotation')} degrees"
                )
            elif isinstance(item, dict) and item.get("type") == "IMPLANT":
                position = item.get("position") or {}
                rows.append(
                    f"Implant object {index}: catalog_item={item.get('catalog_item_id')}; "
                    f"position=({position.get('x')}, {position.get('y')}); "
                    f"rotation={item.get('rotation_degrees')} degrees; scale={item.get('scale')}; "
                    f"opacity={item.get('opacity')}; variant={item.get('variant')}; view={item.get('view')}"
                )
        validation = snapshot.get("clinical_validation") or {}
        rows.append(f"Clinical review status: {validation.get('status', 'not recorded')}")
        for event in validation.get("audit", []):
            if isinstance(event, dict):
                rows.append(
                    f"Review audit: {event.get('decision')} by {event.get('actor_id')} "
                    f"at {event.get('reviewed_at')}; protocol={event.get('protocol_version')}"
                )

        chunks = [rows[index : index + 34] for index in range(0, len(rows), 34)] or [[]]
        pages: list[Image.Image] = []
        for page_number, chunk in enumerate(chunks, start=2):
            page = Image.new("RGB", PAGE_SIZE, "white")
            draw = ImageDraw.Draw(page)
            title_font = ImageFont.load_default(size=38)
            font = ImageFont.load_default(size=22)
            TploPlanReportRenderer._text(
                draw,
                (64, 56),
                f"PLAN DETAILS - PAGE {page_number}",
                font=title_font,
            )
            for index, row in enumerate(chunk):
                TploPlanReportRenderer._text(draw, (64, 140 + index * 56), row, font=font)
            pages.append(page)
        return pages

    @classmethod
    def _draw_plan_geometry(cls, image: Image.Image, snapshot: dict[str, Any]) -> None:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=18)
        landmarks = snapshot.get("tplo_landmarks") or {}
        point_index = 0
        for point in landmarks.values():
            if isinstance(point, dict):
                point_index += 1
                cls._draw_point(draw, point, image.size, f"P{point_index}", font)

        additional = snapshot.get("additional_measurements_input") or {}
        named_points = additional.get("landmarks") or {}
        for index, point in enumerate(named_points.values(), start=1):
            cls._draw_point(draw, point, image.size, f"A{index}", font)

        for item in snapshot.get("objects", []):
            if not isinstance(item, dict):
                continue
            if item.get("visible", True) is False:
                continue
            kind = item.get("type")
            if kind == "LINE":
                cls._draw_segment(draw, item.get("start"), item.get("end"), image.size)
            elif kind == "ANGLE":
                vertex = item.get("vertex")
                cls._draw_segment(draw, item.get("start"), vertex, image.size)
                cls._draw_segment(draw, vertex, item.get("end"), image.size)
            elif kind in {"CIRCLE", "TPLO"}:
                center, edge = item.get("center"), item.get("edge")
                cls._draw_segment(draw, center, edge, image.size)
                if center and edge:
                    cx, cy = cls._pixel_point(center, image.size)
                    ex, ey = cls._pixel_point(edge, image.size)
                    radius = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
                    draw.ellipse(
                        (cx - radius, cy - radius, cx + radius, cy + radius),
                        outline="#2563eb",
                        width=3,
                    )
                fragment = item.get("fragment") or {}
                points = fragment.get("points") or []
                if len(points) > 2:
                    if (item.get("simulation") or {}).get("status") == "SIMULATED":
                        center_x, center_y = cls._pixel_point(item["center"], image.size)
                        radians = math.radians(float(item.get("rotation_degrees", 0)))
                        cosine, sine = math.cos(radians), math.sin(radians)
                        polygon = []
                        for point in points:
                            source_x, source_y = cls._pixel_point(point, image.size)
                            dx, dy = source_x - center_x, source_y - center_y
                            polygon.append(
                                (
                                    int(center_x + cosine * dx - sine * dy),
                                    int(center_y + sine * dx + cosine * dy),
                                )
                            )
                    else:
                        polygon = [cls._pixel_point(point, image.size) for point in points]
                    draw.line(polygon + [polygon[0]], fill="#dc2626", width=3)
            elif kind == "IMPLANT":
                position = item.get("position")
                if isinstance(position, dict):
                    x, y = cls._pixel_point(position, image.size)
                    opacity = max(0.2, min(1.0, float(item.get("opacity", 1))))
                    color = (29, 78, 216, round(opacity * 255))
                    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
                    implant_draw = ImageDraw.Draw(overlay)
                    radians = float(item.get("rotation_degrees", 0)) * 3.141592653589793 / 180
                    dx, dy = 28 * math.cos(radians), 28 * math.sin(radians)
                    implant_draw.line((x - dx, y - dy, x + dx, y + dy), fill=color, width=7)
                    implant_draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color)
                    image.paste(overlay, (0, 0), overlay)

    @classmethod
    def _draw_point(
        cls,
        draw: ImageDraw.ImageDraw,
        point: object,
        size: tuple[int, int],
        label: str,
        font: ImageFont.ImageFont,
    ) -> None:
        if not isinstance(point, dict):
            return
        x, y = cls._pixel_point(point, size)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#dc2626", outline="white", width=2)
        draw.text((x + 9, y + 4), label, fill="#111827", font=font)

    @classmethod
    def _draw_segment(
        cls,
        draw: ImageDraw.ImageDraw,
        start: object,
        end: object,
        size: tuple[int, int],
    ) -> None:
        if isinstance(start, dict) and isinstance(end, dict):
            draw.line(
                [cls._pixel_point(start, size), cls._pixel_point(end, size)],
                fill="#dc2626",
                width=3,
            )

    @staticmethod
    def _pixel_point(point: dict[str, Any], size: tuple[int, int]) -> tuple[float, float]:
        return float(point["x"]) * size[0], float(point["y"]) * size[1]

    @classmethod
    def _draw_measurements(
        cls,
        draw: ImageDraw.ImageDraw,
        snapshot: dict[str, Any],
        *,
        top: int,
        font: ImageFont.ImageFont,
        small_font: ImageFont.ImageFont,
    ) -> None:
        tplo = snapshot.get("tplo") or {}
        validation = snapshot.get("clinical_validation") or {}
        measurement = snapshot.get("tplo_measurement") or {}
        correction = snapshot.get("tplo_correction") or {}
        quality = snapshot.get("radiographic_quality") or {}
        calibration = snapshot.get("calibration") or {}
        calibration_result = calibration.get("result") or {}
        rows = [
            "TPLO calculation validation: NOT CLINICALLY VALIDATED",
            (
                f"Laterality: {tplo.get('laterality', 'not recorded')}  |  "
                f"Projection: {tplo.get('projection', 'not recorded')}"
            ),
            (
                f"Clinical review: {validation.get('status', 'not recorded')}  |  "
                f"TPA: {measurement.get('tpa_degrees', 'not calculated')} degrees"
            ),
            (
                f"Plateau length: {measurement.get('plateau_length_mm', 'not calibrated')} mm  |  "
                f"Tibial axis: {measurement.get('tibial_axis_length_mm', 'not calibrated')} mm"
            ),
            (
                f"Calibration: {calibration_result.get('calibration_id', 'not recorded')}  |  "
                f"Scale: {calibration_result.get('mm_per_pixel', 'not recorded')} mm/px"
            ),
            "Radiographic quality: "
            + ", ".join(f"{key}={value}" for key, value in quality.items() if key != "notes"),
            (
                f"Correction: {correction.get('status', 'not calculated')}; "
                f"pre-op TPA={correction.get('preoperative_tpa_degrees')} degrees"
            ),
            (
                f"Current slope={correction.get('current_slope_degrees')} degrees; "
                f"target={correction.get('target_slope_degrees')} degrees; "
                f"blade={correction.get('blade_diameter_mm')} mm"
            ),
            (
                f"Rotation={correction.get('rotation_mm')} mm; "
                f"acceptance={correction.get('acceptance', 'NOT_ASSESSED')}"
            ),
            (
                f"Rotation table: {correction.get('table_version', 'not recorded')}; "
                f"source={correction.get('table_source', 'not recorded')}"
            ),
            f"Rotation table SHA-256: {correction.get('table_entries_sha256', 'not recorded')}",
        ]
        rotation_objects = [
            item
            for item in snapshot.get("objects", [])
            if isinstance(item, dict) and item.get("type") == "TPLO"
        ]
        for index, item in enumerate(rotation_objects[:2], start=1):
            values = (item.get("measurement") or {}).get("values") or {}
            rows.append(
                f"TPLO plan {index}: radius={values.get('radius')} mm; "
                f"rotation={values.get('rotation')} degrees"
            )
        cls._text(draw, (64, top), "PLAN SUMMARY", font=font)
        for index, row in enumerate(rows, start=1):
            cls._text(draw, (64, top + index * 42), row, font=small_font)

        additional = snapshot.get("additional_measurements") or []
        y = top + 42 * (len(rows) + 1)
        available_rows = max(0, (PAGE_SIZE[1] - y - 80) // 34)
        for item in additional[: min(4, available_rows)]:
            cls._text(
                draw,
                (64, y),
                (
                    f"{item.get('id')}: {item.get('value')} {item.get('unit')}  |  "
                    f"acceptance={item.get('acceptance')}"
                ),
                font=small_font,
            )
            y += 34
        audit = validation.get("audit") or []
        if audit and isinstance(audit[-1], dict):
            latest = audit[-1]
            cls._text(
                draw,
                (64, min(y + 16, PAGE_SIZE[1] - 60)),
                (
                    f"Latest review: {latest.get('decision')} by {latest.get('actor_id')} "
                    f"at {latest.get('reviewed_at')}"
                ),
                font=small_font,
            )

    @staticmethod
    def _text(
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        value: object,
        *,
        font: ImageFont.ImageFont,
    ) -> None:
        ascii_text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
        draw.text(position, ascii_text, fill="#111827", font=font)
