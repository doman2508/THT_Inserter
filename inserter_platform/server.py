from __future__ import annotations

import json
import mimetypes
import os
import shutil
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from . import db
from . import html_exporter
from . import importer


HOST = os.environ.get("INSERTER_PLATFORM_HOST", "127.0.0.1")
PORT = int(os.environ.get("INSERTER_PLATFORM_PORT", "8780"))
STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(os.environ.get("INSERTER_UPLOAD_DIR", Path("data") / "uploads"))
MAX_BODY_BYTES = 60 * 1024 * 1024
ALLOWED_BOARD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def parse_number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.replace(",", ".").strip()
    return float(value)


def parse_int(value: object, fallback: int = 1) -> int:
    if value in (None, ""):
        return fallback
    return int(value)


PROJECT_STATUSES = {"draft", "imported", "needs_preparation", "prepared", "ready", "active", "archived"}


def parse_header_parameters(value: str) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        parameters[key.strip().lower()] = raw_value.strip().strip('"')
    return parameters


def save_board_image(project_id: str, upload: dict[str, object] | None) -> str | None:
    if not upload:
        return None
    filename = str(upload.get("filename") or "").strip()
    content = bytes(upload.get("content") or b"")
    if not filename or not content:
        return None

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_BOARD_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_BOARD_IMAGE_EXTENSIONS))
        raise ApiError(400, f"Unsupported board image type. Allowed: {allowed}")

    project_upload_dir = UPLOAD_DIR / project_id
    project_upload_dir.mkdir(parents=True, exist_ok=True)
    for existing in project_upload_dir.glob("board*"):
        if existing.is_file() and existing.suffix.lower() in ALLOWED_BOARD_IMAGE_EXTENSIONS:
            existing.unlink(missing_ok=True)
    target = project_upload_dir / f"board_{time.time_ns()}{extension}"
    target.write_bytes(content)
    return target.as_posix()


def remove_project_uploads(project_id: str) -> None:
    target = (UPLOAD_DIR / project_id).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if upload_root in target.parents and target.exists():
        shutil.rmtree(target, ignore_errors=True)


