from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_TABLES = (
    "component_points",
    "component_polarity",
    "project_imports",
    "project_changes",
    "operator_sessions",
)


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


def insert_row(
    dest: sqlite3.Connection,
    table: str,
    row: sqlite3.Row | dict[str, Any],
    *,
    source_columns: set[str],
    dest_columns: set[str],
    exclude: set[str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> int:
    exclude = exclude or set()
    overrides = overrides or {}
    raw = row_dict(row) if isinstance(row, sqlite3.Row) else dict(row)

    values: dict[str, Any] = {}
    for column in source_columns & dest_columns:
        if column not in exclude:
            values[column] = raw.get(column)
    values.update({key: value for key, value in overrides.items() if key in dest_columns})

    columns = list(values.keys())
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders(len(columns))})"
    cursor = dest.execute(sql, [values[column] for column in columns])
    return int(cursor.lastrowid or 0)


def count_rows(db: sqlite3.Connection, table: str, project_id: str) -> int:
    return int(
        db.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE project_id = ?", (project_id,)).fetchone()["count"]
    )


def project_summary(source: sqlite3.Connection, project_id: str) -> dict[str, int]:
    summary = {table: count_rows(source, table, project_id) for table in PROJECT_TABLES}
    summary["placement_steps"] = count_rows(source, "placement_steps", project_id)
    summary["operator_step_statuses"] = count_rows(source, "operator_step_statuses", project_id)
    summary["operator_feedback"] = count_rows(source, "operator_feedback", project_id)
    return summary


