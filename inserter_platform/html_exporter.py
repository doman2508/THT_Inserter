from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from . import db


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "pcb_template.html"


def safe_html_filename(name: str) -> str:
    stem = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip(" .")
    stem = re.sub(r"\s+", " ", stem) or "projekt"
    return f"{stem}.html"


def _point_designators_for_step(step: dict[str, Any]) -> list[str]:
    segments = db.step_segments_from_row(step)
    if segments:
        designators: list[str] = []
        for segment in segments:
            for designator in segment.get("designators") or []:
                clean = str(designator).strip().upper()
                if clean and clean not in designators:
                    designators.append(clean)
        return designators
    return db.split_designators(str(step.get("designators") or ""))


def _display_designators_for_step(step: dict[str, Any]) -> str:
    segments = db.step_segments_from_row(step)
    if segments:
        labels = [
            str(segment.get("label") or "+".join(segment.get("designators") or [])).strip()
            for segment in segments
        ]
        labels = [label for label in labels if label]
        if labels:
            return ",".join(labels)
    return ",".join(_point_designators_for_step(step))


def _display_value_for_step(step: dict[str, Any]) -> str:
    value = str(step.get("value") or "")
    segments = db.step_segments_from_row(step)
    counts = db.pin_counts_from_value(value)
    pin_count = db.step_pin_count_from_values(value, segments)
    if pin_count and len(counts) > 1 and counts[0] != pin_count:
        return re.sub(r"^\s*\d+\s*PIN", f"{pin_count} PIN", value, flags=re.IGNORECASE)
    return value


def _display_quantity_for_step(step: dict[str, Any]) -> str:
    segments = db.step_segments_from_row(step)
    if not segments:
        return str(step.get("quantity") or 1)
    quantity = sum(int(segment.get("quantity") or 1) for segment in segments)
    pin_count = db.step_pin_count_from_values(str(step.get("value") or ""), segments)
    return f"{quantity} szt. po {pin_count} PIN" if pin_count else f"{quantity} szt."


def _board_base_metrics(project: dict[str, Any], points: list[dict[str, Any]]) -> dict[str, Any]:
    project_width = float(project.get("board_width") or 0)
    project_height = float(project.get("board_height") or 0)
    metric_points = project.get("points") or points
    coordinates = [
        {"x": float(point.get("x") or 0), "y": float(point.get("y") or 0)}
        for point in metric_points
    ]
    raw_max_x = max([point["x"] for point in coordinates], default=0)
    raw_max_y = max([point["y"] for point in coordinates], default=0)
    raw_min_x = min([point["x"] for point in coordinates], default=0)
    raw_min_y = min([point["y"] for point in coordinates], default=0)
    max_x = max(0, raw_max_x)
    max_y = max(0, raw_max_y)

    profile = (project.get("board_contours") or {}).get("profile") or {}
    try:
        profile_width = float(profile.get("width") or 0)
        profile_height = float(profile.get("height") or 0)
        profile_origin_x = float(profile.get("x") or 0)
        profile_origin_y = float(profile.get("y") or 0)
    except (TypeError, ValueError):
        profile_width = 0
        profile_height = 0
        profile_origin_x = 0
        profile_origin_y = 0
    if profile.get("fromProfile") and profile_width > 0 and profile_height > 0:
        raw_fit = 0
        local_fit = 0
        for point in coordinates:
            if (
                profile_origin_x - 2 <= point["x"] <= profile_origin_x + profile_width + 2
                and profile_origin_y - 2 <= point["y"] <= profile_origin_y + profile_height + 2
            ):
                raw_fit += 1
            if -2 <= point["x"] <= profile_width + 2 and -2 <= point["y"] <= profile_height + 2:
                local_fit += 1
        return {
            "width": profile_width,
            "height": profile_height,
            "originX": profile_origin_x if raw_fit > local_fit else 0,
            "originY": profile_origin_y if raw_fit > local_fit else 0,
            "swapped": False,
        }

    if not project_width or not project_height:
        return {"width": max_x or 1, "height": max_y or 1, "originX": 0, "originY": 0, "swapped": False}

    looks_swapped = bool(
        coordinates
        and max_y > project_height
        and max_y <= project_width * 1.03
        and max_x <= project_height * 1.03
    )
    width = project_height if looks_swapped else project_width
    height = project_width if looks_swapped else project_height
    tolerance_x = max(1, width * 0.03)
    tolerance_y = max(1, height * 0.03)
    if raw_max_x > width + tolerance_x:
        origin_x = raw_max_x - width
    elif raw_min_x < -tolerance_x:
        origin_x = raw_min_x
    else:
        origin_x = 0

    if raw_max_y <= 0 and raw_min_y < -tolerance_y:
        origin_y = raw_max_y - height
    elif raw_max_y > height + tolerance_y:
        origin_y = raw_max_y - height
    elif raw_min_y < -tolerance_y:
        origin_y = raw_min_y
    else:
        origin_y = 0

    return {
        "width": width,
        "height": height,
        "originX": origin_x,
        "originY": origin_y,
        "swapped": looks_swapped,
    }


