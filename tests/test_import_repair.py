import copy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from inserter_platform import db, import_repair as repair, importer


class ImportRepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "repair.db"
        with patch.dict(os.environ, {"INSERTER_PLATFORM_DB": str(self.database)}):
            # init_db's production connection context does not close on exit.
            with closing(db.connect()) as connection:
                with patch.object(db, "connect", return_value=connection):
                    db.init_db()
        with closing(sqlite3.connect(self.database)) as c, c:
            c.execute("INSERT INTO projects (id,name,status,created_at,updated_at) VALUES ('p','Test','prepared','t','t')")
            c.execute("INSERT INTO projects (id,name,created_at,updated_at) VALUES ('other','Other','t','t')")
            c.execute("""INSERT INTO placement_steps
                (project_id,step_no,designators,value,medcom_index,quantity,seconds,notes,segments_json,created_at,updated_at)
                VALUES ('p',7,'TP22,TP20,TP21','custom','M-CUSTOM',6,2.5,'keep note',?, 't','t')""",
                (json.dumps([{"designators": ["TP22", "TP20", "TP21"], "quantity": 6, "custom": "keep"}]),))
            c.execute("INSERT INTO component_points (project_id,designator,x,y,created_at) VALUES ('p','TP22',100,200,'t')")
            c.execute("INSERT INTO operator_step_statuses VALUES ('p',1,'done','keep operator note','t')")
            self.before = repair.snapshot(c, "p")
        self.bom = [importer.BomItem(n, "source", "M-SOURCE", 2) for n in ("TP20", "TP21", "TP22")]
        self.bom += [importer.BomItem(n, "RJ45", "M-RJ45", 3) for n in ("X-AL", "ZEN")]
        self.bom += [importer.BomItem("X-DIAG1'", "screw", "M-SCREW", 4)]
        self.pp = [importer.PlacementPoint(n, i, i + 1, 90, i) for i, n in enumerate(("TP22", "X-AL", "ZEN", "X-EXTRA"))]
        self.allowed = ["X-AL", "ZEN", "X-DIAG1'"]
        self.plan = self.make_plan()

    def make_plan(self, allowed=None):
        with patch.object(importer, "parse_bom", return_value=(self.bom, {"bomRowsWithoutDesignators": []})), \
             patch.object(importer, "parse_placement", return_value=(self.pp, {"ppInvalidRows": []})):
            return repair.make_plan(self.before, bom_bytes=b"bom", pp_bytes=b"pp",
                                    allowed_designators=self.allowed if allowed is None else allowed)

    def dump(self):
        with closing(sqlite3.connect(self.database)) as c:
            return list(c.iterdump())

    def test_dry_run_makes_no_database_changes_or_backup(self):
        before = self.dump()
        result = repair.apply_plan(self.database, self.plan)
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["addedPoints"], 2)
        self.assertEqual(self.dump(), before)
        self.assertFalse((self.database.parent / "deploy-backups").exists())

    def test_additive_backup_preservation_and_idempotence(self):
        original_dump = self.dump()
        result = repair.apply_plan(self.database, self.plan, apply=True)
        self.assertEqual(result["status"], "applied")
        with closing(sqlite3.connect(result["backup"])) as c:
            self.assertEqual(list(c.iterdump()), original_dump)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with closing(sqlite3.connect(self.database)) as c:
            after = repair.snapshot(c, "p")
            self.assertEqual(after["steps"][:1], self.before["steps"])
            self.assertEqual([s["step_no"] for s in after["steps"]], [7, 8, 9])
            self.assertEqual(after["project"]["status"], "prepared")
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM operator_step_statuses")],
                             [("p", 1, "done", "keep operator note", "t")])
            self.assertEqual(c.execute("SELECT updated_at FROM projects WHERE id='other'").fetchone()[0], "t")
            old_point = next(p for p in after["points"] if p["designator"] == "TP22")
            self.assertEqual(old_point, self.before["points"][0])
            self.assertEqual({p["designator"] for p in after["points"]}, {"TP22", "X-AL", "ZEN"})
            self.assertEqual(after["steps"][-1]["notes"], "Brak punktu P&P: X-DIAG1'")
        applied_dump = self.dump()
        self.assertEqual(repair.apply_plan(self.database, self.plan, apply=True)["status"], "already-applied")
        self.assertEqual(self.dump(), applied_dump)

    def test_stale_plan_rejected_without_changes(self):
        with closing(sqlite3.connect(self.database)) as c, c:
            c.execute("UPDATE placement_steps SET notes='new operator preparation'")
        before = self.dump()
        with self.assertRaisesRegex(ValueError, "Project changed"):
            repair.apply_plan(self.database, self.plan, apply=True)
        self.assertEqual(self.dump(), before)

    def test_allowlist_must_exactly_match_source_difference(self):
        for allowed in (["X-AL"], self.allowed + ["TP22"], self.allowed + ["X-EXTRA"]):
            with self.subTest(allowed=allowed), self.assertRaises(ValueError):
                self.make_plan(allowed)

    def test_unapproved_point_and_missing_note_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["points"].append({"designator": "X-EXTRA", "x": 0, "y": 0})
        with self.assertRaisesRegex(ValueError, "allowlist"):
            repair.apply_plan(self.database, plan, apply=True)
        plan = copy.deepcopy(self.plan)
        plan["steps"][-1]["notes"] = ""
        with self.assertRaisesRegex(ValueError, "explicitly noted"):
            repair.apply_plan(self.database, plan, apply=True)

    def test_insert_failure_rolls_back_all_changes(self):
        with closing(sqlite3.connect(self.database)) as c, c:
            c.execute("""CREATE TRIGGER fail_repair BEFORE INSERT ON component_points
                WHEN NEW.designator='ZEN' BEGIN SELECT RAISE(ABORT,'test failure'); END""")
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            repair.apply_plan(self.database, self.plan, apply=True)
        self.assertEqual(self.dump(), before)

    def test_backup_failure_prevents_inserts(self):
        before = self.dump()
        with patch.object(Path, "touch", side_effect=OSError("backup unavailable")):
            with self.assertRaises(OSError):
                repair.apply_plan(self.database, self.plan, apply=True)
        self.assertEqual(self.dump(), before)

    def test_backup_also_works_with_wal_database(self):
        with closing(sqlite3.connect(self.database)) as c:
            c.execute("PRAGMA journal_mode=WAL")
        result = repair.apply_plan(self.database, self.plan, apply=True)
        self.assertEqual(result["status"], "applied")
        with closing(sqlite3.connect(result["backup"])) as c:
            self.assertEqual(repair.snapshot(c, "p"), self.before)


if __name__ == "__main__":
    unittest.main()
