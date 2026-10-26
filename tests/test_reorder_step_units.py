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


class ReorderStepUnitsTests(unittest.TestCase):
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
        self.designators = ["R189", "RP.A2.1", "RP.A3.1", "RP.A4.1", "RP.B1.1", "RP.B2.1", "RP.B5.1"]
        self.units = [
            {"designators": ["TP20", "TP21", "TP22"], "label": "TP20+TP21+TP22",
             "pinCount": 3, "quantity": 2, "value": "3 PIN", "medcomIndex": "M-PINS", "custom": "preserve"},
            {"designators": ["J20"], "label": "J20", "pinCount": 1, "quantity": 1,
             "value": "1 PIN", "medcomIndex": "M-SINGLE"},
        ]
        timestamp = db.now_iso()
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("order-test", "Kolejność — test", "prepared", timestamp, timestamp),
            )
            self.plain_id = connection.execute(
                """INSERT INTO placement_steps
                   (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("order-test", 1, ",".join(self.designators), "10K", "M-RES", 15, 12.5, "Uwagi", timestamp, timestamp),
            ).lastrowid
            self.segment_id = connection.execute(
                """INSERT INTO placement_steps
                   (project_id, step_no, designators, value, medcom_index, quantity, seconds, notes,
                    segments_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("order-test", 2, "TP20,TP21,TP22,J20", "3 PIN", "M-PINS", 3, 8, "Sprawdź montaż",
                 json.dumps(self.units), timestamp, timestamp),
            ).lastrowid
            connection.executemany(
                "INSERT INTO component_points (project_id, designator, x, y, created_at) VALUES (?, ?, ?, ?, ?)",
                [("order-test", name, index + 1, 1, timestamp)
                 for index, name in enumerate(self.designators + ["TP20", "TP21", "TP22", "J20"])],
            )

    def step(self, step_id, project=None):
        return next(step for step in (project or db.get_project("order-test"))["steps"] if step["id"] == step_id)

    def expected(self, step_id):
        return [unit["designators"] for unit in db.step_units_from_row(self.step(step_id))]

    def exported_rows(self, project):
        image_path = Path(self.directory.name) / "board.gif"
        image_path.write_bytes(base64.b64decode("R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="))
        project["board_image_path"] = str(image_path)
        html, _ = html_exporter.render_project_html(project)
        return json.loads(re.search(r"var tableData = (\[.*?\]);", html, re.DOTALL).group(1))

    def assert_only_order_changed(self, before, after):
        changed = {"designators", "segments_json", "segments", "updated_at", "unit_origin_notes"}
        self.assertEqual({k: v for k, v in before.items() if k not in changed},
                         {k: v for k, v in after.items() if k not in changed})

    def test_plain_line_persists_exact_order_and_keeps_manual_quantity(self):
        before = db.get_project("order-test")
        order = [6, 0, 4, 2, 1, 5, 3]
        project = db.reorder_step_units("order-test", self.plain_id, order, self.expected(self.plain_id))
        expected = ",".join(self.designators[index] for index in order)
        after = self.step(self.plain_id, project)
        self.assertEqual(after["designators"], expected)
        self.assertEqual(after["quantity"], 15)
        self.assertEqual(after["segments"], [])
        self.assert_only_order_changed(self.step(self.plain_id, before), after)
        self.assertEqual(self.step(self.segment_id, before), self.step(self.segment_id, project))
        self.assertEqual(project["points"], before["points"])
        self.assertEqual(self.step(self.plain_id)["designators"], expected)
        self.assertEqual(self.exported_rows(project)[0]["Desygnator"], expected)

    def test_segments_move_intact_including_all_material_metadata_and_html(self):
        before = self.step(self.segment_id)
        project = db.reorder_step_units("order-test", self.segment_id, [1, 0], self.expected(self.segment_id))
        step = self.step(self.segment_id, project)
        self.assertEqual(step["designators"], "J20,TP20,TP21,TP22")
        self.assertEqual(step["segments"], list(reversed(self.units)))
        self.assert_only_order_changed(before, step)
        self.assertEqual(html_exporter._point_designators_for_step(step), ["J20", "TP20", "TP21", "TP22"])
        row = self.exported_rows(project)[1]
        self.assertEqual(row["Desygnator"], "J20,TP20+TP21+TP22")
        self.assertEqual(row["Ilość"], "3 szt. (różne PIN)")
        with db.connect() as connection:
            history = connection.execute(
                "SELECT description FROM project_changes WHERE change_type = 'step_units_reorder'"
            ).fetchall()
        self.assertEqual(len(history), 1)
        self.assertIn("J20,TP20,TP21,TP22", history[0]["description"])

    def test_invalid_permutations_are_atomic(self):
        expected = self.expected(self.segment_id)
        before = db.get_project("order-test")
        for order in (None, "1,0", [], [0], [0, 0], [1, 2], [-1, 0], [0, 1, 2], [True, 0], [1.0, 0], ["1", 0]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                db.reorder_step_units("order-test", self.segment_id, order, expected)
            self.assertEqual(db.get_project("order-test"), before)

    def test_missing_or_stale_snapshot_is_rejected_without_overwrite(self):
        original = self.expected(self.segment_id)
        db.reorder_step_units("order-test", self.segment_id, [1, 0], original)
        before = db.get_project("order-test")
        for expected in (None, [], original, [["J20"], ["TP20", "TP22", "TP21"]]):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                db.reorder_step_units("order-test", self.segment_id, [1, 0], expected)
            self.assertEqual(db.get_project("order-test"), before)
        current = self.expected(self.segment_id)
        db.delete_step_designators("order-test", self.segment_id, ["TP22"])
        with self.assertRaises(ValueError):
            db.reorder_step_units("order-test", self.segment_id, [1, 0], current)
        self.assertNotIn("TP22", self.step(self.segment_id)["designators"])

    def test_noop_and_wrong_project_leave_data_and_history_unchanged(self):
        before = db.get_project("order-test")
        expected = self.expected(self.segment_id)
        self.assertEqual(db.reorder_step_units("order-test", self.segment_id, [0, 1], expected), before)
        self.assertIsNone(db.reorder_step_units("another", self.segment_id, [1, 0], expected))
        self.assertIsNone(db.reorder_step_units("order-test", -1, [1, 0], expected))
        self.assertEqual(db.get_project("order-test"), before)

    def test_legacy_notes_are_migrated_without_stale_order(self):
        with db.connect() as connection:
            connection.execute(
                "UPDATE placement_steps SET segments_json = '', notes = ? WHERE id = ?",
                ("Sprawdź montaż | Odcinki: TP20+TP21+TP22; J20", self.segment_id),
            )
        project = db.reorder_step_units("order-test", self.segment_id, [1, 0], self.expected(self.segment_id))
        step = self.step(self.segment_id, project)
        self.assertEqual(step["notes"], "Sprawdź montaż")
        self.assertEqual([unit["designators"] for unit in step["segments"]], [["J20"], ["TP20", "TP21", "TP22"]])
        self.assertEqual(self.exported_rows(project)[1]["Desygnator"], "J20,TP20+TP21+TP22")

    def test_single_unit_noop(self):
        with db.connect() as connection:
            connection.execute("UPDATE placement_steps SET designators = 'R189' WHERE id = ?", (self.plain_id,))
        before = db.get_project("order-test")
        self.assertEqual(db.reorder_step_units("order-test", self.plain_id, [0], [["R189"]]), before)

    def test_http_endpoint_validation_save_and_reload(self):
        class QuietHandler(PlatformHandler):
            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/projects/order-test/steps/{self.segment_id}/reorder-units"
            expected = self.expected(self.segment_id)
            for order, status in (([0, 0], 400), ([1, 0], 200), ([1, 0], 400)):
                request = Request(url, json.dumps({"unitOrder": order, "expectedUnits": expected}).encode(),
                                  {"Content-Type": "application/json"}, method="POST")
                if status == 200:
                    with urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, status)
                        self.assertEqual(self.step(self.segment_id, json.load(response)["project"])["designators"], "J20,TP20,TP21,TP22")
                else:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, status)
                    error.exception.close()
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/projects/order-test", timeout=5) as response:
                self.assertEqual(self.step(self.segment_id, json.load(response)["project"])["designators"], "J20,TP20,TP21,TP22")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
