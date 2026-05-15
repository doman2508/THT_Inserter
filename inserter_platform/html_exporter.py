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
    coordinates = [
        {"x": float(point.get("x") or 0), "y": float(point.get("y") or 0)}
        for point in points
    ]
    max_x = max([0, *[point["x"] for point in coordinates]])
    max_y = max([0, *[point["y"] for point in coordinates]])

    if not project_width or not project_height:
        return {"width": max_x or 1, "height": max_y or 1, "swapped": False}

    looks_swapped = bool(
        coordinates
        and max_y > project_height
        and max_y <= project_width * 1.03
        and max_x <= project_height * 1.03
    )
    if looks_swapped:
        return {"width": project_height, "height": project_width, "swapped": True}
    return {"width": project_width, "height": project_height, "swapped": False}


def _normalize_calibration(project: dict[str, Any]) -> dict[str, Any]:
    calibration = project.get("board_calibration") or {}
    rotation = int(calibration.get("rotation") or 0)
    if rotation not in {0, 90, 180, 270}:
        rotation = 0
    return {
        "rotation": rotation,
        "flipX": bool(calibration.get("flipX")),
        "flipY": bool(calibration.get("flipY")),
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

    exported: list[dict[str, Any]] = []
    for point in source_points:
        normalized_x = float(point.get("x") or 0) / board_width
        normalized_y = (board_height - float(point.get("y") or 0)) / board_height
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


def _image_data_uri(path_value: str) -> str:
    image_path = Path(path_value)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono obrazu PCB: {path_value}")

    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


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
    environment = Environment(loader=FileSystemLoader(str(TEMPLATE_PATH.parent)))
    template = environment.get_template(TEMPLATE_PATH.name)
    html = template.render(
        pcb_image=_image_data_uri(str(project.get("board_image_path"))),
        table_data=json.dumps(table_data, ensure_ascii=False),
        component_data=json.dumps(component_data, ensure_ascii=False),
        pcb_width=pcb_width,
        pcb_height=pcb_height,
        project_name=str(project.get("name") or "Projekt"),
    )
    return html, safe_html_filename(str(project.get("name") or "Projekt"))
