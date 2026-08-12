from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from laneorchestrator.diagnostics import Level, render_human, render_json
from laneorchestrator.doctor import run_status
from tests.test_doctor import PROFILE_NAMES, _profile_fixture, _tree_snapshot


class StatusContractTests(unittest.TestCase):
    def test_status_reports_the_required_read_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            result = run_status(root / "state", root / "agents")
        self.assertEqual(result.command, "status")
        self.assertEqual(
            list(result.data),
            [
                "effective_roles",
                "config_source",
                "managed_profile_state",
                "fallback_policy",
                "latest_receipt",
            ],
        )

    def test_defaults_and_missing_profiles_are_truthful_json_primitives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            result = run_status(root / "state", root / "agents")
            payload = json.loads(render_json(result))
        self.assertEqual(payload["data"]["config_source"], "defaults")
        self.assertEqual(payload["data"]["latest_receipt"], None)
        self.assertEqual(
            set(payload["data"]["managed_profile_state"].values()),
            {"missing"},
        )
        self.assertEqual(
            payload["data"]["fallback_policy"]["small_task_executor"],
            "main_implementer",
        )
        self.assertFalse(result.ok)
        installed = next(item for item in result.diagnostics if item.code == "INSTALLED_PROFILES")
        self.assertEqual(installed.level, Level.FAIL)
        self.assertIn("blocked", installed.message.casefold())
        self.assertEqual(
            payload["data"]["fallback_policy"],
            {
                "router": "pause_all_routes",
                "small_task_executor": "main_implementer",
                "main_implementer": "pause",
                "high_risk_reviewer": "pause",
                "optional_specialist": "continue_without_specialist",
            },
        )

    def test_managed_status_reports_only_supported_receipt_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _repo, state, agents, _env = _profile_fixture(Path(temporary))
            result = run_status(state, agents)
            payload = json.loads(render_json(result))["data"]
        self.assertEqual(set(payload["managed_profile_state"].values()), {"managed"})
        self.assertEqual(
            payload["latest_receipt"],
            {
                "operation": "install",
                "profile_count": 4,
                "schema_version": 1,
                "template_version": "0.2.3",
            },
        )
        self.assertNotIn("timestamp", json.dumps(payload["latest_receipt"]).casefold())

    def test_malformed_state_is_diagnostic_not_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _repo, state, agents, _env = _profile_fixture(Path(temporary))
            (state / "config.json").write_text("{bad", encoding="utf-8")
            result = run_status(state, agents)
        self.assertFalse(result.ok)
        self.assertEqual(result.data["config_source"], "invalid")
        self.assertTrue(any(item.code == "CONFIG_SCHEMA" and item.level is Level.FAIL for item in result.diagnostics))

    def test_human_and_json_include_identical_diagnostic_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_status(root / "state", root / "agents")
        human = render_human(result)
        payload = json.loads(render_json(result))
        for diagnostic in payload["diagnostics"]:
            self.assertIn(diagnostic["code"], human)
            self.assertIn(diagnostic["level"], human)
            self.assertIn(json.dumps(diagnostic["evidence"], sort_keys=True), human)

    def test_status_is_read_only_when_repeated_and_when_roots_are_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "missing-state"
            agents = root / "missing-agents"
            before = _tree_snapshot(root)
            first = run_status(state, agents)
            second = run_status(state, agents)
            self.assertEqual(before, _tree_snapshot(root))
            self.assertEqual(first.to_dict(), second.to_dict())

            target = root / "target"
            target.mkdir()
            state.symlink_to(target, target_is_directory=True)
            before = _tree_snapshot(root)
            linked = run_status(state, agents)
            self.assertFalse(linked.ok)
            self.assertEqual(before, _tree_snapshot(root))

    def test_portable_no_dir_fd_adapter_preserves_read_only_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _repo, state, agents, _env = _profile_fixture(Path(temporary))
            before = _tree_snapshot(state.parent)
            with mock.patch("laneorchestrator.doctor._dir_fd_read_supported", return_value=False):
                result = run_status(state, agents)
            after = _tree_snapshot(state.parent)
        self.assertTrue(result.ok)
        self.assertEqual(set(result.data["managed_profile_state"].values()), {"managed"})
        self.assertEqual(before, after)

    def test_status_distinguishes_unmanaged_drift_bad_mode_and_invalid_receipt(self) -> None:
        cases = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, state, agents, _env = _profile_fixture(root)
            (state / "receipts.json").unlink()
            cases.append(set(run_status(state, agents).data["managed_profile_state"].values()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, state, agents, _env = _profile_fixture(root)
            (agents / PROFILE_NAMES[0]).write_bytes(b"drift\n")
            cases.append(set(run_status(state, agents).data["managed_profile_state"].values()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, state, agents, _env = _profile_fixture(root)
            (agents / PROFILE_NAMES[0]).chmod(0o644)
            cases.append(set(run_status(state, agents).data["managed_profile_state"].values()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, state, agents, _env = _profile_fixture(root)
            (state / "receipts.json").write_text("{bad", encoding="utf-8")
            cases.append(set(run_status(state, agents).data["managed_profile_state"].values()))
        self.assertIn("unmanaged", cases[0])
        self.assertIn("drift", cases[1])
        self.assertIn("bad_mode", cases[2])
        self.assertIn("invalid_receipt", cases[3])


if __name__ == "__main__":
    unittest.main()
