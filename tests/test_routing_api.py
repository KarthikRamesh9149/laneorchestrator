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
