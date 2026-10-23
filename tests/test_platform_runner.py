import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import venv


@unittest.skipUnless(os.name == "nt", "Windows deployment runner")
class PlatformRunnerTests(unittest.TestCase):
    def test_python_stderr_and_all_process_exits_trigger_recovery(self):
        runner = Path(__file__).resolve().parents[1] / "run_platform_8780.ps1"
        with tempfile.TemporaryDirectory(prefix="inserter runner ") as directory:
            repo = Path(directory)
            venv.EnvBuilder(with_pip=False).create(repo / ".venv")
            package = repo / "inserter_platform"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            for exit_code in (0, 7):
                with self.subTest(exit_code=exit_code):
                    (package / "server.py").write_text(
                        "import sys\n"
                        "print('server output')\n"
                        "print('diagnostic on stderr', file=sys.stderr)\n"
                        f"sys.exit({exit_code})\n",
                        encoding="utf-8",
                    )
                    result = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                         "-File", str(runner), "-RepoPath", str(repo), "-Port", "18780"],
                        capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    lifecycle = (repo / "logs/inserter_platform_18780.lifecycle.log").read_text(encoding="utf-8-sig")
                    self.assertIn(f"Python exited: {exit_code}; scheduling recovery.", lifecycle)
                    self.assertNotIn("Runner failed:", lifecycle)
            logs = repo / "logs"
            self.assertEqual(len(list(logs.glob("*.stdout.log"))), 2)
            self.assertEqual(len(list(logs.glob("*.stderr.log"))), 2)
            for path in logs.glob("*.stdout.log"):
                self.assertIn("server output", path.read_text(encoding="utf-8"))
            for path in logs.glob("*.stderr.log"):
                self.assertIn("diagnostic on stderr", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
