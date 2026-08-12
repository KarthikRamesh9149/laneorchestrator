from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_module(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "laneorchestrator", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def run_module_with_home(self, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        environment["PATH"] = ""
        return subprocess.run(
            [sys.executable, "-m", "laneorchestrator", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_version_json_returns_the_canonical_envelope(self) -> None:
        result = self.run_module("version", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "version")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["version"], "0.2.3")
        self.assertEqual(payload["diagnostics"], [])
        self.assertEqual(payload["errors"], [])

    def test_malformed_json_command_returns_structured_error(self) -> None:
        result = self.run_module("bogus", "--json")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ARGUMENTS")

    def test_malformed_json_arguments_return_structured_error(self) -> None:
        result = self.run_module("version", "--unexpected", "--json")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ARGUMENTS")

    def test_doctor_and_status_dispatch_to_canonical_read_only_results(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            home = Path(temporary)
            before = sorted(str(path.relative_to(home)) for path in home.rglob("*"))
            doctor = self.run_module_with_home(home, "doctor", "--json")
            status = self.run_module_with_home(home, "status", "--json")
            after = sorted(str(path.relative_to(home)) for path in home.rglob("*"))
        self.assertEqual(doctor.returncode, 1)
        self.assertEqual(json.loads(doctor.stdout)["command"], "doctor")
        self.assertEqual(status.returncode, 1)
        self.assertEqual(json.loads(status.stdout)["command"], "status")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
