from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def derive_plan_measurements(
    document: dict[str, Any], *, width_px: int | None, height_px: int | None
) -> dict[str, Any]:
    """Calculate displayable measurements from normalized source geometry.

    Derived values are always replaced on save. The calibration fingerprint binds them to
    the manual reference and the source image dimensions used for pixel conversion.
    """
    result = json.loads(json.dumps(document))
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

    return result


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
