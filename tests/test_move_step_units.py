import base64
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from inserter_platform import db, html_exporter


class MoveStepUnitsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("INSERTER_PLATFORM_DB")
        os.environ["INSERTER_PLATFORM_DB"] = str(Path(self.directory.name) / "test.db")
        self.original_connect = db.connect
        self.connections = []

        def tracked_connect():
            connection = self.original_connect()
            self.connections.append(connection)
            return connection

        db.connect = tracked_connect
        db.init_db()
        timestamp = db.now_iso()
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("test", "Test", timestamp, timestamp),
            )
            source = connection.execute(
                """
                INSERT INTO placement_steps
                    (project_id, step_no, designators, value, medcom_index, quantity,
                     notes, segments_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "test", 1, "J20,J21,J19", "1 PIN", "M-ZLACZ-00015", 3, "",
                    json.dumps([
                        {"pinCount": 1, "designators": [name], "quantity": 1, "label": name}
                        for name in ("J20", "J21", "J19")
                    ]),
                    timestamp, timestamp,
                ),
            )
            target = connection.execute(
                """
                INSERT INTO placement_steps
                    (project_id, step_no, designators, value, medcom_index, quantity,
                     notes, segments_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "test", 2, "JP1,JP2", "4 PIN (4PIN 2x40 H12)", "M-ZLACZ-00851", 2, "",
                    json.dumps([
                        {"pinCount": 4, "designators": [name], "quantity": 1, "label": name}
                        for name in ("JP1", "JP2")
                    ]),
                    timestamp, timestamp,
                ),
            )
            self.source_id = source.lastrowid
            self.target_id = target.lastrowid

    def tearDown(self):
        db.connect = self.original_connect
        for connection in self.connections:
            connection.close()
        if self.previous_db_path is None:
            os.environ.pop("INSERTER_PLATFORM_DB", None)
        else:
            os.environ["INSERTER_PLATFORM_DB"] = self.previous_db_path
        self.directory.cleanup()

    def test_move_between_different_values_and_indexes_preserves_unit_origin(self):
        project = db.move_step_units("test", self.source_id, self.target_id, [0, 1])
        steps = {step["id"]: step for step in project["steps"]}
        self.assertEqual(steps[self.source_id]["designators"], "J19")
        target = steps[self.target_id]
        self.assertEqual(target["designators"], "JP1,JP2,J20,J21")
        self.assertEqual(target["quantity"], 4)
        self.assertEqual(
            target["unit_origin_notes"],
            ["J20, J21: 1 PIN / indeks M-ZLACZ-00015"],
        )
        self.assertEqual(html_exporter._display_quantity_for_step(target), "4 szt. (różne PIN)")

        image_path = Path(self.directory.name) / "board.gif"
        image_path.write_bytes(base64.b64decode("R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="))
        project["board_image_path"] = str(image_path)
        html, _ = html_exporter.render_project_html(project)
        table_data = json.loads(re.search(r"var tableData = (\[.*?\]);", html, re.DOTALL).group(1))
        self.assertEqual(table_data[1]["Pochodzenie"], "J20, J21: 1 PIN / indeks M-ZLACZ-00015")
        self.assertEqual(table_data[1]["Ilość"], "4 szt. (różne PIN)")

        project = db.move_step_units("test", self.target_id, self.source_id, [2])
        steps = {step["id"]: step for step in project["steps"]}
        self.assertEqual(steps[self.source_id]["designators"], "J19,J20")
        self.assertEqual(steps[self.source_id]["unit_origin_notes"], [])
        self.assertEqual(steps[self.target_id]["unit_origin_notes"], ["J21: 1 PIN / indeks M-ZLACZ-00015"])

    def test_move_from_plain_line_keeps_mixed_pin_quantity_accurate(self):
        with db.connect() as connection:
            connection.execute("UPDATE placement_steps SET segments_json = '' WHERE id IN (?, ?)", (self.source_id, self.target_id))

        project = db.move_step_units("test", self.source_id, self.target_id, [0])
        target = next(step for step in project["steps"] if step["id"] == self.target_id)
        self.assertEqual(target["unit_origin_notes"], ["J20: 1 PIN / indeks M-ZLACZ-00015"])
        self.assertEqual(html_exporter._display_quantity_for_step(target), "3 szt. (różne PIN)")


if __name__ == "__main__":
    unittest.main()
