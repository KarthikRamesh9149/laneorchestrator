from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class InstallerTests(unittest.TestCase):
    def test_collision_safe_installer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        subprocess.run(["sh", str(root / "tests" / "test_installer.sh")], check=True)


if __name__ == "__main__":
    unittest.main()