def init_destination_schema(dest_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    os.environ["INSERTER_PLATFORM_DB"] = str(dest_path)
    from inserter_platform import db as app_db

    app_db.init_db()


def backup_database(dest_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = dest_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{dest_path.stem}_before_merge_{timestamp}{dest_path.suffix}"
    shutil.copy2(dest_path, backup_path)
    return backup_path


def copy_uploads(source_uploads: Path, dest_uploads: Path, project_id: str) -> bool:
    source_dir = source_uploads / project_id
    if not source_dir.exists():
        return False
    dest_dir = dest_uploads / project_id
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
    return True


def existing_project_by_name(dest: sqlite3.Connection) -> dict[str, str]:
    rows = dest.execute("SELECT id, name FROM projects").fetchall()
    return {str(row["name"] or "").strip().casefold(): row["id"] for row in rows}


def merge_pin_indexes(source: sqlite3.Connection, dest: sqlite3.Connection, apply: bool) -> int:
    if "pin_indexes" not in {
        row["name"] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        return 0

    source_rows = source.execute("SELECT * FROM pin_indexes WHERE active = 1 ORDER BY medcom_index").fetchall()
    existing = {
        row["medcom_index"]
        for row in dest.execute("SELECT medcom_index FROM pin_indexes").fetchall()
    }
    missing = [row for row in source_rows if row["medcom_index"] not in existing]
    if apply:
        source_columns = set(table_columns(source, "pin_indexes"))
        dest_columns = set(table_columns(dest, "pin_indexes"))
        for row in missing:
            insert_row(dest, "pin_indexes", row, source_columns=source_columns, dest_columns=dest_columns)
    return len(missing)


def import_project(
    source: sqlite3.Connection,
    dest: sqlite3.Connection,
    project: sqlite3.Row,
    *,
    source_uploads: Path,
    dest_uploads: Path,
) -> dict[str, Any]:
    project_id = str(project["id"])

    source_columns_by_table = {
        table: set(table_columns(source, table))
        for table in [
            "projects",
            "placement_steps",
            "operator_step_statuses",
            "operator_feedback",
            "operator_feedback_history",
            "step_events",
            *PROJECT_TABLES,
        ]
    }
    dest_columns_by_table = {
        table: set(table_columns(dest, table))
        for table in [
            "projects",
            "placement_steps",
            "operator_step_statuses",
            "operator_feedback",
            "operator_feedback_history",
            "step_events",
            *PROJECT_TABLES,
        ]
    }

    insert_row(
        dest,
        "projects",
        project,
        source_columns=source_columns_by_table["projects"],
        dest_columns=dest_columns_by_table["projects"],
    )

    step_id_map: dict[int, int] = {}
    for row in source.execute(
        "SELECT * FROM placement_steps WHERE project_id = ? ORDER BY step_no, id",
        (project_id,),
    ).fetchall():
        old_id = int(row["id"])
        new_id = insert_row(
            dest,
            "placement_steps",
            row,
            source_columns=source_columns_by_table["placement_steps"],
            dest_columns=dest_columns_by_table["placement_steps"],
            exclude={"id"},
            overrides={"project_id": project_id},
        )
        step_id_map[old_id] = new_id

    for table in ("component_points", "component_polarity", "project_imports", "project_changes"):
        for row in source.execute(
            f"SELECT * FROM {table} WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall():
            insert_row(
                dest,
                table,
                row,
                source_columns=source_columns_by_table[table],
                dest_columns=dest_columns_by_table[table],
                exclude={"id"},
                overrides={"project_id": project_id},
            )

    for row in source.execute(
        "SELECT * FROM operator_sessions WHERE project_id = ? ORDER BY started_at, id",
        (project_id,),
    ).fetchall():
        insert_row(
            dest,
            "operator_sessions",
            row,
            source_columns=source_columns_by_table["operator_sessions"],
            dest_columns=dest_columns_by_table["operator_sessions"],
            overrides={"project_id": project_id},
        )

    for row in source.execute(
        "SELECT * FROM operator_step_statuses WHERE project_id = ?",
        (project_id,),
    ).fetchall():
        old_step_id = int(row["step_id"])
        new_step_id = step_id_map.get(old_step_id)
        if not new_step_id:
            continue
        insert_row(
            dest,
            "operator_step_statuses",
            row,
            source_columns=source_columns_by_table["operator_step_statuses"],
            dest_columns=dest_columns_by_table["operator_step_statuses"],
            overrides={"project_id": project_id, "step_id": new_step_id},
        )

    feedback_id_map: dict[int, int] = {}
    for row in source.execute(
        "SELECT * FROM operator_feedback WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall():
        old_step_id = int(row["step_id"])
        new_step_id = step_id_map.get(old_step_id)
        if not new_step_id:
            continue
        old_feedback_id = int(row["id"])
        new_feedback_id = insert_row(
            dest,
            "operator_feedback",
            row,
            source_columns=source_columns_by_table["operator_feedback"],
            dest_columns=dest_columns_by_table["operator_feedback"],
            exclude={"id"},
            overrides={"project_id": project_id, "step_id": new_step_id},
        )
        feedback_id_map[old_feedback_id] = new_feedback_id

    for old_feedback_id, new_feedback_id in feedback_id_map.items():
        for row in source.execute(
            "SELECT * FROM operator_feedback_history WHERE feedback_id = ? ORDER BY created_at, id",
            (old_feedback_id,),
        ).fetchall():
            insert_row(
                dest,
                "operator_feedback_history",
                row,
                source_columns=source_columns_by_table["operator_feedback_history"],
                dest_columns=dest_columns_by_table["operator_feedback_history"],
                exclude={"id"},
                overrides={"feedback_id": new_feedback_id},
            )

    for row in source.execute(
        """
        SELECT e.*
        FROM step_events e
        JOIN operator_sessions s ON s.id = e.session_id
        WHERE s.project_id = ?
        ORDER BY e.created_at, e.id
        """,
        (project_id,),
    ).fetchall():
        old_step_id = int(row["step_id"])
        new_step_id = step_id_map.get(old_step_id)
        if not new_step_id:
            continue
        insert_row(
            dest,
            "step_events",
            row,
            source_columns=source_columns_by_table["step_events"],
            dest_columns=dest_columns_by_table["step_events"],
            exclude={"id"},
            overrides={"step_id": new_step_id},
        )

    copied_uploads = copy_uploads(source_uploads, dest_uploads, project_id)
    return {"project_id": project_id, "steps": len(step_id_map), "uploads": copied_uploads}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge selected MSX THT Inserter projects between SQLite databases.")
    parser.add_argument("--source", required=True, type=Path, help="Source inserter_platform.db")
    parser.add_argument("--dest", required=True, type=Path, help="Destination inserter_platform.db")
    parser.add_argument("--source-uploads", required=True, type=Path, help="Source data/uploads directory")
    parser.add_argument("--dest-uploads", required=True, type=Path, help="Destination data/uploads directory")
    parser.add_argument("--project", action="append", default=[], help="Project id or exact project name to import")
    parser.add_argument("--allow-name-duplicates", action="store_true", help="Import even when project name exists")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without this flag only a plan is printed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    dest_path = args.dest.resolve()
    if not source_path.exists():
        raise SystemExit(f"Source database does not exist: {source_path}")
    if not dest_path.exists():
        raise SystemExit(f"Destination database does not exist: {dest_path}")

    init_destination_schema(dest_path)
    source = connect(source_path)
    dest = connect(dest_path)

    requested = {str(value).strip().casefold() for value in args.project if str(value).strip()}
    projects = source.execute("SELECT * FROM projects ORDER BY updated_at DESC, name").fetchall()
    if requested:
        projects = [
            project
            for project in projects
            if str(project["id"]).casefold() in requested
            or str(project["name"] or "").strip().casefold() in requested
        ]

    dest_ids = {
        row["id"]
        for row in dest.execute("SELECT id FROM projects").fetchall()
    }
    dest_names = existing_project_by_name(dest)

    to_import: list[sqlite3.Row] = []
    skipped: list[tuple[sqlite3.Row, str]] = []
    for project in projects:
        project_id = str(project["id"])
        project_name = str(project["name"] or "").strip()
        normalized_name = project_name.casefold()
        if project_id in dest_ids:
            skipped.append((project, "same project id already exists"))
        elif not args.allow_name_duplicates and normalized_name in dest_names:
            skipped.append((project, f"project name already exists as {dest_names[normalized_name]}"))
        else:
            to_import.append(project)

    print("Project merge plan")
    print(f"Source: {source_path}")
    print(f"Destination: {dest_path}")
    print(f"Mode: {'APPLY' if args.apply else 'PLAN ONLY'}")
    print("")

    pin_count = merge_pin_indexes(source, dest, apply=False)
    print(f"Pin indexes to add: {pin_count}")

    if to_import:
        print("Projects to import:")
        for project in to_import:
            summary = project_summary(source, str(project["id"]))
            print(
                f"- {project['name']} [{project['id']}] "
                f"steps={summary['placement_steps']} points={summary['component_points']} "
                f"feedback={summary['operator_feedback']}"
            )
    else:
        print("Projects to import: none")

    if skipped:
        print("Skipped projects:")
        for project, reason in skipped:
            print(f"- {project['name']} [{project['id']}]: {reason}")

    if not args.apply:
        print("")
        print("No changes were written. Re-run with --apply to import the listed projects.")
        return 0

    backup_path = backup_database(dest_path)
    print("")
    print(f"Destination backup: {backup_path}")

    with dest:
        added_pin_indexes = merge_pin_indexes(source, dest, apply=True)
        print(f"Added pin indexes: {added_pin_indexes}")
        for project in to_import:
            result = import_project(
                source,
                dest,
                project,
                source_uploads=args.source_uploads,
                dest_uploads=args.dest_uploads,
            )
            print(
                f"Imported {project['name']} [{result['project_id']}]: "
                f"steps={result['steps']} uploads={'yes' if result['uploads'] else 'no'}"
            )

    print("Merge completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
