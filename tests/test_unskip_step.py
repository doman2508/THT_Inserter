import json
import os
from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from inserter_platform import db
from inserter_platform.server import PlatformHandler


class UnskipStepTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {"INSERTER_PLATFORM_DB": str(Path(self.directory.name) / "test.db")})
        env.start()
        self.addCleanup(env.stop)
        original_connect = db.connect

        @contextmanager
        def connect():
            with closing(original_connect()) as connection, connection:
                yield connection

        connection_patch = patch.object(db, "connect", connect)
        connection_patch.start()
        self.addCleanup(connection_patch.stop)
        db.init_db()
        self.notes = "Brak punktu P&P: Z_K5K6, Z_RPA5A7 | Uwagi technologiczne"
        with db.connect() as c:
            c.execute("INSERT INTO projects (id,name,status,created_at,updated_at) VALUES ('restore','Restore','prepared','t','t')")
            c.execute("INSERT INTO projects (id,name,created_at,updated_at) VALUES ('other','Other','t','t')")
            self.step_id = c.execute(
                """INSERT INTO placement_steps
                   (project_id,step_no,designators,value,medcom_index,quantity,seconds,notes,segments_json,created_at,updated_at)
                   VALUES ('restore',51,'Z_K5K6,Z_RPA5A7','ZWORA','M-ZWORA-00000',2,3.5,?,'[]','t','t')""",
                (self.notes,),
            ).lastrowid
            c.execute("INSERT INTO operator_step_statuses VALUES ('restore',?,'done','uwaga operatora','t')", (self.step_id,))

    def step(self, project=None):
        return (project or db.get_project("restore"))["steps"][0]

    def test_skip_then_restore_removes_marker_and_preserves_other_data(self):
        before = db.get_project("restore")
        skipped = db.mark_step_skipped("restore", self.step_id, "Decyzja technologa")
        self.assertIn("Pominięte w montażu", self.step(skipped)["notes"])
        restored = db.unskip_step("restore", self.step_id)
        self.assertEqual(self.step(restored)["notes"], self.notes + " | Decyzja technologa")
        self.assertNotIn("Pominięte w montażu", self.step()["notes"])
        self.assertEqual(restored["operator_step_statuses"], before["operator_step_statuses"])
        self.assertEqual(restored["points"], before["points"])
        self.assertEqual(restored["status"], before["status"])
        for key in ("id", "step_no", "designators", "value", "medcom_index", "quantity", "seconds", "segments_json"):
            self.assertEqual(self.step(restored)[key], self.step(before)[key], key)
        self.assertEqual(restored["changes"][0]["change_type"], "step_unskip")

    def test_only_exact_markers_are_removed_including_duplicates(self):
        notes = "Pominięte w montażu | " + self.notes + " |  Pominięte w montażu  | Instrukcja: Pominięte w montażu"
        db.update_step_notes("restore", self.step_id, notes)
        restored = db.unskip_step("restore", self.step_id)
        self.assertEqual(self.step(restored)["notes"], self.notes + " | Instrukcja: Pominięte w montażu")

    def test_wrong_project_or_missing_step_changes_nothing(self):
        before = db.get_project("restore")
        self.assertIsNone(db.unskip_step("other", self.step_id))
        self.assertIsNone(db.unskip_step("restore", self.step_id + 100))
        self.assertEqual(db.get_project("restore"), before)

    def test_http_restore_persists_on_reload_and_can_be_skipped_again(self):
        db.mark_step_skipped("restore", self.step_id)
        server = ThreadingHTTPServer(("127.0.0.1", 0), PlatformHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/api/projects"
        try:
            request = Request(f"{base}/restore/steps/{self.step_id}/unskip", data=b"{}",
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(self.step(json.load(response)["project"])["notes"], self.notes)
            with urlopen(f"{base}/restore", timeout=5) as response:
                self.assertEqual(self.step(json.load(response)["project"])["notes"], self.notes)
            wrong = Request(f"{base}/other/steps/{self.step_id}/unskip", data=b"{}",
                            headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as error:
                urlopen(wrong, timeout=5)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
            db.mark_step_skipped("restore", self.step_id)
            self.assertEqual(self.step()["notes"], self.notes + " | Pominięte w montażu")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
