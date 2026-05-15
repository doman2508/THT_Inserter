from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


HOST = os.environ.get("INSERTER_REPORT_HOST", "127.0.0.1")
PORT = int(os.environ.get("INSERTER_REPORT_PORT", "8765"))
REPORT_DIR = Path(
    os.environ.get(
        "INSERTER_REPORT_DIR",
        r"\\DOKUMENTACJE\__NARZEDZIA__\Raporty_inserter",
    )
)
MAX_BODY_BYTES = 10 * 1024 * 1024


def safe_filename(value: str, fallback: str = "projekt") -> str:
    value = (value or fallback).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value or fallback


def status_label(status: str) -> str:
    return {
        "done": "Zrobione",
        "problem": "Problem",
        "skipped": "Pominiete",
        "pending": "Do zrobienia",
    }.get(status or "pending", status or "Do zrobienia")


def normalize_report(payload: dict) -> dict:
    project_name = str(payload.get("projectName") or "projekt")
    generated_at = str(payload.get("generatedAt") or datetime.now().isoformat(timespec="seconds"))
    elapsed_seconds = int(payload.get("elapsedSeconds") or 0)
    steps = payload.get("steps") or []
    if not isinstance(steps, list):
        steps = []

    return {
        "projectName": project_name,
        "generatedAt": generated_at,
        "elapsedSeconds": elapsed_seconds,
        "steps": steps,
    }


def write_csv(path: Path, report: dict) -> None:
    fieldnames = [
        "lp",
        "status",
        "uwagi_operatora",
        "desygnatory",
        "wartosc",
        "indeks_medcom",
        "ilosc",
        "sekundy",
    ]

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for step in report["steps"]:
            writer.writerow(
                {
                    "lp": step.get("lp", ""),
                    "status": status_label(str(step.get("status") or "pending")),
                    "uwagi_operatora": step.get("notes", ""),
                    "desygnatory": step.get("designators", ""),
                    "wartosc": step.get("value", ""),
                    "indeks_medcom": step.get("medcomIndex", ""),
                    "ilosc": step.get("quantity", ""),
                    "sekundy": step.get("seconds", ""),
                }
            )


def save_report(payload: dict) -> dict:
    report = normalize_report(payload)
    project_slug = safe_filename(report["projectName"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = REPORT_DIR / project_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{project_slug}_raport_operatora_{timestamp}"
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    write_csv(csv_path, report)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "csvPath": str(csv_path),
        "jsonPath": str(json_path),
    }


class ReportHandler(BaseHTTPRequestHandler):
    server_version = "MSXInserterReportServer/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self.send_json(200, {"ok": True, "reportDir": str(REPORT_DIR)})
            return
        self.send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/report":
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length") or "0")
            if content_length <= 0 or content_length > MAX_BODY_BYTES:
                self.send_json(413, {"ok": False, "error": "Invalid report size"})
                return

            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            result = save_report(payload)
            self.send_json(200, result)
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), ReportHandler)
    print(f"MSX Inserter report server listening on http://{HOST}:{PORT}")
    print(f"Reports directory: {REPORT_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
