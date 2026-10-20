import base64
import json
import os
import re
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from inserter_platform import db, html_exporter
from inserter_platform.server import PlatformHandler


class DeleteStepDesignatorsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {"INSERTER_PLATFORM_DB": str(Path(self.directory.name) / "test.db")})
        self.env.start()
        self.addCleanup(self.env.stop)
        original_connect = db.connect
        @contextmanager
        def connect():
            with closing(original_connect()) as connection, connection:
                yield connection

        self.connection_patch = patch.object(db, "connect", connect)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        db.init_db()
        timestamp = db.now_iso()
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("delete-test", "Usuwanie TP — test", "prepared", timestamp, timestamp),
            )
            self.units = [
                {
                    "designators": ["TP20", "TP21", "TP22"], "label": "TP20+TP21+TP22",
                    "pinCount": 3, "quantity": 2, "value": "3 PIN", "medcomIndex": "M-ORIGINAL",
                },
                {
                    "designators": ["TP23"], "label": "TP23",
                    "pinCount": 1, "quantity": 1, "value": "1 PIN", "medcomIndex": "M-SINGLE",
                },
            ]
            self.step_id = connection.execute(
                """INSERT INTO placement_steps
                   (project_id, step_no, designators, value, medcom_index, quantity,
                    notes, segments_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "delete-test", 1, "TP20,TP21,TP22,TP23", "3 PIN", "M-ORIGINAL", 3,
                    "Sprawdź montaż", json.dumps(self.units), timestamp, timestamp,
                ),
            ).lastrowid
            self.other_step_id = connection.execute(
                """INSERT INTO placement_steps
                   (project_id, step_no, designators, value, medcom_index, quantity, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("delete-test", 2, "R1,R2", "10K", "M-RES", 2, timestamp, timestamp),
            ).lastrowid
            connection.executemany(
                "INSERT INTO component_points (project_id, designator, x, y, created_at) VALUES (?, ?, ?, ?, ?)",
                [("delete-test", name, index + 1, 1, timestamp) for index, name in enumerate(["TP20", "TP21", "TP22", "TP23", "R1", "R2"])],
            )

    def get_step(self, project, step_id=None):
        return next(step for step in project["steps"] if step["id"] == (step_id or self.step_id))

    def test_partial_segment_preserves_other_points_quantity_and_material(self):
        project = db.delete_step_designators("delete-test", self.step_id, ["tp22", "TP22"])
        step = self.get_step(project)
        self.assertEqual(step["designators"], "TP20,TP21,TP23")
        self.assertEqual(step["quantity"], 3)
        self.assertEqual(step["segments"][0], {
            **self.units[0], "designators": ["TP20", "TP21"], "label": "TP20+TP21",
        })
        self.assertEqual(step["segments"][1], self.units[1])
        self.assertEqual(step["notes"], "Sprawdź montaż")
        self.assertEqual(self.get_step(project, self.other_step_id)["designators"], "R1,R2")
        # Removing from assembly leaves the imported PCB point available for later editing.
        self.assertIn("TP22", [point["designator"] for point in project["points"]])
        self.assertNotIn("TP22", html_exporter._point_designators_for_step(step))

        image_path = Path(self.directory.name) / "board.gif"
        image_path.write_bytes(base64.b64decode("R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="))
        project["board_image_path"] = str(image_path)
        html, _ = html_exporter.render_project_html(project)
        rows = json.loads(re.search(r"var tableData = (\[.*?\]);", html, re.DOTALL).group(1))
        points = json.loads(re.search(r"var componentData = (\[.*?\]);", html, re.DOTALL).group(1))
        self.assertEqual(rows[0]["Desygnator"], "TP20+TP21,TP23")
        self.assertNotIn("TP22", [point["Desygnator"] for point in points])

    def test_partial_and_whole_unit_in_one_operation(self):
        project = db.delete_step_designators("delete-test", self.step_id, ["TP22", "TP23"])
        step = self.get_step(project)
        self.assertEqual(step["designators"], "TP20,TP21")
        self.assertEqual(step["quantity"], 2)
        self.assertEqual(len(step["segments"]), 1)
        with db.connect() as connection:
            history = connection.execute(
                "SELECT description FROM project_changes WHERE project_id = ? AND change_type = ?",
                ("delete-test", "step_delete_designators"),
            ).fetchall()
        self.assertEqual(len(history), 1)
        self.assertIn("TP22, TP23", history[0]["description"])

    def test_plain_line_and_removing_last_item_renumbers_remaining_lines(self):
        project = db.delete_step_designators("delete-test", self.other_step_id, ["R2"])
        step = self.get_step(project, self.other_step_id)
        self.assertEqual((step["designators"], step["quantity"]), ("R1", 1))
        project = db.delete_step_designators("delete-test", self.step_id, ["TP20", "TP21", "TP22", "TP23"])
        self.assertEqual([(step["id"], step["step_no"]) for step in project["steps"]], [(self.other_step_id, 1)])
        project = db.delete_step_designators("delete-test", self.other_step_id, ["R1"])
        self.assertEqual(project["steps"], [])

    def test_invalid_and_stale_selection_is_atomic(self):
        before = db.get_project("delete-test")
        for selection in ([], None, "TP22", [""], [None], ["TP22", "TP999"], ["R1"]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                db.delete_step_designators("delete-test", self.step_id, selection)
            self.assertEqual(db.get_project("delete-test"), before)
        self.assertIsNone(db.delete_step_designators("another-project", self.step_id, ["TP22"]))
        self.assertEqual(db.get_project("delete-test"), before)

    def test_legacy_segment_notes_are_replaced_by_updated_segments(self):
        for prefix in ("", "Sprawdź montaż | "):
            with self.subTest(prefix=prefix):
                with db.connect() as connection:
                    connection.execute(
                        "UPDATE placement_steps SET segments_json = '', notes = ?, designators = ? WHERE id = ?",
                        (prefix + "Odcinki: TP20+TP21+TP22; TP23", "TP20,TP21,TP22,TP23", self.step_id),
                    )
                project = db.delete_step_designators("delete-test", self.step_id, ["TP22"])
                step = self.get_step(project)
                self.assertEqual(step["notes"], prefix.removesuffix(" | "))
                self.assertEqual(step["segments"][0]["designators"], ["TP20", "TP21"])
                self.assertNotIn("TP22", html_exporter._display_designators_for_step(step))

    def test_http_endpoint_rejects_invalid_selection_and_deletes_only_requested_point(self):
        class QuietHandler(PlatformHandler):
            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/projects/delete-test/steps/{self.step_id}/delete-designators"
            request = Request(url, json.dumps({"designators": ["TP22", "TP999"]}).encode(), {"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=5)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            request = Request(url, json.dumps({"designators": ["TP22"]}).encode(), {"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                project = json.load(response)["project"]
            self.assertEqual(self.get_step(project)["designators"], "TP20,TP21,TP23")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
