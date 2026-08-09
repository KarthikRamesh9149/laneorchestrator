from __future__ import annotations

import json
import subprocess
import sys
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

    def test_version_json_returns_the_canonical_envelope(self) -> None:
        result = self.run_module("version", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "version")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["version"], "0.2.0")
        self.assertEqual(payload["diagnostics"], [])
        self.assertEqual(payload["errors"], [])

    def test_malformed_json_command_returns_structured_error(self) -> None:
        result = self.run_module("bogus", "--json")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "invalid_arguments")

    def test_malformed_json_arguments_return_structured_error(self) -> None:
        result = self.run_module("version", "--unexpected", "--json")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["errors"][0]["code"], "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