def _normalize_calibration(project: dict[str, Any]) -> dict[str, Any]:
    calibration = project.get("board_calibration") or {}
    rotation = int(calibration.get("rotation") or 0)
    if rotation not in {0, 90, 180, 270}:
        rotation = 0

    def number(name: str, fallback: float) -> float:
        try:
            return float(calibration.get(name))
        except (TypeError, ValueError):
            return fallback

    offset_x = max(-50.0, min(50.0, number("offsetX", 0.0)))
    offset_y = max(-50.0, min(50.0, number("offsetY", 0.0)))
    scale_x = max(0.2, min(3.0, number("scaleX", 1.0)))
    scale_y = max(0.2, min(3.0, number("scaleY", 1.0)))
    return {
        "rotation": rotation,
        "flipX": bool(calibration.get("flipX")),
        "flipY": bool(calibration.get("flipY")),
        "offsetX": offset_x,
        "offsetY": offset_y,
        "scaleX": scale_x,
        "scaleY": scale_y,
    }


def _apply_calibration(x: float, y: float, calibration: dict[str, Any]) -> tuple[float, float]:
    rotation = calibration.get("rotation")
    if rotation == 90:
        x, y = 1 - y, x
    elif rotation == 180:
        x, y = 1 - x, 1 - y
    elif rotation == 270:
        x, y = y, 1 - x

    if calibration.get("flipX"):
        x = 1 - x
    if calibration.get("flipY"):
        y = 1 - y

    x = 0.5 + (x - 0.5) * float(calibration.get("scaleX") or 1) + float(calibration.get("offsetX") or 0) / 100
    y = 0.5 + (y - 0.5) * float(calibration.get("scaleY") or 1) + float(calibration.get("offsetY") or 0) / 100

    return max(0, min(1, x)), max(0, min(1, y))


def _export_component_points(project: dict[str, Any], used_designators: set[str]) -> tuple[list[dict[str, Any]], float, float]:
    source_points = [
        point for point in project.get("points") or []
        if str(point.get("designator") or "").strip().upper() in used_designators
    ]
    metrics = _board_base_metrics(project, source_points or (project.get("points") or []))
    calibration = _normalize_calibration(project)
    sideways = calibration["rotation"] in {90, 270}
    display_width = metrics["height"] if sideways else metrics["width"]
    display_height = metrics["width"] if sideways else metrics["height"]
    board_width = float(metrics["width"] or 1)
    board_height = float(metrics["height"] or 1)
    origin_x = float(metrics.get("originX") or 0)
    origin_y = float(metrics.get("originY") or 0)

    exported: list[dict[str, Any]] = []
    for point in source_points:
        normalized_x = (float(point.get("x") or 0) - origin_x) / board_width
        normalized_y = (board_height - (float(point.get("y") or 0) - origin_y)) / board_height
        calibrated_x, calibrated_y = _apply_calibration(normalized_x, normalized_y, calibration)
        exported.append(
            {
                "Desygnator": str(point.get("designator") or "").strip().upper(),
                "X": calibrated_x * display_width,
                "Y": (1 - calibrated_y) * display_height,
                "Rotacja": point.get("rotation"),
            }
        )

    return exported, float(display_width or 1), float(display_height or 1)


def _export_polarity_points(project: dict[str, Any], used_designators: set[str]) -> list[dict[str, Any]]:
    source_points = [
        point for point in project.get("points") or []
        if str(point.get("designator") or "").strip().upper() in used_designators
    ]
    metrics = _board_base_metrics(project, source_points or (project.get("points") or []))
    calibration = _normalize_calibration(project)
    sideways = calibration["rotation"] in {90, 270}
    display_width = metrics["height"] if sideways else metrics["width"]
    display_height = metrics["width"] if sideways else metrics["height"]
    board_width = float(metrics["width"] or 1)
    board_height = float(metrics["height"] or 1)
    origin_x = float(metrics.get("originX") or 0)
    origin_y = float(metrics.get("originY") or 0)

    exported: list[dict[str, Any]] = []
    for item in project.get("polarity") or []:
        designator = str(item.get("designator") or "").strip().upper()
        plus_x = item.get("plus_x")
        plus_y = item.get("plus_y")
        if not item.get("required") or designator not in used_designators or plus_x is None or plus_y is None:
            continue
        normalized_x = (float(plus_x) - origin_x) / board_width
        normalized_y = (board_height - (float(plus_y) - origin_y)) / board_height
        calibrated_x, calibrated_y = _apply_calibration(normalized_x, normalized_y, calibration)
        exported.append(
            {
                "Desygnator": designator,
                "X": calibrated_x * display_width,
                "Y": (1 - calibrated_y) * display_height,
            }
        )
    return exported


