from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "laneorchestrator" / "scripts" / "route.py"


def route(*args: str) -> dict[str, object]:
    result = subprocess.run(["python3", str(SCRIPT), *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class RouteTests(unittest.TestCase):
    def test_luna_for_bounded_local_work(self) -> None:
        self.assertEqual(route("--objective", "fix a typo in the readme", "--known-area", "--acceptance-criteria", "--files", "1")["lane"], "luna")

    def test_terra_for_normal_feature_work(self) -> None:
        self.assertEqual(route("--objective", "add a dashboard filter", "--files", "4")["lane"], "terra")

    def test_sol_review_for_auth_migration(self) -> None:
        self.assertEqual(route("--objective", "migrate OAuth authentication schema", "--files", "5")["lane"], "sol-plan-terra-sol-review")


if __name__ == "__main__":
    unittest.main()
