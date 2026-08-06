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
        self.assertEqual(route("--objective", "fix a typo in the readme", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")["lane"], "luna")

    def test_terra_for_normal_feature_work(self) -> None:
        self.assertEqual(route("--objective", "add a dashboard filter", "--files", "4", "--risk-assessment", "normal")["lane"], "terra")

    def test_sol_review_for_auth_migration(self) -> None:
        self.assertEqual(route("--objective", "migrate OAuth authentication schema", "--files", "5")["lane"], "sol-plan-terra-sol-review")

    def test_unknown_risk_does_not_select_luna(self) -> None:
        result = route("--objective", "change account recovery browser origin and issuer checks", "--known-area", "--acceptance-criteria", "--files", "1")
        self.assertEqual(result["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(result["reason"], "risk assessment required")

    def test_high_risk_terms_override_low_risk_assessment(self) -> None:
        self.assertEqual(route("--objective", "change authentication settings", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")["lane"], "sol-plan-terra-sol-review")


if __name__ == "__main__":
    unittest.main()
