from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "skills" / "laneorchestrator" / "scripts" / "route.py"
CATALOG = ROOT / "skills" / "laneorchestrator" / "scripts" / "catalog.py"


def run_json(script: Path, *args: str) -> dict[str, object]:
    result = subprocess.run(["python3", str(script), *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class EndToEndTests(unittest.TestCase):
    def test_bounded_change_uses_luna_lane(self) -> None:
        route = run_json(ROUTE, "--objective", "fix a README title typo", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")
        catalog = run_json(CATALOG, "--query", "fix a README title typo", "--cwd", str(ROOT), "--no-default-roots", "--agents-root", str(ROOT / "agents"))
        self.assertEqual(route["lane"], "luna")
        self.assertIn("laneorchestrator-luna-executor", [item["name"] for item in catalog["lane_agents"]])

    def test_unscoped_auth_migration_uses_only_control_plane(self) -> None:
        route = run_json(ROUTE, "--objective", "migrate OAuth token storage and public authentication endpoints for production", "--files", "4")
        catalog = run_json(CATALOG, "--query", "migrate OAuth token storage and public authentication endpoints for production", "--cwd", str(ROOT), "--no-default-roots", "--agents-root", str(ROOT / "agents"), "--unscoped-high-risk")
        self.assertEqual(route["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(catalog["skills"], [])
        self.assertEqual(catalog["agents"], [])
        self.assertEqual({item["name"] for item in catalog["lane_agents"]}, {"laneorchestrator-router", "laneorchestrator-luna-executor", "laneorchestrator-terra-executor", "laneorchestrator-sol-reviewer"})


if __name__ == "__main__":
    unittest.main()
