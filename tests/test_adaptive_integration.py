"""Adaptive orchestration, real rendered profiles, and migration regressions."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from laneorchestrator.adaptive import validate_selection, spawn_settings
from laneorchestrator.config import load_config
from laneorchestrator.models import Availability, RoleEvidence
from laneorchestrator.orchestration import build_adaptive_card
from laneorchestrator.profiles import render_profiles
from laneorchestrator.routing import RouteFacts
from laneorchestrator.voltagent import render_pack, legacy_pack, preview_install, apply_install, pack_status, PackError


class AdaptiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.agents = self.root / "agents"
        self.state = self.root / "state"
        self.agents.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.config = load_config(self.state)
        self.evidence = {role: RoleEvidence(role, value.model, None, Availability.AVAILABLE)
                         for role, value in self.config.roles.items()}

    def card(self, text, risk="low", known=True):
        return build_adaptive_card(RouteFacts(text, known, True, 1, risk), self.config, self.evidence, [], [])

    def test_paraphrases_and_unicode_do_not_create_expensive_workflows(self):
        for text in ("Fix a README typo", "Please fix a README typo", "Fix a typo in README.md", "Corrige la errata del README", "修复 README 中的错字"):
            card = self.card(text)
            self.assertEqual(card["task_kind"], "small", text)
            self.assertFalse(card["verification"]["independent_review_required"])
            self.assertEqual(card["selection_status"], "awaiting_astra_decision")

    def test_unknown_scope_is_investigation_not_writable_pipeline(self):
        card = self.card("Fix authentication", "unknown", False)
        self.assertEqual(card["task_kind"], "investigation")
        self.assertEqual(card["verification"]["required_roles"], ["router"])
        self.assertEqual(card["execution"]["status"], "not_dispatched")

    def test_consequential_work_still_requires_independent_review(self):
        card = self.card("Change OAuth token storage", "high")
        self.assertTrue(card["verification"]["independent_review_required"])
        self.assertIn("independent_reviewer", card["verification"]["required_roles"])

    def test_all_176_profiles_are_model_neutral_for_every_supported_combo(self):
        profiles = {**render_profiles(self.config), **render_pack()}
        self.assertEqual(len(profiles), 176)
        host = {model: ["low", "medium", "high", "xhigh", "max", "ultra"]
                for model in ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")}
        for name, content in profiles.items():
            self.assertNotRegex(content.decode(), r'(?m)^model(?:_reasoning_effort)?\s*=')
            for model, efforts in host.items():
                for effort in efforts:
                    selected = validate_selection({"model": model, "reasoning_effort": effort, "reason": "Explicit task preference"}, host, task_kind="demanding", user_override=True)
                    self.assertEqual(spawn_settings(selected)["model"], model, name)
                    self.assertEqual(spawn_settings(selected)["reasoning_effort"], effort, name)

    def apply(self, action):
        token, preview = preview_install(self.agents, self.state, now=100, action=action)
        result = apply_install(token, self.agents, self.state, now=101, action=action, approval="approve:" + preview.data["approval_digest"])
        return preview, result

    def test_exact_legacy_specialists_upgrade_and_uninstall(self):
        for name, content in legacy_pack().items():
            (self.agents / name).write_bytes(content)
        preview, result = self.apply("update")
        self.assertEqual(result.data["change_count"], 172)
        self.assertEqual(len(preview.data["changes"]), 172)
        self.assertEqual(pack_status(self.agents).data["installed"], 172)
        self.apply("uninstall")
        self.assertEqual(pack_status(self.agents).data["missing"], 172)

    def test_recovery_accepts_only_known_partial_states_and_preserves_foreign_files(self):
        old, current = legacy_pack(), render_pack()
        names = list(current)
        for i, name in enumerate(names[:100]):
            (self.agents / name).write_bytes(current[name] if i % 2 else old[name])
        foreign = self.agents / "user-agent.toml"
        foreign.write_text("User owned")
        self.apply("update")
        self.assertEqual(pack_status(self.agents).data["installed"], 172)
        (self.agents / names[0]).write_bytes(current[names[0]] + b"\n# user edit")
        for action in ("update", "uninstall"):
            with self.assertRaises(PackError):
                self.apply(action)
        self.assertEqual(foreign.read_text(), "User owned")

    def test_update_publication_failure_restores_exact_legacy_bytes(self):
        import laneorchestrator.voltagent as pack
        old = legacy_pack()
        for name, content in old.items():
            (self.agents / name).write_bytes(content)
        token, preview = preview_install(self.agents, self.state, now=100, action="update")
        original = pack.os.replace
        count = [0]
        def fail_once(*args, **kwargs):
            count[0] += 1
            if count[0] == 3:
                raise OSError("fixture publication failure")
            return original(*args, **kwargs)
        with mock.patch.object(pack.os, "replace", side_effect=fail_once):
            with self.assertRaises(PackError):
                apply_install(token, self.agents, self.state, now=101, action="update", approval="approve:" + preview.data["approval_digest"])
        self.assertEqual({name: (self.agents / name).read_bytes() for name in old}, old)


if __name__ == "__main__":
    unittest.main()
