from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.install_agents import load_templates


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-agents.sh"
PRESENTATION_NAMES = (
    "laneorchestrator-luna-executor.toml",
    "laneorchestrator-router.toml",
    "laneorchestrator-sol-reviewer.toml",
    "laneorchestrator-terra-executor.toml",
)


class InstallerTests(unittest.TestCase):
    def test_check_mode_reports_missing_profiles_without_creating_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing" / "agents"
            result = subprocess.run(
                ["sh", str(INSTALLER), "--check", "--target", str(target)],
                check=True, capture_output=True, text=True,
            )
            self.assertFalse(target.exists())
        self.assertEqual(
            result.stdout.splitlines(),
            ["missing {0}".format(target / name) for name in PRESENTATION_NAMES],
        )

    def test_legacy_adapter_never_mints_and_consumes_its_own_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "agents"
            result = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("preview", result.stderr.lower())
            self.assertIn("approval", result.stderr.lower())
            self.assertFalse(target.exists())

    def test_help_keeps_the_read_only_check_path_discoverable(self) -> None:
        result = subprocess.run(
            ["sh", str(INSTALLER), "--help"], check=True, capture_output=True, text=True,
        )
        self.assertIn("--check", result.stdout)
        self.assertIn("--target", result.stdout)

    def test_source_loading_rejects_missing_or_unsafe_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            templates = Path(directory)
            with self.assertRaises(SystemExit):
                load_templates(templates)
            source = ROOT / "agents" / PRESENTATION_NAMES[0]
            (templates / source.name).symlink_to(source)
            with self.assertRaises(SystemExit):
                load_templates(templates)

    def test_default_check_uses_isolated_home_and_remains_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment["HOME"] = directory
            result = subprocess.run(
                ["sh", str(INSTALLER), "--check"], check=True,
                capture_output=True, text=True, env=environment,
            )
            self.assertEqual(result.stdout.count("missing "), 4)
            self.assertFalse((Path(directory) / ".codex").exists())


if __name__ == "__main__":
    unittest.main()
