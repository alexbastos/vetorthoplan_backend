from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from vetorthoplan.domain.planning.clinical_protocol import TploClinicalProtocol
from vetorthoplan.domain.planning.rotation_table import TploRotationTable, matches_numeric_filter


def derive_plan_measurements(
    document: dict[str, Any],
    *,
    width_px: int | None,
    height_px: int | None,
    clinical_protocol: TploClinicalProtocol | None = None,
    rotation_table: TploRotationTable | None = None,
) -> dict[str, Any]:
    """Calculate displayable measurements from normalized source geometry.

    Derived values are always replaced on save. The calibration fingerprint binds them to
    the manual reference and the source image dimensions used for pixel conversion.
    """
    result = json.loads(json.dumps(document))
    result.pop("clinical_protocol_version", None)
    _derive_additional_measurements(
        result,
        width_px=width_px,
        height_px=height_px,
        mm_per_pixel=derive_mm_per_pixel(result, width_px=width_px, height_px=height_px),
        clinical_protocol=clinical_protocol,
    )
    calibration = result.get("calibration")
    calibration_id: str | None = None
    mm_per_pixel: float | None = None

    if calibration is not None:
        calibration.pop("result", None)
        if width_px and height_px:
            if calibration["kind"] == "REFERENCE_LINE":
                start, end = calibration["start"], calibration["end"]
                reference_length_mm = calibration["known_length_mm"]
                reference_length_px = _distance(start, end, width_px, height_px)
            else:
                center, edge = calibration["center"], calibration["edge"]
                reference_length_mm = calibration["known_diameter_mm"]
                reference_length_px = 2 * _distance(center, edge, width_px, height_px)
            if reference_length_px > 0:
                canonical = json.dumps(
                    {
                        "calibration": calibration,
                        "image_dimensions_px": [width_px, height_px],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                calibration_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                mm_per_pixel = reference_length_mm / reference_length_px
                calibration["result"] = {
                    "calibration_id": calibration_id,
                    "reference_length_px": reference_length_px,
                    "mm_per_pixel": mm_per_pixel,
                }

    for item in result.get("objects", []):
        item.pop("measurement", None)
        item.pop("simulation", None)
        kind = item["type"]
        if kind == "ANGLE":
            value = _angle_degrees(item["start"], item["vertex"], item["end"])
            item["measurement"] = {
                "status": "CALCULATED",
                "values": {"angle": value},
                "units": {"angle": "degrees"},
            }
            continue

        if mm_per_pixel is None:
            status = "CALIBRATION_REQUIRED" if calibration is None else "IMAGE_DIMENSIONS_REQUIRED"
            item["measurement"] = {"status": status, "values": {}, "units": {}}
            if kind == "TPLO":
                item["simulation"] = {"status": status}
            continue

        if kind == "LINE":
            length = _distance(item["start"], item["end"], width_px, height_px) * mm_per_pixel
            values, units = {"length": length}, {"length": "mm"}
        elif kind == "CIRCLE":
            diameter = 2 * _distance(item["center"], item["edge"], width_px, height_px) * mm_per_pixel
            values = {
                "radius": diameter / 2,
                "diameter": diameter,
                "circumference": math.pi * diameter,
            }
            units = {key: "mm" for key in values}
        else:  # TPLO geometry includes a radius and a user-entered rotation.
            radius = _distance(item["center"], item["edge"], width_px, height_px) * mm_per_pixel
            values = {"radius": radius, "rotation": item["rotation_degrees"]}
            units = {"radius": "mm", "rotation": "degrees"}
        item["measurement"] = {
            "status": "CALCULATED",
            "calibration_id": calibration_id,
            "values": values,
            "units": units,
        }
        if kind == "TPLO":
            if item.get("fragment") is None:
                item["simulation"] = {
                    "status": "FRAGMENT_REQUIRED",
                    "calibration_id": calibration_id,
                }
            else:
                item["simulation"] = _simulate_fragment(
                    item,
                    calibration_id=calibration_id,
                    width_px=width_px,
                    height_px=height_px,
                    radius_mm=values["radius"],
                )

    landmarks = result.get("tplo_landmarks")
    result.pop("tplo_measurement", None)
    if landmarks is not None:
        if not width_px or not height_px:
            result["tplo_measurement"] = {
                "method": landmarks["method"],
                "status": "IMAGE_DIMENSIONS_REQUIRED",
                "clinically_validated": False,
            }
        else:
            plateau_start = landmarks["plateau_cranial"]
            plateau_end = landmarks["plateau_caudal"]
            axis_start = landmarks["intercondylar_midpoint"]
            axis_end = landmarks["talus_center"]
            plateau_dx = (plateau_end["x"] - plateau_start["x"]) * width_px
            plateau_dy = (plateau_end["y"] - plateau_start["y"]) * height_px
            axis_dx = (axis_end["x"] - axis_start["x"]) * width_px
            axis_dy = (axis_end["y"] - axis_start["y"]) * height_px
            axis_length = math.hypot(axis_dx, axis_dy)
            plateau_length = math.hypot(plateau_dx, plateau_dy)
            if axis_length > 0 and plateau_length > 0:
                cross_product = abs(plateau_dx * axis_dy - plateau_dy * axis_dx)
                dot_product = plateau_dx * axis_dx + plateau_dy * axis_dy
                tpa = math.degrees(math.atan2(abs(dot_product), cross_product))
                measurement = {
                    "method": landmarks["method"],
                    "status": "CALCULATED",
                    "tpa_degrees": tpa,
                    "clinically_validated": False,
                }
                if mm_per_pixel is not None:
                    measurement.update(
                        plateau_length_mm=plateau_length * mm_per_pixel,
                        tibial_axis_length_mm=axis_length * mm_per_pixel,
                        calibration_id=calibration_id,
                    )
                result["tplo_measurement"] = measurement
            else:
                result["tplo_measurement"] = {
                    "method": landmarks["method"],
                    "status": "LANDMARKS_REQUIRED",
                    "clinically_validated": False,
                }
    elif result.get("tplo") is not None:
        result["tplo_measurement"] = {
            "method": "MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1",
            "status": "LANDMARKS_REQUIRED",
            "clinically_validated": False,
        }

    _apply_tpa_acceptance(
        result,
        clinical_protocol=clinical_protocol,
    )
    if result.get("tplo") is not None or result.get("tplo_landmarks") is not None:
        result["tplo_correction"] = derive_tplo_correction(result, rotation_table=rotation_table)
    else:
        result.pop("tplo_correction", None)

    return result


def derive_tplo_correction(
    document: dict[str, Any], *, rotation_table: TploRotationTable | None
) -> dict[str, Any]:
    """Resolve only an exact, versioned rotation-table entry; never interpolate."""
    metadata = document.get("tplo") or {}
    measurement = document.get("tplo_measurement") or {}
    tpa = measurement.get("tpa_degrees")
    blade_diameter = metadata.get("blade_diameter_mm")
    result: dict[str, Any] = {
        "status": "LANDMARKS_REQUIRED",
        "preoperative_tpa_degrees": tpa,
        "current_slope_degrees": metadata.get("current_slope_degrees"),
        "target_slope_degrees": metadata.get("target_slope_degrees"),
        "blade_diameter_mm": blade_diameter,
        "rotation_mm": None,
        "table_version": rotation_table.version if rotation_table else None,
        "table_source": rotation_table.source if rotation_table else None,
        "table_entries_sha256": rotation_table.entries_sha256 if rotation_table else None,
        "acceptance": "NOT_ASSESSED",
        "clinically_validated": False,
    }
    if tpa is None:
        return result
    if blade_diameter is None:
        result["status"] = "BLADE_DIAMETER_REQUIRED"
        return result
    if rotation_table is None:
        result["status"] = "ROTATION_TABLE_NOT_CONFIGURED"
        return result

    result["target_slope_degrees"] = (
        result["target_slope_degrees"]
        if result["target_slope_degrees"] is not None
        else rotation_table.target_slope_degrees
    )
    if (
        metadata.get("target_slope_degrees") is not None
        and rotation_table.target_slope_degrees is not None
        and not math.isclose(
            float(metadata["target_slope_degrees"]),
            rotation_table.target_slope_degrees,
            abs_tol=1e-9,
        )
    ):
        result["status"] = "TARGET_SLOPE_MISMATCH"
        return result
    if result["target_slope_degrees"] is None:
        result["status"] = "TARGET_SLOPE_REQUIRED"
        return result
    entry = next(
        (
            row
            for row in rotation_table.entries
            if matches_numeric_filter(row.get("tpa_degrees"), tpa)
            and matches_numeric_filter(row.get("blade_diameter_mm"), blade_diameter)
        ),
        None,
    )
    if entry is None:
        result["status"] = "EXACT_TABLE_MATCH_REQUIRED"
        return result

    result.update(
        status="CALCULATED",
        rotation_mm=float(entry["rotation_mm"]),
        acceptance="PASS",
    )
    return result


def derive_mm_per_pixel(
    document: dict[str, Any], *, width_px: int | None, height_px: int | None
) -> float | None:
    calibration = document.get("calibration")
    if calibration is None or not width_px or not height_px:
        return None
    if calibration["kind"] == "REFERENCE_LINE":
        length_px = _distance(calibration["start"], calibration["end"], width_px, height_px)
        known_length = calibration["known_length_mm"]
    else:
        length_px = 2 * _distance(calibration["center"], calibration["edge"], width_px, height_px)
        known_length = calibration["known_diameter_mm"]
    return known_length / length_px if length_px > 0 else None


def _derive_additional_measurements(
    document: dict[str, Any],
    *,
    width_px: int | None,
    height_px: int | None,
    mm_per_pixel: float | None,
    clinical_protocol: TploClinicalProtocol | None,
) -> None:
    document.pop("additional_measurements", None)
    if clinical_protocol is None:
        document["additional_measurements"] = []
        return

    inputs = document.get("additional_measurements_input") or {}
    landmarks = inputs.get("landmarks", {})
    reference_values = inputs.get("reference_values", {})
    results = []
    for definition in clinical_protocol.measurements:
        points = [landmarks.get(name) for name in definition.landmarks]
        value = None
        status = "LANDMARKS_REQUIRED"
        if all(point is not None for point in points):
            if definition.kind == "DISTANCE":
                if width_px and height_px and mm_per_pixel is not None:
                    value = _distance(points[0], points[1], width_px, height_px) * mm_per_pixel
                    status = "CALCULATED"
                else:
                    status = "CALIBRATION_REQUIRED"
            else:
                value = _angle_degrees(points[0], points[1], points[2])
                status = "CALCULATED"

        reference = reference_values.get(definition.id)
        error = abs(value - reference) if value is not None and reference is not None else None
        accepted = error <= definition.max_absolute_error if error is not None else None
        results.append(
            {
                "id": definition.id,
                "label": definition.label,
                "kind": definition.kind,
                "status": status,
                "value": value,
                "reference_value": reference,
                "absolute_error": error,
                "max_absolute_error": definition.max_absolute_error,
                "acceptance": "PASS" if accepted is True else "FAIL" if accepted is False else "NOT_ASSESSED",
                "unit": definition.unit,
                "clinically_validated": False,
            }
        )
    document["additional_measurements"] = results
    document["clinical_protocol_version"] = clinical_protocol.version


def _apply_tpa_acceptance(
    document: dict[str, Any], *, clinical_protocol: TploClinicalProtocol | None
) -> None:
    measurement = document.get("tplo_measurement")
    if not isinstance(measurement, dict):
        return
    if clinical_protocol is None or clinical_protocol.tpa_max_absolute_error_degrees is None:
        measurement["acceptance"] = "NOT_CONFIGURED"
        return
    inputs = document.get("additional_measurements_input") or {}
    reference = (inputs.get("reference_values") or {}).get("TPA")
    value = measurement.get("tpa_degrees")
    tolerance = clinical_protocol.tpa_max_absolute_error_degrees
    error = abs(value - reference) if value is not None and reference is not None else None
    measurement.update(
        reference_tpa_degrees=reference,
        tpa_absolute_error_degrees=error,
        tpa_max_absolute_error_degrees=tolerance,
        acceptance=("PASS" if error <= tolerance else "FAIL") if error is not None else "NOT_ASSESSED",
        clinical_protocol_version=clinical_protocol.version,
    )


def _distance(
    start: dict[str, float], end: dict[str, float], width_px: int, height_px: int
) -> float:
    dx = (end["x"] - start["x"]) * width_px
    dy = (end["y"] - start["y"]) * height_px
    return math.hypot(dx, dy)


def _angle_degrees(
    start: dict[str, float], vertex: dict[str, float], end: dict[str, float]
) -> float:
    ax, ay = start["x"] - vertex["x"], start["y"] - vertex["y"]
    bx, by = end["x"] - vertex["x"], end["y"] - vertex["y"]
    return math.degrees(math.atan2(abs(ax * by - ay * bx), ax * bx + ay * by))


def _simulate_fragment(
    item: dict[str, Any],
    *,
    calibration_id: str,
    width_px: int,
    height_px: int,
    radius_mm: float,
) -> dict[str, Any]:
    center_px = {
        "x": item["center"]["x"] * width_px,
        "y": item["center"]["y"] * height_px,
    }
    radians = math.radians(item["rotation_degrees"])
    cosine, sine = math.cos(radians), math.sin(radians)
    cx, cy = center_px["x"], center_px["y"]
    return {
        "status": "SIMULATED",
        "calibration_id": calibration_id,
        "center_px": center_px,
        "radius_mm": radius_mm,
        "rotation_degrees": item["rotation_degrees"],
        "affine_matrix": [
            [cosine, -sine, cx - cosine * cx + sine * cy],
            [sine, cosine, cy - sine * cx - cosine * cy],
        ],
    }
