import base64
import json
import math
import os
import re
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from inserter_platform import db, html_exporter
from inserter_platform.server import PlatformHandler


class ManualPointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test.db"
        env = patch.dict(os.environ, {"INSERTER_PLATFORM_DB": str(self.path)})
        env.start()
        self.addCleanup(env.stop)
        original_connect = db.connect

        @contextmanager
        def connect():
            with closing(original_connect()) as c, c:
                yield c

        patched = patch.object(db, "connect", connect)
        patched.start()
        self.addCleanup(patched.stop)
        db.init_db()
        image = Path(self.directory.name) / "pcb.gif"
        image.write_bytes(base64.b64decode("R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="))
        with db.connect() as c:
            c.execute("""INSERT INTO projects (id,name,board_width,board_height,board_image_path,status,created_at,updated_at)
                       VALUES ('manual','Test',100,50,?,'prepared','t','t')""", (str(image),))
            self.step_id = c.execute("""INSERT INTO placement_steps
                (project_id,step_no,designators,value,medcom_index,quantity,seconds,notes,segments_json,created_at,updated_at)
                VALUES ('manual',51,'Z_K5K6,Z_RPA5A7','ZWORA','M-ZWORA',2,3.5,?,'[]','t','t')""",
                ("Brak punktu P&P: Z_K5K6, Z_RPA5A7 | Pominięte w montażu | Uwagi technologa",)).lastrowid
            c.execute("""INSERT INTO placement_steps (project_id,step_no,designators,value,medcom_index,created_at,updated_at)
                       VALUES ('manual',1,'R1','10K','M-R','t','t')""")
            c.execute("INSERT INTO component_points (project_id,designator,x,y,created_at) VALUES ('manual','R1',5,40,'t')")
            c.execute("INSERT INTO operator_step_statuses VALUES ('manual',?,'done','Operator','t')", (self.step_id,))

    def project(self):
        return db.get_project("manual")

    def step(self, project):
        return next(step for step in project["steps"] if step["id"] == self.step_id)

    def save(self, name="Z_K5K6", x=30, y=20, project=None, **overrides):
        project = project or self.project()
        current = next((p for p in project["points"] if p["designator"] == name), None)
        payload = dict(designator=name, x=x, y=y, expected_context=db.manual_point_context(project),
                       expected_point={k: current[k] for k in ("id", "x", "y")} if current else None)
        payload.update(overrides)
        return db.save_manual_point("manual", **payload)

    def test_add_and_complete_line_keep_notes_status_and_existing_data(self):
        before = self.project()
        first = self.save()
        self.assertEqual(self.step(first)["notes"], "Brak punktu P&P: Z_RPA5A7 | Pominięte w montażu | Uwagi technologa")
        after = self.save("Z_RPA5A7", 80, 10)
        self.assertEqual(self.step(after)["notes"], "Pominięte w montażu | Uwagi technologa")
        self.assertEqual(after["operator_step_statuses"], before["operator_step_statuses"])
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["points"][0], before["points"][0])
        self.assertEqual([p["source"] for p in after["points"]], ["pp", "manual", "manual"])
        for key in ("id", "step_no", "designators", "value", "medcom_index", "quantity", "seconds", "segments_json"):
            self.assertEqual(self.step(after)[key], self.step(before)[key])
        self.assertEqual(after["changes"][0]["change_type"], "manual_point")

    def test_edit_only_manual_and_reject_stale_clicks(self):
        old = self.project()
        first = self.save()
        self.assertNotEqual(first["points"], old["points"])
        with self.assertRaises(ValueError):
            self.save(project=old)
        old_point = next(p for p in first["points"] if p["source"] == "manual")
        after = self.save(x=40, y=30)
        new_point = next(p for p in after["points"] if p["source"] == "manual")
        self.assertEqual(old_point["id"], new_point["id"])
        self.assertEqual((new_point["x"], new_point["y"]), (40, 30))
        with self.assertRaises(ValueError):
            self.save(x=50, y=30, project=first)
        with self.assertRaisesRegex(ValueError, "importu"):
            self.save("R1")

    def test_reject_invalid_input_without_writes(self):
        before = self.project()
        for value in (None, "30", True, math.nan, math.inf, -1, 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(x=value)
            self.assertEqual(self.project(), before)
        with self.assertRaises(ValueError):
            self.save("OTHER-PROJECT")
        with self.assertRaises(ValueError):
            self.save(expected_context={})
        self.assertEqual(self.project(), before)

    def test_geometry_changes_and_missing_image_rejected(self):
        old = self.project()
        with db.connect() as c:
            c.execute("UPDATE projects SET board_calibration_json=? WHERE id='manual'", ('{"rotation":90}',))
        with self.assertRaisesRegex(ValueError, "kalibracja"):
            self.save(project=old)
        with db.connect() as c:
            c.execute("UPDATE projects SET board_image_path=NULL WHERE id='manual'")
        with self.assertRaisesRegex(ValueError, "obraz"):
            self.save()

    def test_no_reference_frame_is_rejected(self):
        with db.connect() as c:
            c.execute("UPDATE projects SET board_width=NULL, board_height=NULL WHERE id='manual'")
            c.execute("DELETE FROM component_points WHERE project_id='manual'")
        with self.assertRaisesRegex(ValueError, "wymiary PCB"):
            self.save(x=0, y=0)

    def test_manual_markers_do_not_change_frame_or_export_alignment(self):
        before = self.project()
        metrics = html_exporter._board_base_metrics(before, before["points"])
        after = self.save(x=99, y=49)
        self.assertEqual(html_exporter._board_base_metrics(after, after["points"]), metrics)
        points_before = html_exporter._export_component_points(before, {"R1"})[0]
        points_after = html_exporter._export_component_points(after, {"R1"})[0]
        self.assertEqual(points_before, points_after)
        after["board_calibration"] = dict(rotation=90, flipX=True, flipY=False, offsetX=2, offsetY=-3, scaleX=.8, scaleY=.9)
        html, _ = html_exporter.render_project_html(after)
        exported = json.loads(re.search(r"var componentData = (\[.*?\]);", html, re.DOTALL).group(1))
        manual = next(p for p in exported if p["Desygnator"] == "Z_K5K6")
        self.assertEqual(manual["Source"], "manual")
        expected = html_exporter._apply_calibration(.99, .02, after["board_calibration"])
        self.assertAlmostEqual(manual["X"], expected[0] * 50)
        self.assertAlmostEqual(manual["Y"], (1 - expected[1]) * 100)
        table = json.loads(re.search(r"var tableData = (\[.*?\]);", html, re.DOTALL).group(1))
        self.assertIn("Punkty dodane ręcznie: Z_K5K6", table[-1]["UWAGI"])

    def test_source_default_and_migration_are_safe_to_repeat(self):
        before = self.project()
        with db.connect() as c:
            c.execute("ALTER TABLE component_points DROP COLUMN source")
        db.init_db()
        db.init_db()
        self.assertEqual(self.project(), before)

    def test_supplement_does_not_overwrite_manual_point(self):
        manual = self.save()
        before = next(p for p in manual["points"] if p["source"] == "manual")
        after, _ = db.supplement_project_points("manual", points=[{"designator": "Z_K5K6", "x": 80, "y": 40}], summary={})
        self.assertEqual(next(p for p in after["points"] if p["source"] == "manual"), before)

    def test_http_save_reload_and_invalid_request(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), PlatformHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/api/projects/manual"
        payload = dict(designator="Z_K5K6", x=30, y=20, expectedContext=db.manual_point_context(self.project()), expectedPoint=None)
        try:
            request = Request(base + "/points/manual", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["project"]["points"][-1]["source"], "manual")
            with urlopen(base, timeout=5) as response:
                self.assertEqual(json.load(response)["project"]["points"][-1]["x"], 30)
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=5)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
