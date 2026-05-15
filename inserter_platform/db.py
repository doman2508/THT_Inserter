from __future__ import annotations

import os
import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data") / "inserter_platform.db"
DEFAULT_PIN_INDEXES = (
    "M-ZLACZ-00015",
    "M-ZLACZ-00017",
    "M-ZLACZ-00018",
    "M-ZLACZ-00019",
    "M-ZLACZ-00020",
    "M-ZLACZ-01107",
)
DEFAULT_BOARD_CALIBRATION = {
    "rotation": 0,
    "flipX": False,
    "flipY": False,
}
OPERATOR_STEP_STATUSES = {"done", "problem", "skipped"}
OPERATOR_FEEDBACK_STATUSES = {"open", "in_progress", "fixed", "verified", "rejected"}


def db_path() -> Path:
    return Path(os.environ.get("INSERTER_PLATFORM_DB", DEFAULT_DB_PATH))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_medcom_index(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                board_width REAL,
                board_height REAL,
                board_image_path TEXT,
                board_calibration_json TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS placement_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                step_no INTEGER NOT NULL,
                designators TEXT NOT NULL,
                value TEXT NOT NULL,
                medcom_index TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                seconds REAL,
                notes TEXT NOT NULL DEFAULT '',
                segments_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operator_sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                operator_name TEXT NOT NULL DEFAULT '',
                station_name TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS step_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES operator_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES placement_steps(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operator_step_statuses (
                project_id TEXT NOT NULL,
                step_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, step_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES placement_steps(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operator_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                step_id INTEGER NOT NULL,
                feedback_type TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                admin_status TEXT NOT NULL DEFAULT 'open',
                admin_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES placement_steps(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operator_feedback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_id INTEGER NOT NULL,
                admin_status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(feedback_id) REFERENCES operator_feedback(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS component_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                designator TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                rotation REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, designator)
            );

            CREATE TABLE IF NOT EXISTS project_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pin_indexes (
                medcom_index TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_component_points_project
                ON component_points(project_id);

            CREATE INDEX IF NOT EXISTS idx_project_imports_project
                ON project_imports(project_id);

            CREATE INDEX IF NOT EXISTS idx_project_changes_project
                ON project_changes(project_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_operator_feedback_project
                ON operator_feedback(project_id, admin_status, created_at);
            """
        )
        project_columns = {row["name"] for row in db.execute("PRAGMA table_info(projects)").fetchall()}
        if "board_image_path" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN board_image_path TEXT")
        if "board_calibration_json" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN board_calibration_json TEXT NOT NULL DEFAULT ''")
        step_columns = {row["name"] for row in db.execute("PRAGMA table_info(placement_steps)").fetchall()}
        if "segments_json" not in step_columns:
            db.execute("ALTER TABLE placement_steps ADD COLUMN segments_json TEXT NOT NULL DEFAULT ''")
        timestamp = now_iso()
        db.executemany(
            """
            INSERT OR IGNORE INTO pin_indexes (medcom_index, note, active, created_at, updated_at)
            VALUES (?, '', 1, ?, ?)
            """,
            [(medcom_index, timestamp, timestamp) for medcom_index in DEFAULT_PIN_INDEXES],
        )


def list_pin_indexes() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT medcom_index, note, active, created_at, updated_at
            FROM pin_indexes
            WHERE active = 1
            ORDER BY medcom_index
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_pin_index(medcom_index: str, note: str = "") -> dict[str, Any]:
    clean_index = normalize_medcom_index(medcom_index)
    if not clean_index:
        raise ValueError("Indeks Medcom jest wymagany")

    timestamp = now_iso()
    with connect() as db:
        existing = db.execute(
            "SELECT medcom_index FROM pin_indexes WHERE medcom_index = ?",
            (clean_index,),
        ).fetchone()
        if existing:
            db.execute(
                """
                UPDATE pin_indexes
                SET note = ?, active = 1, updated_at = ?
                WHERE medcom_index = ?
                """,
                (note.strip(), timestamp, clean_index),
            )
        else:
            db.execute(
                """
                INSERT INTO pin_indexes (medcom_index, note, active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (clean_index, note.strip(), timestamp, timestamp),
            )
        row = db.execute(
            """
            SELECT medcom_index, note, active, created_at, updated_at
            FROM pin_indexes
            WHERE medcom_index = ?
            """,
            (clean_index,),
        ).fetchone()
    return dict(row)


def remove_pin_index(medcom_index: str) -> bool:
    clean_index = normalize_medcom_index(medcom_index)
    timestamp = now_iso()
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE pin_indexes
            SET active = 0, updated_at = ?
            WHERE medcom_index = ? AND active = 1
            """,
            (timestamp, clean_index),
        )
        return cursor.rowcount > 0


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def normalize_board_calibration(value: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}

    rotation = int(value.get("rotation") or 0)
    if rotation not in {0, 90, 180, 270}:
        rotation = 0

    return {
        "rotation": rotation,
        "flipX": bool(value.get("flipX")),
        "flipY": bool(value.get("flipY")),
    }


def project_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    project = row_to_dict(row)
    if project is None:
        return None
    project["board_calibration"] = normalize_board_calibration(project.get("board_calibration_json"))
    project.pop("board_calibration_json", None)
    return project


def step_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    raw_segments = item.get("segments_json") or ""
    try:
        item["segments"] = json.loads(raw_segments) if raw_segments else []
    except json.JSONDecodeError:
        item["segments"] = []
    return item


def split_designators(value: str) -> list[str]:
    return [item.upper() for item in re.split(r"[,\s;+]+", value or "") if item.strip()]


def normalize_line_key(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().upper()


def append_project_change(
    db: sqlite3.Connection,
    project_id: str,
    change_type: str,
    description: str,
    timestamp: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO project_changes (project_id, change_type, description, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, change_type.strip(), description.strip(), timestamp or now_iso()),
    )


def step_units_from_row(row: sqlite3.Row | dict[str, Any]) -> list[dict[str, Any]]:
    segments = step_segments_from_row(row)
    if segments:
        units: list[dict[str, Any]] = []
        for segment in segments:
            designators = [
                str(designator).strip().upper()
                for designator in segment.get("designators", [])
                if str(designator).strip()
            ]
            if not designators:
                continue
            label = str(segment.get("label") or "+".join(designators)).strip()
            units.append(
                {
                    "pinCount": int(segment.get("pinCount") or 0),
                    "designators": list(dict.fromkeys(designators)),
                    "quantity": int(segment.get("quantity") or 1),
                    "label": label,
                }
            )
        return units

    return [
        {
            "pinCount": 0,
            "designators": [designator],
            "quantity": 1,
            "label": designator,
        }
        for designator in split_designators(str(dict(row).get("designators") or ""))
    ]


def selected_units(units: list[dict[str, Any]], indexes: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean_indexes = {
        int(index)
        for index in indexes
        if str(index).strip() and str(index).strip().lstrip("-").isdigit()
    }
    if not clean_indexes:
        raise ValueError("Wybierz przynajmniej jedna sztuke/odcinek.")
    if min(clean_indexes) < 0 or max(clean_indexes) >= len(units):
        raise ValueError("Wybor zawiera nieistniejacy odcinek.")
    picked = [unit for index, unit in enumerate(units) if index in clean_indexes]
    remaining = [unit for index, unit in enumerate(units) if index not in clean_indexes]
    return picked, remaining


def line_fields_from_units(
    row: sqlite3.Row | dict[str, Any],
    units: list[dict[str, Any]],
    *,
    value: str | None = None,
    medcom_index: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    source = dict(row)
    clean_units = [
        {
            "pinCount": int(unit.get("pinCount") or 0),
            "designators": [
                str(designator).strip().upper()
                for designator in unit.get("designators", [])
                if str(designator).strip()
            ],
            "quantity": max(1, int(unit.get("quantity") or 1)),
            "label": str(unit.get("label") or "").strip(),
        }
        for unit in units
        if unit.get("designators")
    ]
    designators: list[str] = []
    for unit in clean_units:
        unit["designators"] = list(dict.fromkeys(unit["designators"]))
        if not unit["label"]:
            unit["label"] = "+".join(unit["designators"])
        designators.extend(unit["designators"])
    designators = list(dict.fromkeys(designators))

    has_segments = any(
        len(unit["designators"]) > 1
        or unit["pinCount"] > 0
        or unit["label"] != unit["designators"][0]
        or unit["quantity"] != 1
        for unit in clean_units
    )
    clean_notes = str(notes if notes is not None else source.get("notes") or "").strip()
    if not has_segments:
        clean_notes = note_without_segments(clean_notes)

    return {
        "designators": ",".join(designators),
        "value": str(value if value is not None else source.get("value") or "").strip(),
        "medcom_index": str(medcom_index if medcom_index is not None else source.get("medcom_index") or "").strip(),
        "quantity": sum(int(unit.get("quantity") or 1) for unit in clean_units) or len(designators) or 1,
        "notes": clean_notes,
        "segments_json": json.dumps(clean_units, ensure_ascii=False) if has_segments else "",
    }


def pin_counts_from_value(value: str) -> list[int]:
    return [
        int(match.group(1))
        for match in re.finditer(r"\b(\d+)\s*PIN\b", value or "", flags=re.IGNORECASE)
        if int(match.group(1)) > 0
    ]


def step_segments_from_row(row: sqlite3.Row | dict[str, Any]) -> list[dict[str, Any]]:
    item = dict(row)
    raw_segments = item.get("segments_json") or ""
    if raw_segments:
        try:
            segments = json.loads(raw_segments)
            if isinstance(segments, list):
                return [
                    {
                        "pinCount": int(segment.get("pinCount") or 0),
                        "designators": [
                            str(designator).strip().upper()
                            for designator in segment.get("designators", [])
                            if str(designator).strip()
                        ],
                        "quantity": int(segment.get("quantity") or 1),
                        "label": str(segment.get("label") or "").strip(),
                    }
                    for segment in segments
                    if isinstance(segment, dict)
                ]
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    notes = str(item.get("notes") or "")
    match = re.search(r"Odcinki:\s*(.+)$", notes, flags=re.IGNORECASE)
    if not match:
        return []
    labels = [part.strip() for part in match.group(1).split(";") if part.strip()]
    counts = pin_counts_from_value(str(item.get("value") or ""))
    use_inner_pin_count = (
        bool(labels)
        and len(counts) > 1
        and counts[0] == 1
        and counts[1] > 1
        and all(len(split_designators(label)) == 1 for label in labels)
    )
    pin_count = counts[1] if use_inner_pin_count else (counts[0] if counts else 0)
    segments = []
    for label in labels:
        designators = split_designators(label)
        if designators:
            segments.append(
                {
                    "pinCount": pin_count,
                    "designators": designators,
                    "quantity": 1,
                    "label": label,
                }
            )
    return segments


def step_pin_count_from_values(value: str, segments: list[dict[str, Any]]) -> int:
    counts = pin_counts_from_value(value)
    if not counts:
        return 0
    can_use_inner_value = (
        len(counts) > 1
        and counts[0] == 1
        and counts[1] > 1
        and segments
        and all(len(segment.get("designators") or []) == 1 for segment in segments)
    )
    return counts[1] if can_use_inner_value else counts[0]


def note_without_segments(notes: str) -> str:
    return re.sub(r"\s*\|\s*Odcinki:\s*.+$", "", notes or "", flags=re.IGNORECASE).strip()


def row_pin_segments_for_consolidation(row: sqlite3.Row | dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    item = dict(row)
    segments = step_segments_from_row(item)
    if segments:
        pin_count = step_pin_count_from_values(str(item.get("value") or ""), segments)
        return pin_count, segments

    counts = pin_counts_from_value(str(item.get("value") or ""))
    if not counts:
        return 0, []
    pin_count = counts[0]
    designators = split_designators(str(item.get("designators") or ""))
    return pin_count, [
        {
            "pinCount": pin_count,
            "designators": [designator],
            "quantity": 1,
            "label": designator,
        }
        for designator in designators
    ]


def create_project(name: str, board_width: float | None, board_height: float | None) -> dict[str, Any]:
    project_id = str(uuid.uuid4())
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            """
            INSERT INTO projects (id, name, board_width, board_height, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'draft', ?, ?)
            """,
            (project_id, name.strip(), board_width, board_height, timestamp, timestamp),
        )
    project = get_project(project_id)
    assert project is not None
    return project


def list_projects() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM placement_steps s WHERE s.project_id = p.id) AS step_count,
                   (SELECT COUNT(*) FROM component_points cp WHERE cp.project_id = p.id) AS point_count,
                   (SELECT COUNT(*) FROM operator_feedback f WHERE f.project_id = p.id AND f.admin_status IN ('open', 'in_progress')) AS open_feedback_count
            FROM projects p
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    projects = [project_row_to_dict(row) for row in rows]
    return [project for project in projects if project is not None]


def get_project(project_id: str) -> dict[str, Any] | None:
    with connect() as db:
        project = project_row_to_dict(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
        if not project:
            return None
        project["steps"] = [
            step_row_to_dict(row)
            for row in db.execute(
                "SELECT * FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
                (project_id,),
            ).fetchall()
        ]
        project["points"] = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM component_points WHERE project_id = ? ORDER BY designator",
                (project_id,),
            ).fetchall()
        ]
        project["operator_step_statuses"] = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM operator_step_statuses WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        ]
        project["operator_feedback"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT f.*,
                       s.step_no,
                       s.designators,
                       s.value,
                       s.medcom_index,
                       s.quantity
                FROM operator_feedback f
                JOIN placement_steps s ON s.id = f.step_id
                WHERE f.project_id = ?
                ORDER BY
                    CASE f.admin_status
                        WHEN 'open' THEN 0
                        WHEN 'in_progress' THEN 1
                        WHEN 'fixed' THEN 2
                        WHEN 'verified' THEN 3
                        ELSE 4
                    END,
                    f.created_at DESC,
                    f.id DESC
                """,
                (project_id,),
            ).fetchall()
        ]
        feedback_ids = [item["id"] for item in project["operator_feedback"]]
        histories: dict[int, list[dict[str, Any]]] = {feedback_id: [] for feedback_id in feedback_ids}
        if feedback_ids:
            placeholders = ",".join("?" for _ in feedback_ids)
            for row in db.execute(
                f"""
                SELECT *
                FROM operator_feedback_history
                WHERE feedback_id IN ({placeholders})
                ORDER BY created_at, id
                """,
                feedback_ids,
            ).fetchall():
                histories[int(row["feedback_id"])].append(dict(row))
        for item in project["operator_feedback"]:
            item["history"] = histories.get(int(item["id"]), [])
        project["imports"] = []
        for row in db.execute(
            "SELECT * FROM project_imports WHERE project_id = ? ORDER BY created_at DESC, id DESC",
            (project_id,),
        ).fetchall():
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json"))
            project["imports"].append(item)
        project["changes"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM project_changes
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (project_id,),
            ).fetchall()
        ]
    return project


def create_project_from_import(
    *,
    name: str,
    board_width: float | None,
    board_height: float | None,
    steps: list[dict[str, Any]],
    points: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    project_id = str(uuid.uuid4())
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            """
            INSERT INTO projects (id, name, board_width, board_height, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'imported', ?, ?)
            """,
            (project_id, name.strip(), board_width, board_height, timestamp, timestamp),
        )
        db.executemany(
            """
            INSERT INTO placement_steps
                (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    project_id,
                    int(step["step_no"]),
                    str(step["designators"]).strip(),
                    str(step["value"]).strip(),
                    str(step["medcom_index"]).strip(),
                    int(step["quantity"] or 1),
                    step.get("seconds"),
                    str(step.get("notes") or "").strip(),
                    timestamp,
                    timestamp,
                )
                for step in steps
            ],
        )
        db.executemany(
            """
            INSERT INTO component_points (project_id, designator, x, y, rotation, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    project_id,
                    str(point["designator"]).strip(),
                    float(point["x"]),
                    float(point["y"]),
                    point.get("rotation"),
                    timestamp,
                )
                for point in points
            ],
        )
        db.execute(
            """
            INSERT INTO project_imports (project_id, source_type, summary_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                project_id,
                str(summary.get("sourceType") or "prepared-xlsx"),
                json.dumps(summary, ensure_ascii=False),
                timestamp,
            ),
        )
    project = get_project(project_id)
    assert project is not None
    return project


def update_project_board_image(project_id: str, board_image_path: str) -> dict[str, Any]:
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            """
            UPDATE projects
            SET board_image_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (board_image_path, timestamp, project_id),
        )
    project = get_project(project_id)
    assert project is not None
    return project


def update_project_board_calibration(project_id: str, calibration: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = now_iso()
    clean_calibration = normalize_board_calibration(calibration)
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE projects
            SET board_calibration_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(clean_calibration, ensure_ascii=False), timestamp, project_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_project(project_id)


def update_project(
    project_id: str,
    *,
    name: str,
    board_width: float | None,
    board_height: float | None,
    status: str,
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE projects
            SET name = ?, board_width = ?, board_height = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (name.strip(), board_width, board_height, status.strip(), timestamp, project_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    with connect() as db:
        cursor = db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cursor.rowcount > 0


def replace_project_import_data(
    project_id: str,
    *,
    steps: list[dict[str, Any]],
    points: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        if db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            return None
        db.execute("DELETE FROM placement_steps WHERE project_id = ?", (project_id,))
        db.execute("DELETE FROM component_points WHERE project_id = ?", (project_id,))
        db.executemany(
            """
            INSERT INTO placement_steps
                (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    project_id,
                    int(step["step_no"]),
                    str(step["designators"]).strip(),
                    str(step["value"]).strip(),
                    str(step["medcom_index"]).strip(),
                    int(step["quantity"] or 1),
                    step.get("seconds"),
                    str(step.get("notes") or "").strip(),
                    timestamp,
                    timestamp,
                )
                for step in steps
            ],
        )
        db.executemany(
            """
            INSERT INTO component_points (project_id, designator, x, y, rotation, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    project_id,
                    str(point["designator"]).strip(),
                    float(point["x"]),
                    float(point["y"]),
                    point.get("rotation"),
                    timestamp,
                )
                for point in points
            ],
        )
        db.execute(
            """
            INSERT INTO project_imports (project_id, source_type, summary_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                project_id,
                str(summary.get("sourceType") or "prepared-xlsx"),
                json.dumps(summary, ensure_ascii=False),
                timestamp,
            ),
        )
        db.execute(
            "UPDATE projects SET status = 'imported', updated_at = ? WHERE id = ?",
            (timestamp, project_id),
        )
    return get_project(project_id)


def create_step(
    project_id: str,
    designators: str,
    value: str,
    medcom_index: str,
    quantity: int,
    seconds: float | None,
) -> dict[str, Any]:
    timestamp = now_iso()
    with connect() as db:
        current_max = db.execute(
            "SELECT COALESCE(MAX(step_no), 0) FROM placement_steps WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        cursor = db.execute(
            """
            INSERT INTO placement_steps
                (project_id, step_no, designators, value, medcom_index, quantity, seconds, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                int(current_max) + 1,
                designators.strip(),
                value.strip(),
                medcom_index.strip(),
                int(quantity or 1),
                seconds,
                timestamp,
                timestamp,
            ),
        )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
        step_id = cursor.lastrowid
        row = db.execute("SELECT * FROM placement_steps WHERE id = ?", (step_id,)).fetchone()
    return step_row_to_dict(row)


def update_step_notes(project_id: str, step_id: int, notes: str) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE placement_steps
            SET notes = ?, updated_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (notes.strip(), timestamp, project_id, step_id),
        )
        if cursor.rowcount == 0:
            return None
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def mark_step_skipped(project_id: str, step_id: int, reason: str = "") -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        note_parts = [
            item.strip()
            for item in str(step["notes"] or "").split("|")
            if item.strip() and item.strip() != "Pominięte w montażu"
        ]
        note_parts.append("Pominięte w montażu")
        if reason.strip():
            note_parts.append(reason.strip())
        db.execute(
            """
            UPDATE placement_steps
            SET notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (" | ".join(note_parts), timestamp, step_id),
        )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def delete_step(project_id: str, step_id: int) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        cursor = db.execute(
            "DELETE FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        )
        if cursor.rowcount == 0:
            return None
        remaining = db.execute(
            "SELECT id FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
            (project_id,),
        ).fetchall()
        db.executemany(
            "UPDATE placement_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            [(index + 1, timestamp, row["id"]) for index, row in enumerate(remaining)],
        )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def update_step_details(
    project_id: str,
    step_id: int,
    *,
    value: str,
    medcom_index: str,
    quantity: int,
    notes: str,
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        cursor = db.execute(
            """
            UPDATE placement_steps
            SET value = ?,
                medcom_index = ?,
                quantity = ?,
                notes = ?,
                updated_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                value.strip(),
                medcom_index.strip(),
                max(1, int(quantity or 1)),
                notes.strip(),
                timestamp,
                project_id,
                step_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        append_project_change(db, project_id, "step_edit", f"Edytowano linie {step['step_no']}.", timestamp)
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def reorder_step(project_id: str, step_id: int, direction: str) -> dict[str, Any] | None:
    clean_direction = (direction or "").strip().lower()
    if clean_direction not in {"up", "down"}:
        raise ValueError("Nieprawidlowy kierunek.")

    timestamp = now_iso()
    with connect() as db:
        rows = db.execute(
            "SELECT id, step_no FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
            (project_id,),
        ).fetchall()
        if not rows and db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            return None
        index = next((position for position, row in enumerate(rows) if int(row["id"]) == int(step_id)), -1)
        if index < 0:
            return None
        swap_index = index - 1 if clean_direction == "up" else index + 1
        if swap_index < 0 or swap_index >= len(rows):
            return get_project(project_id)
        rows[index], rows[swap_index] = rows[swap_index], rows[index]
        db.executemany(
            "UPDATE placement_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            [(position + 1, timestamp, row["id"]) for position, row in enumerate(rows)],
        )
        append_project_change(db, project_id, "step_reorder", "Zmieniono kolejnosc linii montazowych.", timestamp)
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def unskip_step(project_id: str, step_id: int) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        note_parts = [
            item.strip()
            for item in str(step["notes"] or "").split("|")
            if item.strip() and item.strip() != "PominiÄ™te w montaĹĽu"
        ]
        db.execute(
            """
            UPDATE placement_steps
            SET notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (" | ".join(note_parts), timestamp, step_id),
        )
        append_project_change(db, project_id, "step_unskip", f"Przywrocono linie {step['step_no']} do montazu.", timestamp)
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def split_step_units(
    project_id: str,
    step_id: int,
    unit_indexes: list[Any],
    note: str = "",
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        units = step_units_from_row(step)
        picked_units, remaining_units = selected_units(units, unit_indexes)
        if not remaining_units:
            raise ValueError("Nie mozna rozdzielic calej linii. Do tego uzyj scalania/przenoszenia.")

        source_fields = line_fields_from_units(step, remaining_units)
        target_note = note_without_segments(str(step["notes"] or ""))
        note_parts = [part.strip() for part in target_note.split("|") if part.strip()]
        note_parts.append("Rozdzielone w edycji PRO")
        if note.strip():
            note_parts.append(note.strip())
        target_fields = line_fields_from_units(step, picked_units, notes=" | ".join(dict.fromkeys(note_parts)))

        original_step_no = int(step["step_no"])
        db.execute(
            """
            UPDATE placement_steps
            SET designators = ?,
                quantity = ?,
                notes = ?,
                segments_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                source_fields["designators"],
                source_fields["quantity"],
                source_fields["notes"],
                source_fields["segments_json"],
                timestamp,
                step_id,
            ),
        )
        db.execute(
            """
            UPDATE placement_steps
            SET step_no = step_no + 1, updated_at = ?
            WHERE project_id = ? AND step_no > ?
            """,
            (timestamp, project_id, original_step_no),
        )
        db.execute(
            """
            INSERT INTO placement_steps
                (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes, segments_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                original_step_no + 1,
                target_fields["designators"],
                target_fields["value"],
                target_fields["medcom_index"],
                target_fields["quantity"],
                step["seconds"],
                target_fields["notes"],
                target_fields["segments_json"],
                timestamp,
                timestamp,
            ),
        )
        append_project_change(
            db,
            project_id,
            "step_split",
            f"Rozdzielono linie {step['step_no']}: {target_fields['designators']}.",
            timestamp,
        )
        db.execute("UPDATE projects SET status = 'prepared', updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def move_step_units(
    project_id: str,
    source_step_id: int,
    target_step_id: int,
    unit_indexes: list[Any],
    note: str = "",
) -> dict[str, Any] | None:
    if int(source_step_id) == int(target_step_id):
        raise ValueError("Wybierz inna linie docelowa.")

    timestamp = now_iso()
    with connect() as db:
        source = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, source_step_id),
        ).fetchone()
        target = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, target_step_id),
        ).fetchone()
        if source is None or target is None:
            return None
        if normalize_line_key(source["value"]) != normalize_line_key(target["value"]):
            raise ValueError("Linie maja rozne wartosci. Najpierw ujednolic opis albo rozdziel do nowej linii.")
        if normalize_medcom_index(source["medcom_index"]) != normalize_medcom_index(target["medcom_index"]):
            raise ValueError("Linie maja rozne indeksy Medcom.")

        picked_units, remaining_units = selected_units(step_units_from_row(source), unit_indexes)
        source_fields = line_fields_from_units(source, remaining_units) if remaining_units else None
        target_units = [*step_units_from_row(target), *picked_units]
        target_note = note_without_segments(str(target["notes"] or ""))
        if note.strip():
            target_note = " | ".join([part for part in [target_note, note.strip()] if part])
        target_fields = line_fields_from_units(target, target_units, notes=target_note)

        if source_fields:
            db.execute(
                """
                UPDATE placement_steps
                SET designators = ?,
                    quantity = ?,
                    notes = ?,
                    segments_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_fields["designators"],
                    source_fields["quantity"],
                    source_fields["notes"],
                    source_fields["segments_json"],
                    timestamp,
                    source_step_id,
                ),
            )
        else:
            db.execute("DELETE FROM placement_steps WHERE id = ?", (source_step_id,))
        db.execute(
            """
            UPDATE placement_steps
            SET designators = ?,
                quantity = ?,
                notes = ?,
                segments_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                target_fields["designators"],
                target_fields["quantity"],
                target_fields["notes"],
                target_fields["segments_json"],
                timestamp,
                target_step_id,
            ),
        )
        append_project_change(
            db,
            project_id,
            "step_move_units",
            f"Przeniesiono {line_fields_from_units(source, picked_units)['designators']} z linii {source['step_no']} do {target['step_no']}.",
            timestamp,
        )
        if not source_fields:
            remaining_rows = db.execute(
                "SELECT id FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
                (project_id,),
            ).fetchall()
            db.executemany(
                "UPDATE placement_steps SET step_no = ?, updated_at = ? WHERE id = ?",
                [(index + 1, timestamp, row["id"]) for index, row in enumerate(remaining_rows)],
            )
        db.execute("UPDATE projects SET status = 'prepared', updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def merge_steps(project_id: str, step_ids: list[Any], note: str = "") -> dict[str, Any] | None:
    clean_ids = list(dict.fromkeys(int(step_id) for step_id in step_ids if str(step_id).strip().isdigit()))
    if len(clean_ids) < 2:
        raise ValueError("Wybierz przynajmniej dwie linie do scalenia.")

    timestamp = now_iso()
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM placement_steps
            WHERE project_id = ? AND id IN ({",".join("?" for _ in clean_ids)})
            ORDER BY step_no, id
            """,
            [project_id, *clean_ids],
        ).fetchall()
        if len(rows) != len(clean_ids):
            return None

        first = rows[0]
        value_key = normalize_line_key(first["value"])
        medcom_key = normalize_medcom_index(first["medcom_index"])
        for row in rows[1:]:
            if normalize_line_key(row["value"]) != value_key:
                raise ValueError("Scalane linie musza miec te sama wartosc.")
            if normalize_medcom_index(row["medcom_index"]) != medcom_key:
                raise ValueError("Scalane linie musza miec ten sam indeks Medcom.")

        merged_units: list[dict[str, Any]] = []
        note_parts: list[str] = []
        for row in rows:
            merged_units.extend(step_units_from_row(row))
            for part in [item.strip() for item in note_without_segments(str(row["notes"] or "")).split("|") if item.strip()]:
                if part not in note_parts:
                    note_parts.append(part)
        note_parts.append("Scalone w edycji PRO")
        if note.strip():
            note_parts.append(note.strip())
        fields = line_fields_from_units(first, merged_units, notes=" | ".join(dict.fromkeys(note_parts)))

        db.execute(
            """
            UPDATE placement_steps
            SET designators = ?,
                quantity = ?,
                notes = ?,
                segments_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                fields["designators"],
                fields["quantity"],
                fields["notes"],
                fields["segments_json"],
                timestamp,
                first["id"],
            ),
        )
        duplicate_ids = [row["id"] for row in rows[1:]]
        db.executemany("DELETE FROM placement_steps WHERE id = ?", [(row_id,) for row_id in duplicate_ids])
        remaining = db.execute(
            "SELECT id FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
            (project_id,),
        ).fetchall()
        db.executemany(
            "UPDATE placement_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            [(index + 1, timestamp, row["id"]) for index, row in enumerate(remaining)],
        )
        append_project_change(
            db,
            project_id,
            "step_merge",
            f"Scalono {len(rows)} linie: {fields['designators']}.",
            timestamp,
        )
        db.execute("UPDATE projects SET status = 'prepared', updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def mark_step_no_preparation(project_id: str, step_id: int, reason: str = "") -> dict[str, Any] | None:
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        note_parts = [
            item.strip()
            for item in str(step["notes"] or "").split("|")
            if item.strip() and item.strip() != "Bez przygotowania"
        ]
        note_parts.append("Bez przygotowania")
        if reason.strip():
            note_parts.append(reason.strip())
        db.execute(
            """
            UPDATE placement_steps
            SET notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (" | ".join(note_parts), timestamp, step_id),
        )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def split_step_into_pin_segments(
    project_id: str,
    step_id: int,
    segments: list[dict[str, Any]],
    technology_note: str = "",
) -> dict[str, Any] | None:
    clean_segments: list[dict[str, Any]] = []
    seen_designators: set[str] = set()
    for segment in segments:
        designators = [
            str(designator).strip().upper()
            for designator in segment.get("designators", [])
            if str(designator).strip()
        ]
        designators = list(dict.fromkeys(designators))
        pin_count = int(segment.get("pinCount") or 0)
        quantity = int(segment.get("quantity") or 1)
        if pin_count <= 0 or not designators:
            continue
        if quantity <= 0:
            quantity = 1
        for designator in designators:
            if designator in seen_designators:
                raise ValueError(f"Desygnator {designator} jest przypisany wiecej niz raz.")
            seen_designators.add(designator)
        clean_segments.append({"pin_count": pin_count, "designators": designators, "quantity": quantity})

    if not clean_segments:
        raise ValueError("Brak poprawnych odcinkow do rozbicia.")

    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None

        original_designators = {
            designator.strip().upper()
            for designator in str(step["designators"]).split(",")
            if designator.strip()
        }
        unknown_designators = seen_designators - original_designators
        if unknown_designators:
            unknown = ", ".join(sorted(unknown_designators))
            raise ValueError(f"Desygnatory spoza oryginalnej linii: {unknown}")
        missing_designators = original_designators - seen_designators
        if missing_designators:
            missing = ", ".join(sorted(missing_designators))
            raise ValueError(f"Nie przypisano wszystkich desygnatorow: {missing}")

        grouped_segments: dict[int, dict[str, Any]] = {}
        ordered_pin_counts: list[int] = []
        for segment in clean_segments:
            pin_count = segment["pin_count"]
            if pin_count not in grouped_segments:
                grouped_segments[pin_count] = {
                    "designators": [],
                    "quantity": 0,
                    "segment_labels": [],
                    "segments": [],
                }
                ordered_pin_counts.append(pin_count)
            grouped_segments[pin_count]["designators"].extend(segment["designators"])
            grouped_segments[pin_count]["quantity"] += segment["quantity"]
            grouped_segments[pin_count]["segment_labels"].append("+".join(segment["designators"]))
            grouped_segments[pin_count]["segments"].append(
                {
                    "pinCount": pin_count,
                    "designators": segment["designators"],
                    "quantity": segment["quantity"],
                    "label": "+".join(segment["designators"]),
                }
            )

        note_parts = ["Rozbite w przygotowaniu produkcji"]
        if technology_note.strip():
            note_parts.append(technology_note.strip())

        original_step_no = int(step["step_no"])
        db.execute("DELETE FROM placement_steps WHERE id = ?", (step_id,))
        db.execute(
            """
            UPDATE placement_steps
            SET step_no = step_no + ?, updated_at = ?
            WHERE project_id = ? AND step_no > ?
            """,
            (len(ordered_pin_counts) - 1, timestamp, project_id, original_step_no),
        )
        for offset, pin_count in enumerate(ordered_pin_counts):
            group = grouped_segments[pin_count]
            designators = group["designators"]
            value = f"{pin_count} PIN"
            line_note = " | ".join([*note_parts, f"Odcinki: {'; '.join(group['segment_labels'])}"])
            segments_json = json.dumps(group["segments"], ensure_ascii=False)
            db.execute(
                """
                INSERT INTO placement_steps
                    (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes, segments_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    original_step_no + offset,
                    ",".join(designators),
                    value,
                    step["medcom_index"],
                    group["quantity"],
                    step["seconds"],
                    line_note,
                    segments_json,
                    timestamp,
                    timestamp,
                ),
            )
        db.execute(
            """
            UPDATE projects
            SET status = 'prepared', updated_at = ?
            WHERE id = ?
            """,
            (timestamp, project_id),
        )
    return get_project(project_id)


def split_step_into_pin_groups(
    project_id: str,
    step_id: int,
    groups: list[dict[str, Any]],
    technology_note: str = "",
) -> dict[str, Any] | None:
    segments: list[dict[str, Any]] = []
    for group in groups:
        designators = [
            str(designator).strip().upper()
            for designator in group.get("designators", [])
            if str(designator).strip()
        ]
        pin_count = int(group.get("pinCount") or 0)
        if pin_count <= 0 or not designators:
            continue
        segments.append({"pinCount": pin_count, "designators": designators, "quantity": len(designators)})
    return split_step_into_pin_segments(
        project_id=project_id,
        step_id=step_id,
        segments=segments,
        technology_note=technology_note,
    )


def consolidate_pin_steps(project_id: str) -> dict[str, Any] | None:
    timestamp = now_iso()
    changed_groups = 0
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
            (project_id,),
        ).fetchall()
        if not rows and db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            return None

        groups: dict[tuple[str, int], list[sqlite3.Row]] = {}
        for row in rows:
            pin_count, segments = row_pin_segments_for_consolidation(row)
            if not segments:
                continue
            if pin_count <= 0:
                continue
            key = (str(row["medcom_index"] or "").strip().upper(), pin_count)
            groups.setdefault(key, []).append(row)

        for (medcom_index, pin_count), group_rows in groups.items():
            if len(group_rows) < 2:
                continue

            changed_groups += 1
            primary = group_rows[0]
            merged_segments: list[dict[str, Any]] = []
            merged_designators: list[str] = []
            note_parts: list[str] = ["Rozbite w przygotowaniu produkcji"]
            for row in group_rows:
                note = note_without_segments(str(row["notes"] or ""))
                for part in [item.strip() for item in note.split("|") if item.strip()]:
                    if part and part not in note_parts:
                        note_parts.append(part)
                _, row_segments = row_pin_segments_for_consolidation(row)
                for segment in row_segments:
                    designators = [
                        str(designator).strip().upper()
                        for designator in segment.get("designators", [])
                        if str(designator).strip()
                    ]
                    if not designators:
                        continue
                    merged_designators.extend(designators)
                    merged_segments.append(
                        {
                            "pinCount": pin_count,
                            "designators": designators,
                            "quantity": int(segment.get("quantity") or 1),
                            "label": segment.get("label") or "+".join(designators),
                        }
                    )

            merged_designators = list(dict.fromkeys(merged_designators))
            segments_json = json.dumps(merged_segments, ensure_ascii=False)
            quantity = sum(int(segment.get("quantity") or 1) for segment in merged_segments)
            db.execute(
                """
                UPDATE placement_steps
                SET designators = ?,
                    value = ?,
                    medcom_index = ?,
                    quantity = ?,
                    notes = ?,
                    segments_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    ",".join(merged_designators),
                    f"{pin_count} PIN",
                    medcom_index,
                    quantity,
                    " | ".join(note_parts),
                    segments_json,
                    timestamp,
                    primary["id"],
                ),
            )
            duplicate_ids = [row["id"] for row in group_rows[1:]]
            db.executemany("DELETE FROM placement_steps WHERE id = ?", [(row_id,) for row_id in duplicate_ids])

        if changed_groups:
            remaining = db.execute(
                "SELECT id FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
                (project_id,),
            ).fetchall()
            db.executemany(
                "UPDATE placement_steps SET step_no = ?, updated_at = ? WHERE id = ?",
                [(index + 1, timestamp, row["id"]) for index, row in enumerate(remaining)],
            )
            db.execute(
                "UPDATE projects SET status = 'prepared', updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
    project = get_project(project_id)
    if project is None:
        return None
    project["consolidated_groups"] = changed_groups
    return project


def record_operator_step(project_id: str, step_id: int, status: str, note: str) -> dict[str, Any] | None:
    clean_status = (status or "").strip().lower()
    if clean_status not in OPERATOR_STEP_STATUSES:
        raise ValueError("Nieprawidlowy status operatora")

    clean_note = (note or "").strip()
    timestamp = now_iso()
    with connect() as db:
        step = db.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? AND id = ?",
            (project_id, step_id),
        ).fetchone()
        if step is None:
            return None
        db.execute(
            """
            INSERT INTO operator_step_statuses (project_id, step_id, status, note, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, step_id) DO UPDATE SET
                status = excluded.status,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (project_id, step_id, clean_status, clean_note, timestamp),
        )

        should_create_feedback = clean_status in {"problem", "skipped"} or bool(clean_note)
        if should_create_feedback:
            feedback_type = clean_status if clean_status in {"problem", "skipped"} else "note"
            cursor = db.execute(
                """
                INSERT INTO operator_feedback
                    (project_id, step_id, feedback_type, note, admin_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (project_id, step_id, feedback_type, clean_note, timestamp, timestamp),
            )
            feedback_id = cursor.lastrowid
            db.execute(
                """
                INSERT INTO operator_feedback_history (feedback_id, admin_status, note, created_at)
                VALUES (?, 'open', ?, ?)
                """,
                (feedback_id, "Zgloszenie operatora", timestamp),
            )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def update_operator_feedback(
    project_id: str,
    feedback_id: int,
    admin_status: str,
    admin_note: str = "",
) -> dict[str, Any] | None:
    clean_status = (admin_status or "").strip().lower()
    if clean_status not in OPERATOR_FEEDBACK_STATUSES:
        raise ValueError("Nieprawidlowy status zgloszenia")

    clean_note = (admin_note or "").strip()
    timestamp = now_iso()
    resolved_at = timestamp if clean_status in {"fixed", "verified", "rejected"} else None
    with connect() as db:
        existing = db.execute(
            "SELECT * FROM operator_feedback WHERE project_id = ? AND id = ?",
            (project_id, feedback_id),
        ).fetchone()
        if existing is None:
            return None
        db.execute(
            """
            UPDATE operator_feedback
            SET admin_status = ?,
                admin_note = ?,
                updated_at = ?,
                resolved_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (clean_status, clean_note, timestamp, resolved_at, project_id, feedback_id),
        )
        db.execute(
            """
            INSERT INTO operator_feedback_history (feedback_id, admin_status, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (feedback_id, clean_status, clean_note, timestamp),
        )
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
    return get_project(project_id)


def create_session(project_id: str, operator_name: str, station_name: str) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            """
            INSERT INTO operator_sessions (id, project_id, operator_name, station_name, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, project_id, operator_name.strip(), station_name.strip(), timestamp),
        )
        db.execute(
            """
            UPDATE projects
            SET status = 'active', updated_at = ?
            WHERE id = ? AND status = 'ready'
            """,
            (timestamp, project_id),
        )
    session = get_session(session_id)
    assert session is not None
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    with connect() as db:
        session = row_to_dict(
            db.execute("SELECT * FROM operator_sessions WHERE id = ?", (session_id,)).fetchone()
        )
        if not session:
            return None
        session["events"] = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM step_events WHERE session_id = ? ORDER BY created_at, id",
                (session_id,),
            ).fetchall()
        ]
    return session


def create_step_event(session_id: str, step_id: int, status: str, note: str) -> dict[str, Any]:
    timestamp = now_iso()
    with connect() as db:
        cursor = db.execute(
            """
            INSERT INTO step_events (session_id, step_id, status, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, step_id, status, note.strip(), timestamp),
        )
        event_id = cursor.lastrowid
        row = db.execute("SELECT * FROM step_events WHERE id = ?", (event_id,)).fetchone()
    return dict(row)
