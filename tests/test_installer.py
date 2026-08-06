from __future__ import annotations

import subprocess
import tempfile
import unittest
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-agents.sh"


class InstallerTests(unittest.TestCase):
    def test_collision_safe_installer(self) -> None:
        subprocess.run(["sh", str(ROOT / "tests" / "test_installer.sh")], check=True)

    def test_check_mode_reports_missing_profiles_without_creating_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing" / "agents"
            result = subprocess.run(["sh", str(INSTALLER), "--check", "--target", str(target)], check=True, capture_output=True, text=True)
            self.assertFalse(target.exists())
        self.assertEqual(result.stdout.count("missing "), 4)

    def test_new_profiles_are_private_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "agents"
            subprocess.run(["sh", str(INSTALLER), "--target", str(target)], check=True, capture_output=True, text=True)
            installed = sorted(target.glob("laneorchestrator-*.toml"))
            self.assertEqual(len(installed), 4)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in installed))

    def test_help_documents_safe_modes(self) -> None:
        result = subprocess.run(["sh", str(INSTALLER), "--help"], check=True, capture_output=True, text=True)
        self.assertIn("--check", result.stdout)
        self.assertIn("--target", result.stdout)

    def test_rejects_filesystem_root_as_target(self) -> None:
        result = subprocess.run(["sh", str(INSTALLER), "--target", "/"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("filesystem root", result.stderr)


if __name__ == "__main__":
    unittest.main()
