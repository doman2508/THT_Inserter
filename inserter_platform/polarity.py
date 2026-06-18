from __future__ import annotations

import io
import re
import math
from typing import Any


CAPACITOR_DESIGNATOR_RE = re.compile(r"\bC\d+[A-Z]?\b", re.IGNORECASE)
POINTS_PER_MM = 72 / 25.4


def designator_sort_key(value: str) -> tuple[str, int, str]:
    match = re.match(r"^([A-Z]+)(\d+)(.*)$", value.upper())
    if not match:
        return (value.upper(), 0, "")
    return (match.group(1), int(match.group(2)), match.group(3))


def content_coordinate_scale(content: str) -> float:
    match = re.search(r"^\s*([0-9.]+)\s+0\s+0\s+\1\s+0\s+0\s+cm\b", content)
    if not match:
        return 1.0
    scale = float(match.group(1))
    return scale if 0 < scale <= 1 else 1.0


def segment_lines_from_content(content: str) -> list[tuple[float, float, float, float, float]]:
    scale = content_coordinate_scale(content)
    command_re = re.compile(
        r"([-0-9.]+)\s+([-0-9.]+)\s+m\s*\n"
        r"([-0-9.]+)\s+([-0-9.]+)\s+l\s*\nS"
    )
    segments = []
    for match in command_re.finditer(content):
        x1, y1, x2, y2 = (float(value) * scale for value in match.groups())
        length = math.hypot(x2 - x1, y2 - y1)
        if length >= 0.05:
            segments.append((x1, y1, x2, y2, length))
    return segments


def find_plus_markers(content: str) -> list[dict[str, float]]:
    segments = segment_lines_from_content(content)
    horizontal = [
        segment for segment in segments
        if abs(segment[1] - segment[3]) < 0.035 and 2.1 <= segment[4] <= 3.6
    ]
    vertical = [
        segment for segment in segments
        if abs(segment[0] - segment[2]) < 0.035 and 2.1 <= segment[4] <= 3.6
    ]

    markers: list[dict[str, float]] = []
    for hx1, hy, hx2, _hy2, h_length in horizontal:
        h_min, h_max = sorted((hx1, hx2))
        h_center_x = (h_min + h_max) / 2
        for vx, vy1, _vx2, vy2, v_length in vertical:
            v_min, v_max = sorted((vy1, vy2))
            v_center_y = (v_min + v_max) / 2
            crosses = h_min - 0.06 <= vx <= h_max + 0.06 and v_min - 0.06 <= hy <= v_max + 0.06
            centered = abs(vx - h_center_x) < 0.25 and abs(hy - v_center_y) < 0.25
            balanced = abs(h_length - v_length) < 0.7
            if not (crosses and centered and balanced):
                continue
            marker = {
                "pdf_x": (h_center_x + vx) / 2,
                "pdf_y": (hy + v_center_y) / 2,
                "size": (h_length + v_length) / 2,
            }
            if not any(
                math.hypot(marker["pdf_x"] - existing["pdf_x"], marker["pdf_y"] - existing["pdf_y"]) < 0.2
                for existing in markers
            ):
                markers.append(marker)
    return markers


def nearest_plus_marker(
    label: dict[str, Any],
    plus_markers: list[dict[str, float]],
    max_distance: float = 35.0,
) -> tuple[dict[str, float] | None, float | None]:
    label_x = float(label.get("pdf_x") or 0)
    label_y = float(label.get("pdf_y") or 0)
    if not plus_markers:
        return None, None
    marker = min(
        plus_markers,
        key=lambda item: (item["pdf_x"] - label_x) ** 2 + (item["pdf_y"] - label_y) ** 2,
    )
    distance = math.hypot(marker["pdf_x"] - label_x, marker["pdf_y"] - label_y)
    if distance > max_distance:
        return None, distance
    return marker, distance


def pdf_point_to_kicad_board_coordinates(pdf_x: float, pdf_y: float, page_height: float) -> tuple[float, float]:
    return pdf_x / POINTS_PER_MM, (pdf_y - page_height) / POINTS_PER_MM


def extract_fab_pdf_candidates(content: bytes) -> list[dict[str, Any]]:
    """Extract capacitor designator candidates from a Fab PDF.

    The first PRO step is intentionally conservative: Fab gives us reliable
    designator labels, while the actual + marker is still confirmed by admin
    on the PCB image.
    """
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("Brak biblioteki pypdf do odczytu PDF.") from error

    reader = PdfReader(io.BytesIO(content))
    found: dict[str, dict[str, Any]] = {}

    for page_index, page in enumerate(reader.pages):
        box = page.mediabox
        page_width = float(box.width)
        page_height = float(box.height)
        page_content = page.get_contents().get_data().decode("latin1", errors="replace")
        plus_markers = find_plus_markers(page_content)

        def visitor(text: str, cm: list[float], tm: list[float], font_dict: dict[str, Any], font_size: float) -> None:
            raw_text = text or ""
            for match in CAPACITOR_DESIGNATOR_RE.finditer(raw_text):
                designator = match.group(0).upper()
                if designator in found:
                    continue
                # In this export the text current matrix gives stable label coordinates.
                x = float(cm[4]) if len(cm) > 4 else None
                y = float(cm[5]) if len(cm) > 5 else None
                found[designator] = {
                    "designator": designator,
                    "pdf_x": x,
                    "pdf_y": y,
                    "pdf_page_width": page_width,
                    "pdf_page_height": page_height,
                    "pdf_page_index": page_index,
                    "confidence": 0.35,
                }

        page.extract_text(visitor_text=visitor)

        for item in found.values():
            if item.get("pdf_page_index") != page_index:
                continue
            marker, distance = nearest_plus_marker(item, plus_markers)
            if not marker:
                item["plus_pdf_distance"] = distance
                continue
            plus_x, plus_y = pdf_point_to_kicad_board_coordinates(
                marker["pdf_x"],
                marker["pdf_y"],
                page_height,
            )
            item.update(
                {
                    "plus_pdf_x": marker["pdf_x"],
                    "plus_pdf_y": marker["pdf_y"],
                    "plus_x": plus_x,
                    "plus_y": plus_y,
                    "plus_pdf_distance": distance,
                    "confidence": 0.82 if distance <= 22 else 0.62,
                }
            )

    return sorted(found.values(), key=lambda item: designator_sort_key(str(item["designator"])))
