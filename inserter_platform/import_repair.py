"""Guarded, additive maintenance repair. Never reimports or rewrites existing lines.

Build a plan with make_plan using a fresh snapshot and the original workbooks.
Review its explicit allowlist, then run::

    python -m inserter_platform.import_repair --db data/inserter_platform.db --plan plan.json
    python -m inserter_platform.import_repair --db data/inserter_platform.db --plan plan.json --apply

The default is read-only. Applying requires an unchanged snapshot, creates and
checks an online SQLite backup, then appends only the reviewed steps and points
in one transaction. Reapplying the same plan is a no-op.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from . import db, importer


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def snapshot(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise ValueError("Project not found")
    return {
        "project": dict(row),
        "steps": [dict(row) for row in connection.execute(
            "SELECT * FROM placement_steps WHERE project_id = ? ORDER BY step_no, id", (project_id,))],
        "points": [dict(row) for row in connection.execute(
            "SELECT * FROM component_points WHERE project_id = ? ORDER BY designator", (project_id,))],
    }


def make_plan(before: dict, *, bom_bytes: bytes, pp_bytes: bytes,
              allowed_designators: list[str]) -> dict:
    bom, bom_summary = importer.parse_bom(bom_bytes)
    pp, pp_summary = importer.parse_placement(pp_bytes)
    _, _, full_summary = importer.build_steps_and_points(bom, pp)
    if (bom_summary["bomRowsWithoutDesignators"] or pp_summary["ppInvalidRows"]
            or full_summary["bomDuplicateDesignators"] or full_summary["ppDuplicateDesignators"]):
        raise ValueError("Resolve invalid rows or duplicate source identifiers before repair")
    existing = {name for step in before["steps"] for name in db.split_designators(step["designators"])}
    source_names = {item.designator for item in bom}
    allowed = set(allowed_designators)
    if len(allowed) != len(allowed_designators) or not allowed:
        raise ValueError("A nonempty, unique explicit allowlist is required")
    if not existing <= source_names or source_names - existing != allowed:
        raise ValueError("Source/project difference does not exactly match the approved allowlist")
    if allowed & {point["designator"] for point in before["points"]}:
        raise ValueError("A missing identifier already has a point; review manually")
    steps, points, _ = importer.build_steps_and_points(
        [item for item in bom if item.designator in allowed], pp)
    plan = {
        "version": 1,
        "projectId": before["project"]["id"],
        "projectName": before["project"]["name"],
        "expectedState": digest(before),
        "allowedDesignators": sorted(allowed),
        "steps": steps,
        "points": points,
        "sourceSha256": {"bom": hashlib.sha256(bom_bytes).hexdigest(),
                         "pp": hashlib.sha256(pp_bytes).hexdigest()},
        "sourceSummary": {**bom_summary, **pp_summary, **full_summary},
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: dict) -> None:
    if plan["version"] != 1:
        raise ValueError("Unsupported plan version")
    allowed = set(plan["allowedDesignators"])
    names = [name for step in plan["steps"] for name in db.split_designators(step["designators"])]
    point_names = [point["designator"] for point in plan["points"]]
    if not allowed or set(names) != allowed or len(names) != len(allowed):
        raise ValueError("Repair lines must contain exactly the allowlisted identifiers once")
    if len(point_names) != len(set(point_names)) or not set(point_names) <= allowed:
        raise ValueError("Repair points must be unique and within the allowlist")
    for point in plan["points"]:
        if not all(math.isfinite(float(point[key])) for key in ("x", "y")):
            raise ValueError("Invalid coordinates")
        if point.get("rotation") is not None and not math.isfinite(float(point["rotation"])):
            raise ValueError("Invalid rotation")
    for step in plan["steps"]:
        step_names = db.split_designators(step["designators"])
        if step["quantity"] != len(step_names) or step.get("segments_json"):
            raise ValueError("Repair must use unmodified source quantities, without segments")
        for name in set(step_names) - set(point_names):
            if "Brak punktu P&P:" not in step["notes"] or name not in step["notes"]:
                raise ValueError("Missing points must be explicitly noted")


def apply_plan(database: Path, plan: dict, *, apply: bool = False,
               backup_dir: Path | None = None) -> dict:
    validate_plan(plan)
    database = database.resolve(strict=True)
    repair_id = digest(plan)
    project_id = plan["projectId"]
    mode = "rw" if apply else "ro"
    with closing(sqlite3.connect(database.as_uri() + f"?mode={mode}", uri=True, timeout=30)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
            for row in connection.execute(
                    "SELECT summary_json FROM project_imports WHERE project_id = ? AND source_type = ?",
                    (project_id, "prepared-xlsx-repair")):
                if json.loads(row[0]).get("repairId") == repair_id:
                    return {"status": "already-applied", "repairId": repair_id}
            before = snapshot(connection, project_id)
            if before["project"]["name"] != plan["projectName"] or digest(before) != plan["expectedState"]:
                raise ValueError("Project changed since planning; take a fresh snapshot and review again")
            existing = {name for step in before["steps"] for name in db.split_designators(step["designators"])}
            allowed = set(plan["allowedDesignators"])
            if allowed & (existing | {point["designator"] for point in before["points"]}):
                raise ValueError("Repair would duplicate an existing identifier")
            missing = sorted((existing | allowed) - {point["designator"] for point in before["points"]}
                             - {point["designator"] for point in plan["points"]})
            result = {"status": "dry-run", "repairId": repair_id,
                      "addedDesignators": sorted(allowed), "addedSteps": len(plan["steps"]),
                      "addedPoints": len(plan["points"]), "missingInPp": missing}
            if not apply:
                return result

            backup_dir = backup_dir or database.parent / "deploy-backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"before-import-repair-{uuid.uuid4().hex}.db"
            backup.touch(exist_ok=False)
            # A separate reader can back up while this connection holds the
            # reserved write lock. No application writes can race the backup.
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(backup)) as target:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                        raise ValueError("Backup integrity check failed; no repair applied")
            timestamp = db.now_iso()
            next_no = max((step["step_no"] for step in before["steps"]), default=0)
            for offset, step in enumerate(plan["steps"], 1):
                connection.execute(
                    """INSERT INTO placement_steps
                       (project_id, step_no, designators, value, medcom_index, quantity, seconds,
                        notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (project_id, next_no + offset, step["designators"], step["value"],
                     step["medcom_index"], step["quantity"], step.get("seconds"),
                     step["notes"], timestamp, timestamp))
            for point in plan["points"]:
                connection.execute(
                    """INSERT INTO component_points (project_id, designator, x, y, rotation, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (project_id, point["designator"], point["x"], point["y"], point.get("rotation"), timestamp))
            after = snapshot(connection, project_id)
            old_points = {point["id"] for point in before["points"]}
            if (after["project"] != before["project"]
                    or after["steps"][:len(before["steps"])] != before["steps"]
                    or [point for point in after["points"] if point["id"] in old_points] != before["points"]):
                raise ValueError("Existing data changed; rolling back repair")
            summary = {**plan["sourceSummary"], **result, "sourceType": "prepared-xlsx-repair",
                       "status": "applied", "sourceSha256": plan["sourceSha256"],
                       "createdSteps": len(plan["steps"]), "createdPoints": len(plan["points"]),
                       "backup": str(backup.resolve()), "existingLinesPreserved": len(before["steps"])}
            connection.execute(
                "INSERT INTO project_imports (project_id, source_type, summary_json, created_at) VALUES (?, ?, ?, ?)",
                (project_id, "prepared-xlsx-repair", json.dumps(summary, ensure_ascii=False), timestamp))
            db.append_project_change(connection, project_id, "import_repair",
                                     f"Uzupełniono {len(allowed)} pominiętych desygnatorów; zachowano istniejące linie.",
                                     timestamp)
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (timestamp, project_id))
            return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply after verified SQLite backup (default: dry-run)")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    print(json.dumps(apply_plan(args.db, plan, apply=args.apply, backup_dir=args.backup_dir), ensure_ascii=True))


if __name__ == "__main__":
    main()
