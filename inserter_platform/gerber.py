from __future__ import annotations

import math
import re
from typing import Any


COORDINATE_RE = re.compile(r"^(?:X(-?\d+))?(?:Y(-?\d+))?(D0[123])?\*$")
FORMAT_RE = re.compile(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%")


def _gerber_scale(text: str) -> float:
    match = FORMAT_RE.search(text)
    decimals = int(match.group(2)) if match else 4
    unit_scale = 25.4 if "%MOIN*%" in text else 1.0
    return unit_scale / (10**decimals)


def _parse_coordinate(value: str | None, previous: float, scale: float) -> float:
    if value is None or value == "":
        return previous
    return int(value) * scale


def _coordinate_paths(text: str) -> list[list[tuple[float, float]]]:
    scale = _gerber_scale(text)
    paths: list[list[tuple[float, float]]] = []
    current_path: list[tuple[float, float]] = []
    current_x = 0.0
    current_y = 0.0
    current_operation = ""
    in_region = False

    def finish_path() -> None:
        nonlocal current_path
        if len(current_path) > 1:
            paths.append(current_path)
        current_path = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "G36*":
            finish_path()
            in_region = True
            current_path = []
            continue
        if line == "G37*":
            finish_path()
            in_region = False
            continue

        match = COORDINATE_RE.match(line)
        if match and not any(match.groups()):
            match = None
        if not match:
            if re.fullmatch(r"D0[123]\*", line):
                current_operation = line[:3]
            continue

        current_x = _parse_coordinate(match.group(1), current_x, scale)
        current_y = _parse_coordinate(match.group(2), current_y, scale)
        operation = match.group(3) or current_operation or ("D01" if in_region else "D02")
        current_operation = operation

        point = (current_x, current_y)
        if operation == "D02":
            finish_path()
            current_path = [point]
        elif operation == "D01":
            if not current_path:
                current_path = [point]
            else:
                current_path.append(point)
        elif operation == "D03":
            finish_path()

    finish_path()
    return paths


def _all_coordinates(text: str) -> list[tuple[float, float]]:
    paths = _coordinate_paths(text)
    return [point for path in paths for point in path]


def _bounds(points: list[tuple[float, float]]) -> dict[str, float] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "minX": min(xs),
        "minY": min(ys),
        "maxX": max(xs),
        "maxY": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _round(value: float) -> float:
    return round(float(value), 4)


def _path_box(path: list[tuple[float, float]]) -> dict[str, Any] | None:
    if len(path) < 3:
        return None
    bounds = _bounds(path)
    if not bounds:
        return None

    width = bounds["width"]
    height = bounds["height"]
    area = width * height
    if width < 2.0 or height < 2.0 or area < 8.0:
        return None
    if width > 90.0 or height > 60.0:
        return None

    rounded_x = {round(point[0], 2) for point in path}
    rounded_y = {round(point[1], 2) for point in path}
    axis_aligned = len(rounded_x) <= 4 or len(rounded_y) <= 4
    if not axis_aligned and len(path) < 8:
        return None

    first = path[0]
    last = path[-1]
    closed_distance = math.hypot(first[0] - last[0], first[1] - last[1])
    return {
        "rawMinX": bounds["minX"],
        "rawMinY": bounds["minY"],
        "rawMaxX": bounds["maxX"],
        "rawMaxY": bounds["maxY"],
        "pointCount": len(path),
        "closed": closed_distance < 0.5,
        "axisAligned": axis_aligned,
        "area": area,
    }


def _dedupe_boxes(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for box in sorted(boxes, key=lambda item: (item["rawMinX"], item["rawMinY"], item["area"])):
        duplicate = False
        for existing in deduped:
            if (
                abs(existing["rawMinX"] - box["rawMinX"]) < 0.12
                and abs(existing["rawMinY"] - box["rawMinY"]) < 0.12
                and abs(existing["rawMaxX"] - box["rawMaxX"]) < 0.12
                and abs(existing["rawMaxY"] - box["rawMaxY"]) < 0.12
            ):
                duplicate = True
                break
        if not duplicate:
            deduped.append(box)
    return deduped


def _assign_contours(
    contours: list[dict[str, Any]],
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    by_id = {item["id"]: item for item in contours}
    for contour in contours:
        contour["designators"] = []
    point_by_designator: dict[str, dict[str, Any]] = {}

    for point in points:
        designator = str(point.get("designator") or "").strip().upper()
        if not designator:
            continue
        point_by_designator[designator] = point
        try:
            point_x = float(point.get("x"))
            point_y = float(point.get("y"))
        except (TypeError, ValueError):
            continue

        best: tuple[float, float, str, str] | None = None
        for contour in contours:
            x = float(contour["x"])
            y = float(contour["y"])
            width = float(contour["width"])
            height = float(contour["height"])
            margin = max(0.9, min(width, height) * 0.22)
            center_x = x + width / 2
            center_y = y + height / 2
            distance = math.hypot(point_x - center_x, point_y - center_y)
            diagonal = math.hypot(width, height) or 1.0
            inside = x - margin <= point_x <= x + width + margin and y - margin <= point_y <= y + height + margin
            if inside:
                score = max(0.62, 0.98 - min(0.28, distance / diagonal * 0.24))
                # Prefer smaller matching boxes when a label glyph sits near a larger footprint.
                rank = score - min(0.08, (width * height) / 2500)
                mode = "inside"
            else:
                threshold = max(3.0, diagonal * 0.38)
                if distance > threshold:
                    continue
                score = max(0.35, 0.72 - distance / threshold * 0.24)
                rank = score - 0.12
                mode = "nearest"
            if best is None or rank > best[0]:
                best = (rank, score, contour["id"], mode)

        if best and best[1] >= 0.45:
            contour = by_id[best[2]]
            contour["designators"].append(designator)
            assignments.append(
                {
                    "designator": designator,
                    "contourId": best[2],
                    "confidence": round(best[1], 3),
                    "mode": best[3],
                }
            )

    assigned_designators = {item["designator"] for item in assignments}
    inferred_index = 1
    for point in points:
        designator = str(point.get("designator") or "").strip().upper()
        if not designator or designator in assigned_designators:
            continue
        if not re.fullmatch(r"[JX]\d+", designator):
            continue
        try:
            point_x = float(point.get("x"))
            point_y = float(point.get("y"))
        except (TypeError, ValueError):
            continue

        point_prefix = re.match(r"[A-Z]+", designator)
        point_rotation = _normal_rotation(point.get("rotation"))
        template: tuple[float, dict[str, Any], dict[str, Any]] | None = None
        for assignment in assignments:
            template_designator = assignment["designator"]
            if not point_prefix or not template_designator.startswith(point_prefix.group(0)):
                continue
            template_point = point_by_designator.get(template_designator)
            template_contour = by_id.get(assignment["contourId"])
            if not template_point or not template_contour:
                continue
            template_rotation = _normal_rotation(template_point.get("rotation"))
            rotation_delta = _rotation_delta(point_rotation, template_rotation)
            if rotation_delta > 20:
                continue
            distance = math.hypot(
                point_x - float(template_point.get("x") or 0),
                point_y - float(template_point.get("y") or 0),
            )
            score = distance + rotation_delta * 2
            if template is None or score < template[0]:
                template = (score, template_point, template_contour)

        if not template:
            continue

        template_point = template[1]
        template_contour = template[2]
        offset_x = float(template_point.get("x") or 0) - float(template_contour["x"])
        offset_y = float(template_point.get("y") or 0) - float(template_contour["y"])
        inferred_contour = {
            "id": f"I{inferred_index:04d}",
            "x": _round(point_x - offset_x),
            "y": _round(point_y - offset_y),
            "width": template_contour["width"],
            "height": template_contour["height"],
            "centerX": _round(point_x - offset_x + float(template_contour["width"]) / 2),
            "centerY": _round(point_y - offset_y + float(template_contour["height"]) / 2),
            "closed": bool(template_contour.get("closed")),
            "axisAligned": bool(template_contour.get("axisAligned")),
            "pointCount": int(template_contour.get("pointCount") or 0),
            "designators": [designator],
            "inferred": True,
            "templateDesignator": str(template_point.get("designator") or "").upper(),
        }
        contours.append(inferred_contour)
        by_id[inferred_contour["id"]] = inferred_contour
        assignments.append(
            {
                "designator": designator,
                "contourId": inferred_contour["id"],
                "confidence": 0.52,
                "mode": "inferred",
            }
        )
        assigned_designators.add(designator)
        inferred_index += 1

    for contour in contours:
        contour["designators"] = sorted(set(contour.get("designators") or []))
    return assignments


def _normal_rotation(value: object) -> float:
    try:
        return float(value) % 360
    except (TypeError, ValueError):
        return 0.0


def _rotation_delta(a: float, b: float) -> float:
    delta = abs((a - b) % 360)
    return min(delta, 360 - delta)


def _local_points(points: list[dict[str, Any]], origin: dict[str, float]) -> list[dict[str, Any]]:
    if not points:
        return []

    min_x = float(origin["minX"])
    min_y = float(origin["minY"])
    max_x = float(origin["maxX"])
    max_y = float(origin["maxY"])
    width = float(origin["width"])
    height = float(origin["height"])
    raw_fit = 0
    local_fit = 0
    numeric_points: list[dict[str, Any]] = []
    for point in points:
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except (TypeError, ValueError):
            continue
        numeric_points.append({**point, "x": x, "y": y})
        if min_x - 2 <= x <= max_x + 2 and min_y - 2 <= y <= max_y + 2:
            raw_fit += 1
        if -2 <= x <= width + 2 and -2 <= y <= height + 2:
            local_fit += 1

    if raw_fit > local_fit:
        return [
            {
                **point,
                "x": float(point["x"]) - min_x,
                "y": float(point["y"]) - min_y,
            }
            for point in numeric_points
        ]
    return numeric_points


def build_contour_overlay(
    *,
    profile_bytes: bytes | None,
    silkscreen_bytes: bytes,
    points: list[dict[str, Any]],
    source: str = "gerber_silkscreen",
) -> dict[str, Any]:
    silkscreen_text = silkscreen_bytes.decode("utf-8", errors="ignore")
    profile_text = profile_bytes.decode("utf-8", errors="ignore") if profile_bytes else ""

    profile_bounds = _bounds(_all_coordinates(profile_text)) if profile_text else None
    silkscreen_bounds = _bounds(_all_coordinates(silkscreen_text))
    origin = profile_bounds or silkscreen_bounds
    if not origin:
        raise ValueError("Nie udało się odczytać współrzędnych Gerber.")

    raw_boxes = [
        box
        for path in _coordinate_paths(silkscreen_text)
        for box in [_path_box(path)]
        if box is not None
    ]
    raw_boxes = _dedupe_boxes(raw_boxes)
    raw_boxes = sorted(raw_boxes, key=lambda item: (item["rawMinY"], item["rawMinX"], item["area"]))

    contours: list[dict[str, Any]] = []
    for index, box in enumerate(raw_boxes, start=1):
        x = box["rawMinX"] - origin["minX"]
        y = box["rawMinY"] - origin["minY"]
        width = box["rawMaxX"] - box["rawMinX"]
        height = box["rawMaxY"] - box["rawMinY"]
        if x < -2 or y < -2 or x > origin["width"] + 2 or y > origin["height"] + 2:
            continue
        contours.append(
            {
                "id": f"G{index:04d}",
                "x": _round(x),
                "y": _round(y),
                "width": _round(width),
                "height": _round(height),
                "centerX": _round(x + width / 2),
                "centerY": _round(y + height / 2),
                "closed": bool(box["closed"]),
                "axisAligned": bool(box["axisAligned"]),
                "pointCount": int(box["pointCount"]),
                "designators": [],
            }
        )

    assignments = _assign_contours(contours, _local_points(points, origin))
    return {
        "source": source,
        "profile": {
            "x": _round(origin["minX"]),
            "y": _round(origin["minY"]),
            "width": _round(origin["width"]),
            "height": _round(origin["height"]),
            "fromProfile": bool(profile_bounds),
        },
        "silkscreen": {
            "width": _round(silkscreen_bounds["width"]) if silkscreen_bounds else 0,
            "height": _round(silkscreen_bounds["height"]) if silkscreen_bounds else 0,
        },
        "contours": contours,
        "assignments": assignments,
        "summary": {
            "contours": len(contours),
            "assigned": len(assignments),
            "unassignedContours": len([item for item in contours if not item.get("designators")]),
            "points": len(points),
        },
    }
