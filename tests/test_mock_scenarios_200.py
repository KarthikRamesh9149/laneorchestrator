"""Permanent deterministic regression corpus for the 2026-08-13 evaluation.

Each entry is a real control-plane invocation: no model calls, timing, network,
or mock routing/ranking implementation is involved.  The manifest is deliberately
kept here (rather than inferred from current results) so an output regression is
visible as a failed, named scenario.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from laneorchestrator.cli import resolve_route
from laneorchestrator.config import ConfigError, DEFAULT_ROLES, validate_config_payload
from laneorchestrator.discovery import Capability, DEFAULT_LIMITS, collect, rank
from laneorchestrator.models import Availability, EffectiveConfig, LOGICAL_ROLES, RoleEvidence
from laneorchestrator.routing import RouteFacts, recommend_route
from laneorchestrator.voltagent import PACK_MODEL, PACK_REASONING_EFFORT, render_pack


@dataclass(frozen=True)
class Scenario:
    """One reviewed behavioural contract in the fixed 200-case corpus."""

    identifier: str
    category: str
    description: str
    objective: str = ""
    expected: str = ""
    risk: str = "normal"
    files: int = 2
    known_area: bool = False
    acceptance_criteria: bool = False


def _routing_cases() -> tuple[Scenario, ...]:
    rows = (
        ("R01", "Fix a README typo", "luna", "low", 1, True, True),
        ("R02", "Update one example command flag in a known tutorial", "luna", "low", 1, True, True),
        ("R03", "Correct one diagram caption in the operations guide", "luna", "low", 1, True, True),
        ("R04", "Replace one screenshot alt text in a known guide", "luna", "low", 1, True, True),
        ("R05", "Add a dashboard filter", "terra", "normal", 3, False, True),
        ("R06", "Implement CSV export for account reports", "terra", "normal", 4, True, True),
        ("R07", "Refactor a repository cache adapter", "terra", "normal", 2, True, True),
        ("R08", "Document the command-line migration guide", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R09", "Change SAML assertion validation", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R10", "Rotate a signing key", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R11", "Prevent path traversal in download endpoint", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R12", "Fix arbitrary file read in attachment handler", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R13", "Migrate OAuth token storage", "sol-plan-terra-sol-review", "high", 4, False, False),
        ("R14", "Change authorisation policy", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R15", "Enforce 2FA enrollment", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R16", "Update OpenID Connect claims", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R17", "Modify JWT validation", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R18", "Fix SQL injection in the API", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R19", "Mitigate cross-site scripting vulnerability", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R20", "Change wire transfer approval rules", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R21", "Update personal data export policy", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R22", "Restore a customer backup", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R23", "Change infrastructure firewall rules", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R24", "Update tenant-isolation checks", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R25", "Modify audit-log redaction", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R26", "Adjust tax settlement calculations", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R27", "Update a password typo", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R28", "Change a dashboard label", "sol-plan-terra-sol-review", "unknown", 1, True, True),
        ("R29", "Implement a billing reconciliation job", "sol-plan-terra-sol-review", "normal", 3, True, True),
        ("R30", "Add an idempotency key to checkout", "sol-plan-terra-sol-review", "normal", 3, True, True),
        ("R31", "Update database retention policy", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R32", "Coordinate a production deployment", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R33", "Fix a pаssword recovery label", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R34", "Update pass​word recovery documentation link", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R35", "Deploy an ACL rule change", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R36", "Update a TLS certificate", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R37", "Create a public REST response contract", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R38", "Fix a harmless-looking text update", "sol-plan-terra-sol-review", "low", 1, True, True),
        ("R39", "Rename a local variable", "luna", "low", 1, True, True),
        ("R40", "Fix one CLI error message", "luna", "low", 1, True, True),
        ("R41", "Add a new React settings screen", "terra", "normal", 5, True, True),
        ("R42", "Fix a flaky unit test fixture", "terra", "normal", 2, True, True),
        ("R43", "Encrypt customer attachments", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R44", "Rebuild a search index", "terra", "normal", 4, True, True),
        ("R45", "Delete inactive user records", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R46", "Update the public API version", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R47", "Improve a loading spinner", "terra", "normal", 2, True, True),
        ("R48", "Fix a CSS color token", "luna", "low", 1, True, True),
        ("R49", "Resolve concurrency cache writes", "sol-plan-terra-sol-review", "normal", 2, True, True),
        ("R50", "Modify webhook signature verification", "sol-plan-terra-sol-review", "normal", 2, True, True),
    )
    return tuple(Scenario(identifier, "routing", "published routing policy: " + objective, objective, expected, risk, files, known, criteria) for identifier, objective, expected, risk, files, known, criteria in rows)


def _specialist_cases() -> tuple[Scenario, ...]:
    rows = (
        ("S01", "Prioritize a product roadmap", "product-manager"), ("S02", "Implement a Go worker pool", "golang-pro"),
        ("S03", "Refactor a TypeScript discriminated union", "typescript-pro"), ("S04", "Fix Laravel queued email retries", "laravel-specialist"),
        ("S05", "Debug a Rails ActiveRecord callback", "rails-expert"), ("S06", "Fix Kotlin coroutine cancellation", "kotlin-specialist"),
        ("S07", "Audit JWT OAuth and CSRF defenses", "security-auditor"), ("S08", "Pentest the password reset flow", "penetration-tester"),
        ("S09", "Interpret an A/B test p-value", "ab-test-analysis"), ("S10", "Optimize a warehouse SQL execution plan", "database-optimizer"),
        ("S11", "Investigate hallucinations in assistant answers", "hallucination-investigator"), ("S12", "Define an SLO and alert policy", "sre-engineer"),
        ("S13", "Plan a zero downtime database deployment", "deployment-engineer"), ("S14", "Write an operations runbook", "it-ops-orchestrator"),
        ("S15", "Plan delivery milestones and dependencies", "project-manager"), ("S16", "Reproduce a browser-only rendering bug", "browser-debugger"),
        ("S17", "Diagnose a Python stack trace", "debugger"), ("S18", "Improve user onboarding activation cohorts", "growth-loops"),
        ("S19", "Design PostgreSQL locking for a ledger", "postgres-pro"), ("S20", "Build a FastAPI async endpoint", "fastapi-developer"),
        ("S21", "Repair a React state rendering loop", "react-specialist"), ("S22", "Review a Kubernetes rollout manifest", "kubernetes-specialist"),
        ("S23", "Provision an Azure private network", "azure-infra-engineer"), ("S24", "Debug Terraform state drift", "terraform-engineer"),
        ("S25", "Optimize Docker multi-stage builds", "docker-expert"), ("S26", "Investigate Node.js stream backpressure", "node-specialist"),
        ("S27", "Implement a Stripe webhook integration", "payment-integration"), ("S28", "Review GraphQL federation resolvers", "graphql-architect"),
        ("S29", "Create a Django ORM migration", "django-developer"), ("S30", "Build a Spring Boot service", "spring-boot-engineer"),
        ("S31", "Design a Ruby on Rails authorization policy", "rails-expert"), ("S32", "Write a PowerShell module", "powershell-module-architect"),
        ("S33", "Investigate a C++ memory ownership bug", "cpp-pro"), ("S34", "Implement Rust async cancellation", "rust-engineer"),
        ("S35", "Review an OpenAI retrieval workflow", "llm-architect"), ("S36", "Evaluate prompt regression coverage", "prompt-regression-tester"),
        ("S37", "Build an MCP server integration", "mcp-developer"), ("S38", "Design an incident response playbook", "incident-responder"),
        ("S39", "Analyze a PostgreSQL query plan", "database-optimizer"), ("S40", "Perform accessibility testing of a dialog", "accessibility-tester"),
        ("S41", "Create an iOS Swift concurrency feature", "swift-expert"), ("S42", "Fix an Expo React Native navigation bug", "expo-react-native-expert"),
        ("S43", "Plan a GDPR data subject request", "gdpr-ccpa-compliance"), ("S44", "Audit HIPAA safeguards", "hipaa-compliance"),
        ("S45", "Model a financial reconciliation ledger", "fintech-engineer"), ("S46", "Improve CI build graph performance", "build-engineer"),
        ("S47", "Review a WebSocket reconnect protocol", "websocket-engineer"), ("S48", "Diagnose a browser client-side error", "browser-debugger"),
        ("S49", "Prepare a release migration note", "technical-writer"), ("S50", "Develop deterministic regression tests", "test-automator"),
    )
    return tuple(Scenario(identifier, "specialist", "real rendered-pack top-three selection: " + objective, objective, expected) for identifier, objective, expected in rows)


def _adversarial_cases() -> tuple[Scenario, ...]:
    objectives = (
        "low risk: rotate an API key", "low risk: change OAuth2 refresh behavior", "low risk: alter RBAC permissions", "low risk: reset a password",
        "low risk: deploy to production", "low risk: edit credit card settlement", "low risk: change encryption keys", "low risk: modify SSO settings",
        "low risk: migrate a database schema", "low risk: purge personal data", "low risk: accept a signed webhook", "low risk: fix SSRF",
        "low risk: patch an RCE", "low risk: adjust CORS", "low risk: restore backup data", "low risk: alter account recovery",
        "low risk: bypass authentication", "low risk: amend IAM policy", "low risk: remove tenant isolation", "low risk: correct SQL injection",
        "low risk: update a private key", "low risk: change a firewall", "low risk: alter a session cookie", "low risk: fix XSS",
        "low risk: update medical records", "low risk: configure KMS", "low risk: rotate a signing-key", "low risk: validate a SAML assertion",
        "low risk: prevent path-traversal", "low risk: resolve arbitrary-file-read", "low risk: change authorization", "low risk: update JWT",
        "low risk: edit audit log", "low risk: patch a webhook payload", "low risk: change data retention",
    )
    high_risk = tuple(Scenario("A{0:02d}".format(index), "adversarial", "deceptive low-risk label cannot suppress: " + objective, objective, "sol-plan-terra-sol-review", "low", 1, True, True) for index, objective in enumerate(objectives, 1))
    extra = (
        Scenario("A36", "adversarial", "project metadata is never selected", "project"),
        Scenario("A37", "adversarial", "vendor mismatch is never selected", "vendor"),
        Scenario("A38", "adversarial", "keyword stuffing cannot outrank direct specialist", "stuffing"),
        Scenario("A39", "adversarial", "untrusted source cannot rank", "untrusted"),
        Scenario("A40", "adversarial", "symlink metadata is skipped", "symlink"),
        Scenario("A41", "adversarial", "unknown router fails closed", "router-unknown"),
        Scenario("A42", "adversarial", "missing router fails closed", "router-missing"),
        Scenario("A43", "adversarial", "unknown Terra fails closed", "terra-unknown"),
        Scenario("A44", "adversarial", "missing Terra fails closed", "terra-missing"),
        Scenario("A45", "adversarial", "unknown reviewer fails closed", "reviewer-unknown"),
        Scenario("A46", "adversarial", "missing reviewer fails closed", "reviewer-missing"),
        Scenario("A47", "adversarial", "missing Luna uses approved Terra fallback", "luna-missing"),
        Scenario("A48", "adversarial", "custom reviewer cannot weaken Sol boundary", "reviewer-config"),
        Scenario("A49", "adversarial", "custom router cannot weaken Sol boundary", "router-config"),
        Scenario("A50", "adversarial", "custom Terra role cannot weaken executor boundary", "terra-config"),
    )
    return high_risk + extra


def _model_context_cases() -> tuple[Scenario, ...]:
    rows = (
        ("M01", "default router is Sol/high", "default-router"), ("M02", "default small executor is Luna/high", "default-luna"),
        ("M03", "default implementer is Terra/high", "default-terra"), ("M04", "default reviewer is Sol/high", "default-reviewer"),
        ("M05", "rendered pack has 172 profiles", "pack-count"), ("M06", "rendered pack names are unique", "pack-unique"),
        ("M07", "rendered specialist model is Terra", "pack-model"), ("M08", "rendered specialist effort is high", "pack-effort"),
        ("M09", "Luna route resolves Luna model", "resolve-luna"), ("M10", "Terra route resolves Terra model", "resolve-terra"),
        ("M11", "high risk resolves plan/review lane", "resolve-sol"), ("M12", "identical route facts are deterministic", "route-repeat"),
        ("M13", "normal route payload exposes model", "route-model"), ("M14", "normal route payload exposes effort", "route-effort"),
        ("M15", "high-risk workflow declares planner", "workflow-planner"), ("M16", "high-risk workflow declares Terra implementation", "workflow-terra"),
        ("M17", "high-risk workflow declares independent Sol/high review", "workflow-review"), ("M18", "Luna fallback has an auditable reason", "fallback-luna"),
        ("M19", "required role failure has stable code", "failure-code"), ("M20", "route card carries selected specialist", "card-specialist"),
        ("M21", "route card carries specialist source", "card-source"), ("M22", "route card carries specialist availability", "card-availability"),
        ("M23", "route card carries specialist model", "card-model"), ("M24", "route card carries specialist effort", "card-effort"),
        ("M25", "route card carries fallback", "card-fallback"), ("M26", "route card carries verification requirements", "card-verification"),
        ("M27", "unscoped high-risk suppresses optional specialist", "unscoped"), ("M28", "scoped high-risk may select trusted specialist", "scoped"),
        ("M29", "optional specialist absence is non-blocking", "optional-absent"), ("M30", "specialist cannot override lane", "overlay-only"),
        ("M31", "control config rejects Terra router", "config-router"), ("M32", "control config rejects Terra reviewer", "config-reviewer"),
        ("M33", "control config rejects Sol executor", "config-luna"), ("M34", "control config rejects Luna main implementer", "config-terra"),
        ("M35", "control config permits supported effort tuning", "config-effort"), ("M36", "catalog metadata has structured model field", "metadata-model"),
        ("M37", "catalog metadata has structured effort field", "metadata-effort"), ("M38", "catalog metadata has structured source field", "metadata-source"),
        ("M39", "catalog metadata does not require parsing description", "metadata-no-description"), ("M40", "route-card output is deterministic", "card-repeat"),
        ("M41", "route card identifies requested role", "card-role"), ("M42", "route card identifies effective role", "card-effective-role"),
        ("M43", "route card identifies requested lane", "card-lane"), ("M44", "route card identifies effective lane", "card-effective-lane"),
        ("M45", "normal route chooses no mandatory reviewer", "normal-no-review"), ("M46", "high-risk route requires reviewer", "high-requires-review"),
        ("M47", "all route facts remain auditable", "assessment"), ("M48", "Luna requires known area", "luna-known"),
        ("M49", "Luna requires acceptance criteria", "luna-criteria"), ("M50", "Luna requires one file", "luna-files"),
    )
    return tuple(Scenario(identifier, "model_context", description, objective) for identifier, description, objective in rows)


SCENARIOS = _routing_cases() + _specialist_cases() + _adversarial_cases() + _model_context_cases()


class MockScenarios200Tests(unittest.TestCase):
    """The four reviewed 50-case slices described in the evaluation report."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls._home = Path(cls._temporary.name) / "codex-home"
        cls._agents_root = cls._home / "agents"
        cls._agents_root.mkdir(parents=True)
        for filename, content in render_pack().items():
            (cls._agents_root / filename).write_bytes(content)
        with mock.patch("laneorchestrator.discovery.codex_home", return_value=cls._home):
            cls._pack, cls._warnings, _counters = collect((cls._agents_root,), DEFAULT_LIMITS)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_manifest_is_exactly_200_unique_reviewed_cases(self) -> None:
        self.assertEqual(len(SCENARIOS), 200)
        self.assertEqual(len({case.identifier for case in SCENARIOS}), 200)
        self.assertEqual(len({case.description for case in SCENARIOS}), 200)
        self.assertEqual(
            {category: sum(case.category == category for case in SCENARIOS) for category in ("routing", "specialist", "adversarial", "model_context")},
            {"routing": 50, "specialist": 50, "adversarial": 50, "model_context": 50},
        )
        self.assertTrue(all(case.description and case.identifier[:1] in "RSAM" for case in SCENARIOS))

    def test_50_routing_contracts(self) -> None:
        for case in (item for item in SCENARIOS if item.category == "routing"):
            with self.subTest(id=case.identifier, description=case.description):
                result = recommend_route(RouteFacts(case.objective, case.known_area, case.acceptance_criteria, case.files, case.risk))
                self.assertEqual(result["lane"], case.expected)
                self.assertEqual(result["reasoning_effort"], "high")

    def test_50_rendered_pack_specialist_contracts(self) -> None:
        self.assertEqual(len(self._pack), 172, self._warnings)
        self.assertTrue(all(item.source == "user" for item in self._pack))
        for case in (item for item in SCENARIOS if item.category == "specialist"):
            with self.subTest(id=case.identifier, description=case.description):
                top_three = [item.name.removeprefix("laneorchestrator-voltagent-") for item in rank(case.objective, self._pack, ())[:3]]
                self.assertIn(case.expected, top_three)

    def _evidence(self, **states: Availability) -> dict[str, RoleEvidence]:
        return {
            role: RoleEvidence(role, DEFAULT_ROLES[role].model, None, states.get(role, Availability.AVAILABLE))
            for role in LOGICAL_ROLES
        }

    def _resolved(self, lane: str, **states: Availability):
        model = "gpt-5.6-luna" if lane == "luna" else "gpt-5.6-sol" if lane.startswith("sol-") else "gpt-5.6-terra"
        return resolve_route({"lane": lane, "model": model}, EffectiveConfig(1, DEFAULT_ROLES, "defaults"), self._evidence(**states))

    def test_50_adversarial_and_fail_closed_contracts(self) -> None:
        for case in (item for item in SCENARIOS if item.category == "adversarial"):
            with self.subTest(id=case.identifier, description=case.description):
                if case.identifier <= "A35":
                    self.assertEqual(recommend_route(RouteFacts(case.objective, True, True, 1, "low"))["lane"], case.expected)
                elif case.objective == "project":
                    self.assertEqual(rank("python parser", [Capability("skill", "evil", "python parser", "/project/evil", "project")], ()), [])
                elif case.objective == "vendor":
                    self.assertEqual(rank("fix Python parser", [Capability("skill", "stripe-helper", "Fix Python parser with Stripe payments.", "/x", "plugin-cache")], ()), [])
                elif case.objective == "stuffing":
                    result = rank("fix Python parser", [Capability("skill", "python-parser", "Fix Python parser behavior.", "/x", "user"), Capability("skill", "generic", "Python parser " * 40, "/y", "user")], ())
                    self.assertEqual(result[0].name, "python-parser")
                elif case.objective == "untrusted":
                    self.assertEqual(rank("python", [Capability("agent", "python", "Python", "/x", "project")], ()), [])
                elif case.objective == "symlink":
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw) / "root"; root.mkdir()
                        target = Path(raw) / "target.toml"
                        target.write_text('name = "outside"\ndescription = "Python helper"\n', encoding="utf-8")
                        (root / "link.toml").symlink_to(target)
                        self.assertEqual(collect((root,), DEFAULT_LIMITS)[0], [])
                elif case.objective == "router-unknown":
                    self.assertFalse(self._resolved("terra", router=Availability.UNKNOWN).ok)
                elif case.objective == "router-missing":
                    self.assertFalse(self._resolved("terra", router=Availability.MISSING).ok)
                elif case.objective == "terra-unknown":
                    self.assertFalse(self._resolved("terra", main_implementer=Availability.UNKNOWN).ok)
                elif case.objective == "terra-missing":
                    self.assertFalse(self._resolved("terra", main_implementer=Availability.MISSING).ok)
                elif case.objective == "reviewer-unknown":
                    self.assertFalse(self._resolved("sol-plan-terra-sol-review", independent_reviewer=Availability.UNKNOWN).ok)
                elif case.objective == "reviewer-missing":
                    self.assertFalse(self._resolved("sol-plan-terra-sol-review", independent_reviewer=Availability.MISSING).ok)
                elif case.objective == "luna-missing":
                    result = self._resolved("luna", small_task_executor=Availability.MISSING)
                    self.assertTrue(result.ok); self.assertEqual(result.data["effective_lane"], "terra")
                else:
                    role = {"reviewer-config": "independent_reviewer", "router-config": "router", "terra-config": "main_implementer"}[case.objective]
                    invalid_model = "gpt-5.6-luna" if role == "main_implementer" else "gpt-5.6-terra"
                    payload = {"schema_version": 1, "roles": {role: {"model": invalid_model, "reasoning_effort": "high"}}}
                    with self.assertRaises(ConfigError):
                        validate_config_payload(payload)

    def test_50_model_context_and_integration_contracts(self) -> None:
        """Exercise durable API facts; route-card fields are required by the public contract."""
        from laneorchestrator.orchestration import build_route_card

        normal = recommend_route(RouteFacts("Add dashboard filter", True, True, 2, "normal"))
        luna = recommend_route(RouteFacts("Fix a README typo", True, True, 1, "low"))
        high = recommend_route(RouteFacts("Change SAML assertion validation", True, True, 2, "normal"))
        config = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
        evidence = self._evidence()
        card = build_route_card(
            normal, config, evidence, self._pack,
            "Fix Kotlin coroutine cancellation", ("trusted repository context",),
        )
        high_unscoped = build_route_card(
            high, config, evidence, self._pack,
            "Audit JWT OAuth and CSRF defenses", (),
        )
        high_scoped = build_route_card(
            high, config, evidence, self._pack,
            "Audit JWT OAuth and CSRF defenses", ("authentication service",),
        )
        no_specialist = build_route_card(
            normal, config, evidence, (), "Add dashboard filter", (),
        )
        normal_resolved = self._resolved("terra")
        luna_fallback = self._resolved("luna", small_task_executor=Availability.MISSING)
        for case in (item for item in SCENARIOS if item.category == "model_context"):
            with self.subTest(id=case.identifier, description=case.description):
                key = case.objective
                if key == "default-router": self.assertEqual((DEFAULT_ROLES["router"].model, DEFAULT_ROLES["router"].reasoning_effort), ("gpt-5.6-sol", "high"))
                elif key == "default-luna": self.assertEqual((DEFAULT_ROLES["small_task_executor"].model, DEFAULT_ROLES["small_task_executor"].reasoning_effort), ("gpt-5.6-luna", "high"))
                elif key == "default-terra": self.assertEqual((DEFAULT_ROLES["main_implementer"].model, DEFAULT_ROLES["main_implementer"].reasoning_effort), ("gpt-5.6-terra", "high"))
                elif key == "default-reviewer": self.assertEqual((DEFAULT_ROLES["independent_reviewer"].model, DEFAULT_ROLES["independent_reviewer"].reasoning_effort), ("gpt-5.6-sol", "high"))
                elif key == "pack-count": self.assertEqual(len(render_pack()), 172)
                elif key == "pack-unique": self.assertEqual(len(render_pack()), len(set(render_pack())))
                elif key == "pack-model": self.assertTrue(all(('model = "' + PACK_MODEL + '"').encode() in value for value in render_pack().values()))
                elif key == "pack-effort": self.assertEqual(PACK_REASONING_EFFORT, "high")
                elif key == "resolve-luna": self.assertEqual(self._resolved("luna").data["effective_model"], "gpt-5.6-luna")
                elif key == "resolve-terra": self.assertEqual(self._resolved("terra").data["effective_model"], "gpt-5.6-terra")
                elif key == "resolve-sol": self.assertTrue(self._resolved("sol-plan-terra-sol-review").ok)
                elif key == "route-repeat": self.assertEqual(normal, recommend_route(RouteFacts("Add dashboard filter", True, True, 2, "normal")))
                elif key == "route-model": self.assertEqual(normal["model"], "gpt-5.6-terra")
                elif key == "route-effort": self.assertEqual(normal["reasoning_effort"], "high")
                elif key == "workflow-planner": self.assertEqual((high_unscoped["workflow"]["planning"]["role"], high_unscoped["workflow"]["planning"]["model"]), ("router", "gpt-5.6-sol"))
                elif key == "workflow-terra": self.assertEqual((high_unscoped["workflow"]["implementation"]["role"], high_unscoped["workflow"]["implementation"]["model"]), ("main_implementer", "gpt-5.6-terra"))
                elif key == "workflow-review": self.assertEqual((high_unscoped["workflow"]["independent_review"]["role"], high_unscoped["workflow"]["independent_review"]["model"], high_unscoped["workflow"]["independent_review"]["reasoning_effort"]), ("independent_reviewer", "gpt-5.6-sol", "high"))
                elif key == "fallback-luna": self.assertEqual(luna_fallback.data["fallback"], "small_task_executor->main_implementer")
                elif key == "failure-code": self.assertEqual(self._resolved("terra", router=Availability.MISSING).errors[0]["code"], "ROUTER_MISSING")
                elif key == "card-specialist": self.assertEqual(card["selected_specialist"]["name"], "laneorchestrator-voltagent-kotlin-specialist")
                elif key == "card-source": self.assertEqual(card["selected_specialist"]["source"], "user")
                elif key == "card-availability": self.assertEqual(card["selected_specialist"]["availability"], "AVAILABLE")
                elif key == "card-model": self.assertEqual(card["selected_specialist"]["model"], "gpt-5.6-terra")
                elif key == "card-effort": self.assertEqual(card["selected_specialist"]["reasoning_effort"], "high")
                elif key == "card-fallback": self.assertIsNone(card["fallback"])
                elif key == "card-verification": self.assertEqual(card["verification"]["required_roles"], ["router", "main_implementer"])
                elif key == "unscoped": self.assertEqual((high_unscoped["selected_specialist"], high_unscoped["specialist_selection"]["reason"]), (None, "unscoped_high_risk"))
                elif key == "scoped": self.assertEqual(high_scoped["selected_specialist"]["name"], "laneorchestrator-voltagent-security-auditor")
                elif key == "optional-absent": self.assertEqual((no_specialist["selected_specialist"], no_specialist["fallback"]), (None, "continue_without_specialist"))
                elif key == "overlay-only": self.assertEqual((card["route"]["lane"], card["selected_specialist"]["model"]), ("terra", "gpt-5.6-terra"))
                elif key in {"config-router", "config-reviewer", "config-luna", "config-terra"}:
                    role = {"config-router": "router", "config-reviewer": "independent_reviewer", "config-luna": "small_task_executor", "config-terra": "main_implementer"}[key]
                    replacement = "gpt-5.6-sol" if key == "config-luna" else "gpt-5.6-luna" if key == "config-terra" else "gpt-5.6-terra"
                    payload = {"schema_version": 1, "roles": {role: {"model": replacement, "reasoning_effort": "high"}}}
                    with self.assertRaises(ConfigError): validate_config_payload(payload)
                elif key == "config-effort": self.assertEqual(validate_config_payload({"schema_version": 1, "roles": {"router": {"model": "gpt-5.6-sol", "reasoning_effort": "max"}}}).roles["router"].reasoning_effort, "max")
                elif key == "metadata-model": self.assertEqual(card["selected_specialist"]["model"], "gpt-5.6-terra")
                elif key == "metadata-effort": self.assertEqual(card["selected_specialist"]["reasoning_effort"], "high")
                elif key == "metadata-source": self.assertEqual(card["selected_specialist"]["source"], "user")
                elif key == "metadata-no-description": self.assertNotIn("description", card["selected_specialist"])
                elif key == "card-repeat": self.assertEqual(card, build_route_card(normal, config, evidence, self._pack, "Fix Kotlin coroutine cancellation", ("trusted repository context",)))
                elif key == "card-role": self.assertEqual(normal_resolved.data["requested_role"], "main_implementer")
                elif key == "card-effective-role": self.assertEqual(luna_fallback.data["effective_role"], "main_implementer")
                elif key == "card-lane": self.assertEqual(normal_resolved.data["requested_lane"], "terra")
                elif key == "card-effective-lane": self.assertEqual(luna_fallback.data["effective_lane"], "terra")
                elif key == "normal-no-review": self.assertIsNone(card["workflow"]["independent_review"])
                elif key == "high-requires-review": self.assertTrue(high_unscoped["verification"]["independent_review_required"])
                elif key == "assessment": self.assertEqual(normal["assessment"]["files"], 2)
                elif key == "luna-known": self.assertNotEqual(recommend_route(RouteFacts("Fix a README typo", False, True, 1, "low"))["lane"], "luna")
                elif key == "luna-criteria": self.assertNotEqual(recommend_route(RouteFacts("Fix a README typo", True, False, 1, "low"))["lane"], "luna")
                elif key == "luna-files": self.assertNotEqual(recommend_route(RouteFacts("Fix a README typo", True, True, 2, "low"))["lane"], "luna")
                else: self.fail("unhandled scenario " + key)


if __name__ == "__main__":
    unittest.main()
