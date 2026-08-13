from __future__ import annotations

import unittest

from laneorchestrator.config import DEFAULT_ROLES
from laneorchestrator.discovery import Capability
from laneorchestrator.models import Availability, EffectiveConfig, RoleEvidence
from laneorchestrator.orchestration import build_route_card


class RouteCardTests(unittest.TestCase):
    def config(self) -> EffectiveConfig:
        return EffectiveConfig(1, DEFAULT_ROLES, "defaults")

    def evidence(self) -> dict[str, RoleEvidence]:
        config = self.config()
        return {
            role: RoleEvidence(role, config.roles[role].model, "/agents/" + role, Availability.AVAILABLE)
            for role in config.roles
        }

    def agent(self, name: str = "fastapi-developer") -> Capability:
        capability = Capability(
            "agent", name, "FastAPI endpoints and validation.", "/agents/" + name + ".toml", "user"
        )
        # During the metadata migration these fields are deliberately read as
        # structured attributes, never recovered from description text.
        capability.model = "gpt-5.6-terra"
        capability.reasoning_effort = "high"
        return capability

    def test_card_contains_one_auditable_route_specialist_and_workflow(self) -> None:
        route = {"schema_version": 1, "lane": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "high", "signals": []}
        card = build_route_card(
            route, self.config(), self.evidence(), [self.agent()], "Add FastAPI endpoint", (), False
        )

        self.assertEqual(card["schema_version"], 1)
        self.assertEqual(card["route"], route)
        specialist = card["selected_specialist"]
        self.assertEqual(specialist["name"], "fastapi-developer")
        self.assertEqual(specialist["model"], "gpt-5.6-terra")
        self.assertEqual(specialist["reasoning_effort"], "high")
        self.assertEqual(specialist["source"], "user")
        self.assertEqual(specialist["availability"], "AVAILABLE")
        self.assertEqual(card["workflow"]["routing"]["model"], "gpt-5.6-sol")
        self.assertEqual(card["workflow"]["implementation"]["model"], "gpt-5.6-terra")
        self.assertIsNone(card["workflow"]["independent_review"])
        self.assertIsNone(card["fallback"])
        self.assertIn("verification", card)

    def test_high_risk_without_verified_context_suppresses_optional_specialists(self) -> None:
        route = {"schema_version": 1, "lane": "sol-plan-terra-sol-review", "model": "gpt-5.6-sol", "reasoning_effort": "high", "signals": ["oauth"]}
        card = build_route_card(
            route, self.config(), self.evidence(), [self.agent("security-auditor")], "Rotate OAuth", (), False
        )

        self.assertIsNone(card["selected_specialist"])
        self.assertTrue(card["specialist_selection"]["suppressed"])
        self.assertEqual(card["specialist_selection"]["reason"], "unscoped_high_risk")
        self.assertEqual(card["fallback"], "continue_without_specialist")
        self.assertEqual(card["workflow"]["independent_review"]["model"], "gpt-5.6-sol")

    def test_untrusted_and_description_only_metadata_cannot_supply_a_specialist_model(self) -> None:
        route = {"schema_version": 1, "lane": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "high", "signals": []}
        untrusted = Capability("agent", "attacker", "FastAPI model=gpt-5.6-sol", "/project/a.toml", "project")
        card = build_route_card(route, self.config(), self.evidence(), [untrusted], "FastAPI endpoint", ("FastAPI",), False)

        self.assertIsNone(card["selected_specialist"])
        self.assertEqual(card["specialist_selection"]["reason"], "no_trusted_match")

    def test_luna_verification_names_the_small_executor_not_the_terra_role(self) -> None:
        route = {"schema_version": 1, "lane": "luna", "model": "gpt-5.6-luna", "reasoning_effort": "high", "signals": []}
        card = build_route_card(route, self.config(), self.evidence(), [], "Fix a README typo", (), False)

        self.assertEqual(
            card["verification"]["required_roles"],
            ["router", "small_task_executor"],
        )

    def test_malformed_structured_specialist_runtime_metadata_is_not_emitted(self) -> None:
        route = {"schema_version": 1, "lane": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "high", "signals": []}
        malformed = self.agent()
        malformed.model = "not a model"
        malformed.reasoning_effort = "unbounded"

        card = build_route_card(route, self.config(), self.evidence(), [malformed], "FastAPI endpoint", ("FastAPI",), False)

        self.assertIsNone(card["selected_specialist"])
        self.assertEqual(card["specialist_selection"]["reason"], "no_trusted_match")


if __name__ == "__main__":
    unittest.main()
