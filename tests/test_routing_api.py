from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import subprocess
import sys
import unittest
from pathlib import Path

from laneorchestrator.routing import RouteFacts, high_risk_signals, recommend_route, validate_route_facts


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "laneorchestrator" / "scripts" / "route.py"


def route(*args: str) -> dict[str, object]:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class RoutingApiTests(unittest.TestCase):
    def test_luna_for_bounded_known_area_work(self) -> None:
        route_data = recommend_route(RouteFacts("Fix a README typo", True, True, 1, "low"))
        self.assertEqual(route_data["lane"], "luna")
        self.assertEqual(route_data["model"], "gpt-5.6-luna")

    def test_terra_for_normal_work(self) -> None:
        route_data = recommend_route(RouteFacts("Add a dashboard filter", False, True, 3, "normal"))
        self.assertEqual(route_data["lane"], "terra")
        self.assertEqual(route_data["model"], "gpt-5.6-terra")

    def test_high_risk_work_uses_sol_plan_terra_sol_review(self) -> None:
        route_data = recommend_route(RouteFacts("Migrate OAuth token storage", False, False, 4, "high"))
        self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(route_data["model"], "gpt-5.6-sol")

    def test_unknown_risk_never_selects_luna(self) -> None:
        route_data = recommend_route(RouteFacts("Fix a README typo", True, True, 1, "unknown"))
        self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(route_data["reason"], "risk assessment required")

    def test_high_risk_signal_overrides_low_risk_claim(self) -> None:
        route_data = recommend_route(RouteFacts("Change authentication settings", True, True, 1, "low"))
        self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(route_data["reason"], "high-risk signal")

    def test_punctuation_and_aliases_cannot_evade_signals(self) -> None:
        self.assertEqual(high_risk_signals("Update OAuth2 trusted_issuer checks"), ["oauth", "trusted issuer"])

    def test_route_facts_are_immutable(self) -> None:
        facts = RouteFacts("Fix a README typo", True, True, 1, "low")
        with self.assertRaises(FrozenInstanceError):
            facts.risk = "high"  # type: ignore[misc]

    def test_validate_route_facts_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_route_facts(RouteFacts("  ", True, True, 1, "low"))
        with self.assertRaises(ValueError):
            validate_route_facts(RouteFacts("x" * (16 * 1024 + 1), True, True, 1, "low"))
        with self.assertRaises(ValueError):
            validate_route_facts(RouteFacts("Fix a typo", True, True, 0, "low"))
        with self.assertRaises(ValueError):
            validate_route_facts(RouteFacts("Fix a typo", True, True, 1, "unsafe"))

    def test_validate_route_facts_rejects_noncanonical_runtime_types(self) -> None:
        invalid_facts = (
            RouteFacts("Fix a README typo", "false", True, 1, "low"),
            RouteFacts("Fix a README typo", True, "false", 1, "low"),
            RouteFacts("Fix a README typo", True, True, True, "low"),
            RouteFacts("Fix a README typo", True, True, 1.0, "low"),
            RouteFacts(1, True, True, 1, "low"),  # type: ignore[arg-type]
            RouteFacts("Fix a README typo", True, True, 1, None),  # type: ignore[arg-type]
        )
        for facts in invalid_facts:
            with self.subTest(facts=facts):
                with self.assertRaises(ValueError):
                    recommend_route(facts)

    def test_unrecognized_or_unicode_low_risk_objectives_never_select_luna(self) -> None:
        objectives = (
            "Prevent account takeover through a harmless-looking text update",
            "Patch a SQL injection weakness in one response string",
            "Update one API token label",
            "Fix a p\u0430ssword reset label",
            "Update pass\u200bword recovery documentation link",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "low"))
                self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")

    def test_unicode_confusables_cannot_downgrade_normal_risk_security_work(self) -> None:
        objective = "Reset p\u0430ssword recovery flow"

        route_data = recommend_route(RouteFacts(objective, True, True, 1, "normal"))

        self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(route_data["reason"], "non-ASCII objective requires review")

    def test_common_security_and_financial_phrases_cannot_downgrade_normal_risk_work(self) -> None:
        objectives = (
            "Fix SQL injection in the API",
            "Mitigate cross-site scripting vulnerability",
            "Change wire transfer approval rules",
            "Update personal data export policy",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "normal"))
                self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
                self.assertEqual(route_data["reason"], "high-risk signal")

    def test_security_sensitive_normal_risk_objectives_require_sol_review(self) -> None:
        cases = {
            "SAML assertion validation": "saml assertion",
            "signing-key rotation": "signing key",
            "Prevent path traversal": "path traversal",
            "Prevent arbitrary file reads": "arbitrary file reads",
        }
        for objective, signal in cases.items():
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "normal"))
                self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
                self.assertEqual(route_data["reason"], "high-risk signal")
                self.assertIn(signal, route_data["signals"])

    def test_security_signal_phrases_do_not_match_safe_subphrases(self) -> None:
        objectives = (
            "Update a test assertion message",
            "Read a local fixture file in a unit test",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "normal"))
                self.assertEqual(route_data["lane"], "terra")
                self.assertEqual(route_data["signals"], [])

    def test_high_risk_aliases_and_synonyms_cannot_downgrade_low_risk_claims(self) -> None:
        objectives = (
            "Rotate web-hook signing secret",
            "Change authorisation checks",
            "Update authz policy",
            "Enforce 2FA enrollment",
            "Decrypt archived customer records",
            "Coordinate production deployments",
            "Mitigate RCE exposure",
            "Prevent SSRF requests",
            "Update credit card chargebacks",
            "Perform data erasure request",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "low"))
                self.assertEqual(route_data["lane"], "sol-plan-terra-sol-review")
                self.assertEqual(route_data["reason"], "high-risk signal")

    def test_bounded_ascii_editorial_objectives_keep_luna_eligibility(self) -> None:
        objectives = (
            "Replace one screenshot alt text in a known guide",
            "Update one example command flag in a known tutorial",
            "Correct one diagram caption in the operations guide",
            "Fix one product name spelling in the FAQ",
        )
        for objective in objectives:
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "low"))
                self.assertEqual(route_data["lane"], "luna")

    def test_common_bounded_one_file_objectives_keep_luna_eligibility(self) -> None:
        cases = {
            "Fix a typo": "luna",
            "Fix a spelling mistake": "luna",
            "Correct documentation typo": "luna",
            "Update one README sentence": "luna",
            "Rename a local variable": "luna",
            "Fix one CLI error message": "luna",
            "Fix a password typo": "sol-plan-terra-sol-review",
            "Update one API token sentence": "sol-plan-terra-sol-review",
        }
        for objective, expected_lane in cases.items():
            with self.subTest(objective=objective):
                route_data = recommend_route(RouteFacts(objective, True, True, 1, "low"))
                self.assertEqual(route_data["lane"], expected_lane)

    def test_api_matches_legacy_json(self) -> None:
        facts = RouteFacts("Fix a README typo", True, True, 1, "low")
        direct = recommend_route(facts)
        legacy = route(
            "--objective", facts.objective, "--known-area", "--acceptance-criteria",
            "--files", "1", "--risk-assessment", "low",
        )
        self.assertEqual(direct, legacy)


if __name__ == "__main__":
    unittest.main()
