from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest import mock

from laneorchestrator.config import ConfigError, apply_config, ensure_private_directory, load_config, preview_config
from laneorchestrator.models import Availability, RoleEvidence
from laneorchestrator.plans import PlanError
import laneorchestrator.cli as cli_module
import laneorchestrator.config as config_module


ROOT = Path(__file__).resolve().parents[1]
ROUTE_SCRIPT = ROOT / "skills" / "laneorchestrator" / "scripts" / "route.py"
CATALOG_SCRIPT = ROOT / "skills" / "laneorchestrator" / "scripts" / "catalog.py"


class CliIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="lane orchestrator cli ")
        self.home = Path(self.temporary_directory.name).resolve()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(
        self,
        *arguments: str,
        home: Optional[Path] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["CODEX_HOME"] = os.fspath(self.home if home is None else home)
        environment["PATH"] = ""
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "laneorchestrator", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=environment,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> Dict[str, object]:
        return json.loads(result.stdout)

    def test_command_allowlist_is_exact_and_benchmark_is_still_a_usage_error(self) -> None:
        version = self.run_cli("version", "--json")
        benchmark = self.run_cli("benchmark", "--json")

        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertEqual(
            self.payload(version)["data"],
            {
                "manifest_version": "0.2.0",
                "package_version": "0.2.0",
                "schema_version": 1,
                "version": "0.2.0",
            },
        )
        self.assertEqual(benchmark.returncode, 2)
        self.assertEqual(self.payload(benchmark)["errors"][0]["code"], "INVALID_ARGUMENTS")
        self.assertNotIn("Traceback", benchmark.stderr + benchmark.stdout)

    def test_every_parser_help_surface_documents_json_mode(self) -> None:
        surfaces = (
            ("--help",),
            ("doctor", "--help"),
            ("status", "--help"),
            ("version", "--help"),
            ("configure", "--help"),
            ("configure", "preview", "--help"),
            ("configure", "apply", "--help"),
            ("route", "--help"),
            ("catalog", "--help"),
            ("profiles", "--help"),
            ("profiles", "install", "--help"),
            ("profiles", "install", "preview", "--help"),
            ("profiles", "install", "apply", "--help"),
        )
        for arguments in surfaces:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--json", result.stdout)

    def test_configure_preview_apply_and_replay_use_one_time_plan(self) -> None:
        preview = self.run_cli(
            "configure",
            "preview",
            "--set",
            "main_implementer.model=gpt-5.6-terra",
            "--set",
            "main_implementer.reasoning_effort=ultra",
            "--json",
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_data = self.payload(preview)["data"]
        token = preview_data["token"]
        self.assertIsNone(preview_data["before_sha256"])
        self.assertRegex(preview_data["after_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(Path(preview_data["destination"]), self.home / "laneorchestrator" / "config.json")

        applied = self.run_cli("configure", "apply", "--token", token, "--json")
        replay = self.run_cli("configure", "apply", "--token", token, "--json")

        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(self.payload(applied)["data"]["phase"], "apply")
        self.assertEqual(replay.returncode, 1)
        self.assertEqual(self.payload(replay)["errors"][0]["code"], "PLAN_CONSUMED")
        self.assertNotIn(token, replay.stdout + replay.stderr)
        config = json.loads((self.home / "laneorchestrator" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["roles"]["main_implementer"]["reasoning_effort"], "ultra")

    def test_unified_route_data_preserves_legacy_payload(self) -> None:
        arguments = (
            "--objective",
            "fix a README title typo",
            "--known-area",
            "--acceptance-criteria",
            "--files",
            "1",
            "--risk-assessment",
            "low",
        )
        legacy = subprocess.run(
            [sys.executable, os.fspath(ROUTE_SCRIPT), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        unified = self.run_cli("route", *arguments, "--json")

        self.assertEqual(unified.returncode, 1)
        payload = self.payload(unified)
        self.assertEqual(payload["command"], "route")
        self.assertEqual(payload["data"]["route"], json.loads(legacy.stdout))
        self.assertEqual(payload["errors"][0]["code"], "ROUTER_MISSING")

    def test_unified_catalog_data_preserves_separate_legacy_catalog(self) -> None:
        skills = self.home / "skills"
        agents = self.home / "agents fixture"
        skill = skills / "python-parser" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: python-parser\ndescription: Fix Python parser behavior.\n---\n",
            encoding="utf-8",
        )
        agents.mkdir()
        (agents / "parser-specialist.toml").write_text(
            'name = "parser-specialist"\ndescription = "Fix Python parser behavior."\nmodel = "gpt-5.6-terra"\n',
            encoding="utf-8",
        )
        arguments = (
            "--query",
            "fix Python parser",
            "--cwd",
            os.fspath(self.home),
            "--no-default-roots",
            "--skills-root",
            os.fspath(skills),
            "--agents-root",
            os.fspath(agents),
        )
        legacy = subprocess.run(
            [sys.executable, os.fspath(CATALOG_SCRIPT), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        unified = self.run_cli("catalog", *arguments, "--json")

        self.assertEqual(unified.returncode, 0, unified.stderr)
        self.assertEqual(self.payload(unified)["data"]["catalog"], json.loads(legacy.stdout))

    def test_default_status_is_read_only_and_truthfully_degraded(self) -> None:
        before = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        result = self.run_cli("--json", "status")
        after = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))

        self.assertEqual(result.returncode, 1)
        payload = self.payload(result)
        self.assertEqual(payload["data"]["config_source"], "defaults")
        self.assertEqual(set(payload["data"]["managed_profile_state"].values()), {"missing"})
        self.assertEqual(before, after)

    def test_configure_rejects_malformed_duplicate_secret_control_and_oversized_sets(self) -> None:
        cases = (
            (("main_implementer.model",), "CONFIG_SET_INVALID"),
            (
                (
                    "main_implementer.model=gpt-5.6-terra",
                    "main_implementer.model=gpt-5.6-sol",
                ),
                "CONFIG_SET_DUPLICATE",
            ),
            (("main_implementer.model=api-key-value",), "CONFIG_INVALID"),
            (("main_implementer.model=bad\nvalue",), "CONFIG_INVALID"),
            (("main_implementer.model=" + "a" * 257,), "CONFIG_INVALID"),
        )
        for settings, code in cases:
            with self.subTest(settings=settings):
                arguments = ["configure", "preview"]
                for setting in settings:
                    arguments.extend(("--set", setting))
                arguments.append("--json")
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(self.payload(result)["errors"][0]["code"], code)
                self.assertNotIn("Traceback", result.stdout + result.stderr)
                self.assertFalse((self.home / "laneorchestrator" / "config.json").exists())

    def test_expired_config_plan_is_rejected_without_echoing_token(self) -> None:
        preview = self.run_cli(
            "configure",
            "preview",
            "--set",
            "router.reasoning_effort=ultra",
            "--json",
        )
        token = self.payload(preview)["data"]["token"]
        plan_path = next(
            path
            for path in (self.home / "laneorchestrator" / "plans").glob("*.json")
            if path.is_file()
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["created_at"] = 0
        plan["expires_at"] = 600
        plan_path.write_text(
            json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        plan_path.chmod(0o600)

        expired = self.run_cli("configure", "apply", "--token", token, "--json")

        self.assertEqual(expired.returncode, 1)
        self.assertEqual(self.payload(expired)["errors"][0]["code"], "PLAN_EXPIRED")
        self.assertNotIn(token, expired.stdout + expired.stderr)
        self.assertFalse((self.home / "laneorchestrator" / "config.json").exists())

    def test_interrupted_config_apply_consumes_token_and_leaves_complete_old_state(self) -> None:
        state = ensure_private_directory(self.home / "state")
        token, _preview = preview_config(
            {"router.reasoning_effort": "ultra"}, state, now=100
        )
        with mock.patch.object(
            config_module, "_write_config_at_locked", side_effect=OSError("interrupted")
        ):
            with self.assertRaises(ConfigError):
                apply_config(token, state, now=101)

        self.assertFalse((state / "config.json").exists())
        with self.assertRaisesRegex(PlanError, "already used"):
            apply_config(token, state, now=102)

    def test_config_apply_rechecks_symlink_and_root_identity_without_outside_write(self) -> None:
        outside = self.home / "outside.json"
        outside.write_text("outside\n", encoding="utf-8")
        preview = self.run_cli(
            "configure", "preview", "--set", "router.reasoning_effort=ultra", "--json"
        )
        token = self.payload(preview)["data"]["token"]
        config_path = self.home / "laneorchestrator" / "config.json"
        config_path.symlink_to(outside)
        refused = self.run_cli("configure", "apply", "--token", token, "--json")
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(self.payload(refused)["errors"][0]["code"], "CONFIG_INVALID")
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

        other_home = self.home / "root identity"
        other_home.mkdir(mode=0o700)
        preview = self.run_cli(
            "configure",
            "preview",
            "--set",
            "router.reasoning_effort=ultra",
            "--json",
            home=other_home,
        )
        token = self.payload(preview)["data"]["token"]
        old_state = other_home / "old-state"
        state = other_home / "laneorchestrator"
        state.rename(old_state)
        state.mkdir(mode=0o700)
        shutil.move(os.fspath(old_state / "plans"), os.fspath(state / "plans"))
        refused = self.run_cli(
            "configure", "apply", "--token", token, "--json", home=other_home
        )
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(self.payload(refused)["errors"][0]["code"], "CONFIG_INVALID")
        self.assertFalse((state / "config.json").exists())

    def test_symlinked_and_relative_codex_homes_are_refused_without_outside_state(self) -> None:
        outside = self.home / "outside home"
        outside.mkdir(mode=0o700)
        linked = self.home / "linked home"
        linked.symlink_to(outside, target_is_directory=True)
        linked_result = self.run_cli(
            "configure",
            "preview",
            "--set",
            "router.reasoning_effort=ultra",
            "--json",
            home=linked,
        )
        relative_result = self.run_cli(
            "configure",
            "preview",
            "--set",
            "router.reasoning_effort=ultra",
            "--json",
            home=Path("relative-codex-home"),
        )
        self.assertEqual(linked_result.returncode, 1)
        self.assertEqual(relative_result.returncode, 1)
        self.assertEqual(
            self.payload(relative_result)["errors"][0]["code"], "UNSAFE_CODEX_HOME"
        )
        self.assertFalse((outside / "laneorchestrator").exists())

    def _profile_preview_apply(self, action: str) -> Dict[str, object]:
        preview = self.run_cli("profiles", action, "preview", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        token = self.payload(preview)["data"]["token"]
        applied = self.run_cli("profiles", action, "apply", "--token", token, "--json")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertNotIn(token, applied.stdout + applied.stderr)
        return self.payload(applied)

    def test_profile_install_update_uninstall_journey_preserves_config_and_unrelated_files(self) -> None:
        installed = self._profile_preview_apply("install")
        self.assertEqual(installed["data"]["change_count"], 4)

        configure = self.run_cli(
            "configure", "preview", "--set", "router.model=custom-router", "--json"
        )
        configure_token = self.payload(configure)["data"]["token"]
        self.assertEqual(
            self.run_cli(
                "configure", "apply", "--token", configure_token, "--json"
            ).returncode,
            0,
        )
        updated = self._profile_preview_apply("update")
        self.assertGreaterEqual(updated["data"]["change_count"], 1)
        router = self.home / "agents" / "laneorchestrator-router.toml"
        self.assertIn('model = "custom-router"', router.read_text(encoding="utf-8"))

        unrelated = self.home / "agents" / "third-party.toml"
        unrelated.write_text("third party\n", encoding="utf-8")
        config_before = (self.home / "laneorchestrator" / "config.json").read_bytes()
        removed = self._profile_preview_apply("uninstall")
        self.assertEqual(removed["data"]["change_count"], 4)
        self.assertTrue(unrelated.is_file())
        self.assertEqual(
            (self.home / "laneorchestrator" / "config.json").read_bytes(), config_before
        )

    def test_profile_preview_accepts_safe_owned_0755_agents_root(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(mode=0o755)
        agents.chmod(0o755)

        preview = self.run_cli("profiles", "install", "preview", "--json")

        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        self.assertEqual(self.payload(preview)["data"]["phase"], "preview")
        self.assertEqual(agents.stat().st_mode & 0o777, 0o755)

    def test_profile_plan_is_bound_to_action_and_replay_safe(self) -> None:
        invalid = self.run_cli(
            "profiles", "install", "apply", "--token", "bad", "--json"
        )
        preview = self.run_cli("profiles", "install", "preview", "--json")
        token = self.payload(preview)["data"]["token"]
        wrong_action = self.run_cli(
            "profiles", "update", "apply", "--token", token, "--json"
        )
        replay = self.run_cli(
            "profiles", "install", "apply", "--token", token, "--json"
        )

        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(self.payload(invalid)["errors"][0]["code"], "PLAN_INVALID")
        self.assertEqual(wrong_action.returncode, 1)
        self.assertEqual(self.payload(wrong_action)["errors"][0]["code"], "PLAN_INVALID")
        self.assertNotIn(token, wrong_action.stdout + wrong_action.stderr)
        self.assertEqual(replay.returncode, 0, replay.stderr)

    def test_route_fallbacks_distinguish_missing_from_unknown(self) -> None:
        config = load_config(self.home / "missing-state")

        def evidence(**states: Availability) -> Dict[str, RoleEvidence]:
            values = {
                "router": Availability.AVAILABLE,
                "small_task_executor": Availability.AVAILABLE,
                "main_implementer": Availability.AVAILABLE,
                "independent_reviewer": Availability.AVAILABLE,
            }
            values.update(states)
            return {
                role: RoleEvidence(role, config.roles[role].model, None, availability)
                for role, availability in values.items()
            }

        luna_decision = json.loads(
            subprocess.run(
                [
                    sys.executable,
                    os.fspath(ROUTE_SCRIPT),
                    "--objective",
                    "fix typo",
                    "--known-area",
                    "--acceptance-criteria",
                    "--files",
                    "1",
                    "--risk-assessment",
                    "low",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        high_decision = dict(luna_decision, lane="sol-plan-terra-sol-review")

        missing_luna = cli_module.resolve_route(
            luna_decision, config, evidence(small_task_executor=Availability.MISSING)
        )
        unknown_luna = cli_module.resolve_route(
            luna_decision, config, evidence(small_task_executor=Availability.UNKNOWN)
        )
        missing_terra = cli_module.resolve_route(
            luna_decision, config, evidence(main_implementer=Availability.MISSING)
        )
        missing_router = cli_module.resolve_route(
            luna_decision, config, evidence(router=Availability.MISSING)
        )
        missing_reviewer = cli_module.resolve_route(
            high_decision, config, evidence(independent_reviewer=Availability.MISSING)
        )

        self.assertEqual(missing_luna.data["effective_lane"], "terra")
        self.assertEqual(
            missing_luna.data["fallback"], "small_task_executor->main_implementer"
        )
        self.assertEqual(unknown_luna.data["effective_lane"], "luna")
        self.assertEqual(
            unknown_luna.data["role_evidence"]["small_task_executor"]["availability"],
            "UNKNOWN",
        )
        self.assertEqual(missing_terra.errors[0]["code"], "MAIN_IMPLEMENTER_MISSING")
        self.assertEqual(missing_router.errors[0]["code"], "ROUTER_MISSING")
        self.assertEqual(missing_reviewer.errors[0]["code"], "REVIEWER_MISSING")

    def test_human_and_json_modes_share_semantics_and_expected_errors_have_no_traceback(self) -> None:
        human = self.run_cli("version")
        machine = self.run_cli("--json", "version")
        invalid = self.run_cli("route", "--objective", " ", "--json")

        self.assertEqual(human.returncode, 0)
        self.assertEqual(machine.returncode, 0)
        for value in self.payload(machine)["data"].values():
            self.assertIn(str(value), human.stdout)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(self.payload(invalid)["errors"][0]["code"], "INVALID_ARGUMENTS")
        self.assertNotIn("Traceback", invalid.stdout + invalid.stderr)

    def test_unexpected_errors_are_generic_unless_debug_and_tokens_are_always_redacted(self) -> None:
        token = "T" * 43

        def invoke(debug: bool) -> tuple[int, str, str]:
            stdout = io.StringIO()
            stderr = io.StringIO()
            environment = {"LANEORCHESTRATOR_DEBUG": "1"} if debug else {}
            with mock.patch.object(
                cli_module, "dispatch", side_effect=RuntimeError("boom " + token)
            ), mock.patch.dict(os.environ, environment, clear=False), mock.patch(
                "sys.stdout", stdout
            ), mock.patch("sys.stderr", stderr):
                if not debug:
                    os.environ.pop("LANEORCHESTRATOR_DEBUG", None)
                code = cli_module.main(
                    ("configure", "apply", "--token", token, "--json")
                )
            return code, stdout.getvalue(), stderr.getvalue()

        ordinary = invoke(False)
        debug = invoke(True)
        self.assertEqual(ordinary[0], 3)
        self.assertNotIn("Traceback", ordinary[1] + ordinary[2])
        self.assertEqual(json.loads(ordinary[1])["errors"][0]["code"], "INTERNAL_ERROR")
        self.assertEqual(debug[0], 3)
        self.assertIn("Traceback", debug[2])
        self.assertNotIn(token, "".join(ordinary[1:] + debug[1:]))


if __name__ == "__main__":
    unittest.main()