class PlatformHandler(BaseHTTPRequestHandler):
    server_version = "MSXInserterPlatform/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def send_html_attachment(self, html: str, filename: str) -> None:
        body = html.encode("utf-8")
        ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii") or "projekt.html"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(filename)}",
        )
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def send_static(self, relative_path: str) -> None:
        if relative_path in ("", "/"):
            relative_path = "index.html"
        relative_path = relative_path.lstrip("/")
        target = (STATIC_DIR / relative_path).resolve()
        static_root = STATIC_DIR.resolve()
        if static_root not in target.parents and target != static_root:
            self.send_json(403, {"ok": False, "error": "Forbidden"})
            return
        if not target.exists() or not target.is_file():
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_upload(self, relative_path: str) -> None:
        relative_path = relative_path.removeprefix("/uploads/").lstrip("/")
        target = (UPLOAD_DIR / relative_path).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if upload_root not in target.parents and target != upload_root:
            self.send_json(403, {"ok": False, "error": "Forbidden"})
            return
        if not target.exists() or not target.is_file():
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ApiError(413, "Invalid request size")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ApiError(400, f"Invalid JSON: {error}") from error

    def read_multipart(self) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ApiError(413, "Invalid request size")

        content_type = self.headers.get("Content-Type") or ""
        parameters = parse_header_parameters(content_type)
        boundary = parameters.get("boundary")
        if not boundary:
            raise ApiError(400, "Missing multipart boundary")

        body = self.rfile.read(length)
        delimiter = f"--{boundary}".encode("utf-8")
        fields: dict[str, str] = {}
        files: dict[str, dict[str, object]] = {}

        for raw_part in body.split(delimiter):
            if not raw_part or raw_part in (b"--\r\n", b"--"):
                continue
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if part == b"--" or b"\r\n\r\n" not in part:
                continue
            raw_headers, content = part.split(b"\r\n\r\n", 1)
            if content.endswith(b"\r\n"):
                content = content[:-2]

            headers: dict[str, str] = {}
            for raw_line in raw_headers.split(b"\r\n"):
                if b":" not in raw_line:
                    continue
                key, value = raw_line.split(b":", 1)
                headers[key.decode("utf-8", errors="replace").lower()] = value.decode(
                    "utf-8", errors="replace"
                ).strip()

            disposition = headers.get("content-disposition", "")
            disposition_parameters = parse_header_parameters(disposition)
            name = disposition_parameters.get("name")
            if not name:
                continue
            filename = disposition_parameters.get("filename")
            if filename is not None:
                files[name] = {"filename": filename, "content": content}
            else:
                fields[name] = content.decode("utf-8", errors="replace")

        return fields, files

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self.send_json(200, {"ok": True, "database": str(db.db_path())})
                return
            if path.startswith("/uploads/"):
                self.send_upload(path)
                return
            if path == "/api/pin-indexes":
                self.send_json(200, {"pinIndexes": db.list_pin_indexes()})
                return
            if path == "/api/projects":
                self.send_json(200, {"projects": db.list_projects()})
                return
            if path.startswith("/api/projects/") and path.endswith("/operator-html"):
                project_id = path.split("/")[3]
                project = db.get_project(project_id)
                if not project:
                    raise ApiError(404, "Project not found")
                try:
                    html, filename = html_exporter.render_project_html(project)
                except ValueError as error:
                    raise ApiError(409, str(error)) from error
                self.send_html_attachment(html, filename)
                return
            if path.startswith("/api/projects/"):
                project_id = path.split("/", 3)[3]
                project = db.get_project(project_id)
                if not project:
                    raise ApiError(404, "Project not found")
                self.send_json(200, {"project": project})
                return
            if path.startswith("/api/sessions/"):
                session_id = path.split("/", 3)[3]
                session = db.get_session(session_id)
                if not session:
                    raise ApiError(404, "Session not found")
                self.send_json(200, {"session": session})
                return
            self.send_static(path)
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/pin-indexes/"):
                medcom_index = unquote(path.split("/", 3)[3])
                if "/" in medcom_index:
                    raise ApiError(404, "Not found")
                if not db.remove_pin_index(medcom_index):
                    raise ApiError(404, "Pin index not found")
                self.send_json(200, {"ok": True, "pinIndexes": db.list_pin_indexes()})
                return
            if path.startswith("/api/projects/") and "/steps/" in path:
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                project = db.delete_step(project_id, step_id)
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return
            if path.startswith("/api/projects/"):
                project_id = path.split("/", 3)[3]
                if "/" in project_id:
                    raise ApiError(404, "Not found")
                if not db.delete_project(project_id):
                    raise ApiError(404, "Project not found")
                remove_project_uploads(project_id)
                self.send_json(200, {"ok": True})
                return
            raise ApiError(404, "Not found")
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/import/prepared-xlsx":
                fields, files = self.read_multipart()
                name = str(fields.get("name") or "").strip()
                if not name:
                    raise ApiError(400, "Project name is required")
                bom_file = files.get("bomFile")
                pp_file = files.get("ppFile")
                if not bom_file or not pp_file:
                    raise ApiError(400, "BOM XLSX and P&P XLSX files are required")
                project, summary = importer.import_prepared_project(
                    name=name,
                    board_width=parse_number(fields.get("boardWidth")),
                    board_height=parse_number(fields.get("boardHeight")),
                    bom_bytes=bytes(bom_file["content"]),
                    pp_bytes=bytes(pp_file["content"]),
                )
                board_image_path = save_board_image(project["id"], files.get("boardImage"))
                if board_image_path:
                    project = db.update_project_board_image(project["id"], board_image_path)
                self.send_json(201, {"project": project, "summary": summary})
                return

            if path.startswith("/api/projects/") and path.endswith("/board-image"):
                project_id = path.split("/")[3]
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                fields, files = self.read_multipart()
                board_image_path = save_board_image(project_id, files.get("boardImage"))
                if not board_image_path:
                    raise ApiError(400, "Board image file is required")
                project = db.update_project_board_image(project_id, board_image_path)
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/import/prepared-xlsx"):
                project_id = path.split("/")[3]
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                fields, files = self.read_multipart()
                bom_file = files.get("bomFile")
                pp_file = files.get("ppFile")
                if not bom_file or not pp_file:
                    raise ApiError(400, "BOM XLSX and P&P XLSX files are required")
                steps, points, summary = importer.prepare_prepared_import(
                    bom_bytes=bytes(bom_file["content"]),
                    pp_bytes=bytes(pp_file["content"]),
                )
                project = db.replace_project_import_data(
                    project_id,
                    steps=steps,
                    points=points,
                    summary=summary,
                )
                if not project:
                    raise ApiError(404, "Project not found")
                board_image_path = save_board_image(project_id, files.get("boardImage"))
                if board_image_path:
                    project = db.update_project_board_image(project_id, board_image_path)
                self.send_json(200, {"project": project, "summary": summary})
                return

            if path.startswith("/api/projects/") and path.endswith("/consolidate-pin-steps"):
                project_id = path.split("/")[3]
                project = db.consolidate_pin_steps(project_id)
                if not project:
                    raise ApiError(404, "Project not found")
                changed_groups = project.pop("consolidated_groups", 0)
                self.send_json(200, {"project": project, "changedGroups": changed_groups})
                return

            payload = self.read_json()

            if path.startswith("/api/projects/") and path.endswith("/steps/merge"):
                project_id = path.split("/")[3]
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    project = db.merge_steps(
                        project_id=project_id,
                        step_ids=list(payload.get("stepIds") or []),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path == "/api/pin-indexes":
                try:
                    pin_index = db.add_pin_index(
                        medcom_index=str(payload.get("medcomIndex") or ""),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                self.send_json(201, {"pinIndex": pin_index, "pinIndexes": db.list_pin_indexes()})
                return

            if path == "/api/projects":
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ApiError(400, "Project name is required")
                project = db.create_project(
                    name=name,
                    board_width=parse_number(payload.get("boardWidth")),
                    board_height=parse_number(payload.get("boardHeight")),
                )
                self.send_json(201, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/steps"):
                project_id = path.split("/")[3]
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                step = db.create_step(
                    project_id=project_id,
                    designators=str(payload.get("designators") or ""),
                    value=str(payload.get("value") or ""),
                    medcom_index=str(payload.get("medcomIndex") or ""),
                    quantity=parse_int(payload.get("quantity"), 1),
                    seconds=parse_number(payload.get("seconds")),
                )
                self.send_json(201, {"step": step})
                return

            if path.startswith("/api/projects/") and path.endswith("/split-units"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    project = db.split_step_units(
                        project_id=project_id,
                        step_id=step_id,
                        unit_indexes=list(payload.get("unitIndexes") or []),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/move-units"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    project = db.move_step_units(
                        project_id=project_id,
                        source_step_id=step_id,
                        target_step_id=parse_int(payload.get("targetStepId"), 0),
                        unit_indexes=list(payload.get("unitIndexes") or []),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/reorder"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    project = db.reorder_step(
                        project_id=project_id,
                        step_id=step_id,
                        direction=str(payload.get("direction") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/operator-feedback"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    project = db.record_operator_step(
                        project_id=project_id,
                        step_id=step_id,
                        status=str(payload.get("status") or ""),
                        note=str(payload.get("note") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(201, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/no-preparation"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                project = db.mark_step_no_preparation(
                    project_id=project_id,
                    step_id=step_id,
                    reason=str(payload.get("reason") or ""),
                )
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/notes"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                project = db.update_step_notes(
                    project_id=project_id,
                    step_id=step_id,
                    notes=str(payload.get("notes") or ""),
                )
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/skip"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                project = db.mark_step_skipped(
                    project_id=project_id,
                    step_id=step_id,
                    reason=str(payload.get("reason") or ""),
                )
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/unskip"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                project = db.unskip_step(project_id=project_id, step_id=step_id)
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/split-pins"):
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                try:
                    if payload.get("segments"):
                        project = db.split_step_into_pin_segments(
                            project_id=project_id,
                            step_id=step_id,
                            segments=list(payload.get("segments") or []),
                            technology_note=str(payload.get("technologyNote") or ""),
                        )
                    else:
                        project = db.split_step_into_pin_groups(
                            project_id=project_id,
                            step_id=step_id,
                            groups=list(payload.get("groups") or []),
                            technology_note=str(payload.get("technologyNote") or ""),
                        )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Step not found")
                project = db.consolidate_pin_steps(project_id) or project
                changed_groups = project.pop("consolidated_groups", 0)
                self.send_json(200, {"project": project, "changedGroups": changed_groups})
                return

            if path.startswith("/api/projects/") and path.endswith("/sessions"):
                project_id = path.split("/")[3]
                project = db.get_project(project_id)
                if not project:
                    raise ApiError(404, "Project not found")
                if project.get("status") not in {"ready", "active"}:
                    raise ApiError(409, "Projekt nie został jeszcze przekazany do operatora")
                session = db.create_session(
                    project_id=project_id,
                    operator_name=str(payload.get("operatorName") or ""),
                    station_name=str(payload.get("stationName") or ""),
                )
                self.send_json(201, {"session": session})
                return

            if path.startswith("/api/sessions/") and "/steps/" in path:
                parts = path.split("/")
                session_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_session(session_id):
                    raise ApiError(404, "Session not found")
                event = db.create_step_event(
                    session_id=session_id,
                    step_id=step_id,
                    status=str(payload.get("status") or "pending"),
                    note=str(payload.get("note") or ""),
                )
                self.send_json(201, {"event": event})
                return

            raise ApiError(404, "Not found")
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/projects/") and "/feedback/" in path:
                parts = path.split("/")
                project_id = parts[3]
                feedback_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                payload = self.read_json()
                try:
                    project = db.update_operator_feedback(
                        project_id=project_id,
                        feedback_id=feedback_id,
                        admin_status=str(payload.get("adminStatus") or ""),
                        admin_note=str(payload.get("adminNote") or ""),
                    )
                except ValueError as error:
                    raise ApiError(400, str(error)) from error
                if not project:
                    raise ApiError(404, "Feedback not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and "/steps/" in path:
                parts = path.split("/")
                project_id = parts[3]
                step_id = parse_int(parts[5])
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                payload = self.read_json()
                project = db.update_step_details(
                    project_id=project_id,
                    step_id=step_id,
                    value=str(payload.get("value") or ""),
                    medcom_index=str(payload.get("medcomIndex") or ""),
                    quantity=parse_int(payload.get("quantity"), 1),
                    notes=str(payload.get("notes") or ""),
                )
                if not project:
                    raise ApiError(404, "Step not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/") and path.endswith("/calibration"):
                project_id = path.split("/")[3]
                if "/" in project_id:
                    raise ApiError(404, "Not found")
                if not db.get_project(project_id):
                    raise ApiError(404, "Project not found")
                payload = self.read_json()
                project = db.update_project_board_calibration(
                    project_id,
                    {
                        "rotation": payload.get("rotation"),
                        "flipX": payload.get("flipX"),
                        "flipY": payload.get("flipY"),
                    },
                )
                if not project:
                    raise ApiError(404, "Project not found")
                self.send_json(200, {"project": project})
                return

            if path.startswith("/api/projects/"):
                project_id = path.split("/", 3)[3]
                if "/" in project_id:
                    raise ApiError(404, "Not found")
                payload = self.read_json()
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ApiError(400, "Project name is required")
                status = str(payload.get("status") or "draft").strip()
                if status not in PROJECT_STATUSES:
                    raise ApiError(400, "Invalid project status")
                project = db.update_project(
                    project_id,
                    name=name,
                    board_width=parse_number(payload.get("boardWidth")),
                    board_height=parse_number(payload.get("boardHeight")),
                    status=status,
                )
                if not project:
                    raise ApiError(404, "Project not found")
                self.send_json(200, {"project": project})
                return
            raise ApiError(404, "Not found")
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})


def main() -> None:
    db.init_db()
    server = ThreadingHTTPServer((HOST, PORT), PlatformHandler)
    print(f"MSX Inserter platform listening on http://{HOST}:{PORT}")
    print(f"Database: {db.db_path()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
