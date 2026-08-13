from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "laneorchestrator" / "scripts" / "route.py"


def route(*args: str) -> dict[str, object]:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def rejected_route(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class RouteTests(unittest.TestCase):
    def test_wrapper_has_no_routing_policy_constants(self) -> None:
        wrapper = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("HIGH_RISK_TERMS", "HIGH_RISK_PHRASES", "recommend_route"):
            self.assertNotIn(forbidden, wrapper)

    def test_luna_for_bounded_local_work(self) -> None:
        self.assertEqual(route("--objective", "fix a typo in the readme", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")["lane"], "luna")

    def test_terra_for_normal_feature_work(self) -> None:
        self.assertEqual(route("--objective", "add a dashboard filter", "--files", "4", "--risk-assessment", "normal")["lane"], "terra")

    def test_sol_review_for_auth_migration(self) -> None:
        self.assertEqual(route("--objective", "migrate OAuth authentication schema", "--files", "5")["lane"], "sol-plan-terra-sol-review")

    def test_unknown_risk_does_not_select_luna(self) -> None:
        result = route("--objective", "change a dashboard label", "--known-area", "--acceptance-criteria", "--files", "1")
        self.assertEqual(result["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(result["reason"], "risk assessment required")

    def test_high_risk_terms_override_low_risk_assessment(self) -> None:
        self.assertEqual(route("--objective", "change authentication settings", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")["lane"], "sol-plan-terra-sol-review")

    def test_hyphenated_risk_phrase_cannot_evade_detection(self) -> None:
        result = route("--objective", "Change account-recovery trusted_issuer checks", "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")
        self.assertEqual(result["lane"], "sol-plan-terra-sol-review")
        self.assertIn("account recovery", result["signals"])
        self.assertIn("trusted issuer", result["signals"])

    def test_incomplete_low_risk_facts_fall_back_to_terra(self) -> None:
        result = route("--objective", "Fix a README typo", "--known-area", "--files", "1", "--risk-assessment", "low")
        self.assertEqual(result["lane"], "terra")
        self.assertEqual(result["reason"], "low-risk requirements not met")

    def test_decision_includes_auditable_assessment(self) -> None:
        result = route("--objective", "Add a dashboard filter", "--files", "3", "--risk-assessment", "normal")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["assessment"], {"risk": "normal", "known_area": False, "acceptance_criteria": False, "files": 3})

    def test_rejects_blank_objective(self) -> None:
        result = rejected_route("--objective", "   ")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not be blank", result.stderr)

    def test_rejects_non_positive_file_count(self) -> None:
        result = rejected_route("--objective", "Fix a typo", "--files", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be at least 1", result.stderr)

    def test_rejects_unbounded_objective(self) -> None:
        result = rejected_route("--objective", "x" * (16 * 1024 + 1))
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not exceed", result.stderr)

    def test_adversarial_high_risk_phrases_override_low_risk_claim(self) -> None:
        objectives = (
            "Change OAuth2 refresh behavior",
            "Update OpenID Connect claims",
            "Adjust the sign-in cookie",
            "Modify JWT validation",
            "Change CORS allowlists",
            "Rotate the TLS certificate",
            "Update KMS configuration",
            "Restore a customer backup",
            "Change infrastructure firewall rules",
            "Update tenant-isolation checks",
            "Modify audit-log redaction",
            "Change medical record handling",
            "Adjust tax settlement calculations",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                result = route("--objective", objective, "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low")
                self.assertEqual(result["lane"], "sol-plan-terra-sol-review")
                self.assertTrue(result["signals"])

    def test_cli_routes_security_sensitive_normal_risk_objectives_to_sol_review(self) -> None:
        cases = {
            "SAML assertion validation": "saml assertion",
            "signing-key rotation": "signing key",
            "Prevent path traversal": "path traversal",
            "Prevent arbitrary file reads": "arbitrary file reads",
        }
        for objective, signal in cases.items():
            with self.subTest(objective=objective):
                result = route("--objective", objective, "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "normal")
                self.assertEqual(result["lane"], "sol-plan-terra-sol-review")
                self.assertEqual(result["reason"], "high-risk signal")
                self.assertIn(signal, result["signals"])


if __name__ == "__main__":
    unittest.main()