def _calibrated_display_point(
    *,
    x: float,
    y: float,
    metrics: dict[str, Any],
    calibration: dict[str, Any],
    display_width: float,
    display_height: float,
) -> dict[str, float]:
    board_width = float(metrics["width"] or 1)
    board_height = float(metrics["height"] or 1)
    normalized_x = x / board_width
    normalized_y = (board_height - y) / board_height
    calibrated_x, calibrated_y = _apply_calibration(normalized_x, normalized_y, calibration)
    return {
        "X": calibrated_x * display_width,
        "Y": (1 - calibrated_y) * display_height,
    }


def _export_board_contours(project: dict[str, Any], used_designators: set[str]) -> list[dict[str, Any]]:
    board_contours = project.get("board_contours") or {}
    contours = board_contours.get("contours") if isinstance(board_contours.get("contours"), list) else []
    if not contours:
        return []

    metrics = _board_base_metrics(project, project.get("points") or [])
    calibration = _normalize_calibration(project)
    sideways = calibration["rotation"] in {90, 270}
    display_width = float(metrics["height"] if sideways else metrics["width"]) or 1
    display_height = float(metrics["width"] if sideways else metrics["height"]) or 1

    exported: list[dict[str, Any]] = []
    for contour in contours:
        designators = [
            str(item or "").strip().upper()
            for item in contour.get("designators") or []
            if str(item or "").strip()
        ]
        designators = list(dict.fromkeys(designators))
        if not designators or not any(designator in used_designators for designator in designators):
            continue
        try:
            x = float(contour.get("x") or 0)
            y = float(contour.get("y") or 0)
            width = float(contour.get("width") or 0)
            height = float(contour.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue

        corners = [
            _calibrated_display_point(
                x=x,
                y=y,
                metrics=metrics,
                calibration=calibration,
                display_width=display_width,
                display_height=display_height,
            ),
            _calibrated_display_point(
                x=x + width,
                y=y,
                metrics=metrics,
                calibration=calibration,
                display_width=display_width,
                display_height=display_height,
            ),
            _calibrated_display_point(
                x=x + width,
                y=y + height,
                metrics=metrics,
                calibration=calibration,
                display_width=display_width,
                display_height=display_height,
            ),
            _calibrated_display_point(
                x=x,
                y=y + height,
                metrics=metrics,
                calibration=calibration,
                display_width=display_width,
                display_height=display_height,
            ),
        ]
        exported.append(
            {
                "Id": str(contour.get("id") or ""),
                "Desygnatory": designators,
                "Punkty": corners,
                "Inferowany": bool(contour.get("inferred")),
            }
        )
    return exported


def _image_data_uri(path_value: str) -> str:
    image_path = Path(path_value)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono obrazu PCB: {path_value}")

    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _optional_image_data_uri(path_value: str | None) -> str:
    if not path_value:
        return ""
    try:
        return _image_data_uri(path_value)
    except FileNotFoundError:
        return ""


def render_project_html(project: dict[str, Any]) -> tuple[str, str]:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError("Brak szablonu pcb_template.html")
    if not project.get("board_image_path"):
        raise ValueError("Projekt nie ma obrazu PCB")

    table_data: list[dict[str, Any]] = []
    used_designators: set[str] = set()
    for index, step in enumerate(project.get("steps") or [], start=1):
        point_designators = _point_designators_for_step(step)
        used_designators.update(point_designators)
        table_data.append(
            {
                "Lp.": index,
                "Desygnator": _display_designators_for_step(step),
                "Wartość": _display_value_for_step(step),
                "Indeks Medcom": str(step.get("medcom_index") or ""),
                "Ilość": _display_quantity_for_step(step),
                "UWAGI": db.note_without_segments(str(step.get("notes") or "")),
                "Sekundy": step.get("seconds") or "",
            }
        )

    component_data, pcb_width, pcb_height = _export_component_points(project, used_designators)
    polarity_data = _export_polarity_points(project, used_designators)
    contour_data = _export_board_contours(project, used_designators)
    preview_images = [
        {
            "key": "tht",
            "label": "Podgląd THT",
            "image": _optional_image_data_uri(project.get("tht_preview_image_path")),
        },
        {
            "key": "labeling",
            "label": "Podgląd Oklejanie",
            "image": _optional_image_data_uri(project.get("labeling_preview_image_path")),
        },
    ]
    preview_images = [item for item in preview_images if item["image"]]
    environment = Environment(loader=FileSystemLoader(str(TEMPLATE_PATH.parent)))
    template = environment.get_template(TEMPLATE_PATH.name)
    html = template.render(
        pcb_image=_image_data_uri(str(project.get("board_image_path"))),
        table_data=json.dumps(table_data, ensure_ascii=False),
        component_data=json.dumps(component_data, ensure_ascii=False),
        polarity_data=json.dumps(polarity_data, ensure_ascii=False),
        contour_data=json.dumps(contour_data, ensure_ascii=False),
        preview_images=json.dumps(preview_images, ensure_ascii=False),
        pcb_width=pcb_width,
        pcb_height=pcb_height,
        project_name=str(project.get("name") or "Projekt"),
    )
    return html, safe_html_filename(str(project.get("name") or "Projekt"))
