from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from laneorchestrator.config import DEFAULT_ROLES, load_config, serialize_config
from laneorchestrator.diagnostics import render_json
from laneorchestrator.models import EffectiveConfig, RoleConfig
from laneorchestrator.plans import Operation, approval_digest, create_plan, load_plan
import laneorchestrator.profiles as profiles_module
from laneorchestrator.profiles import (
    PROFILE_NAMES,
    ProfileConflict,
    apply_profiles as _apply_profiles,
    inspect_profiles,
    preview_profiles,
    render_profile,
    render_profiles,
)


def apply_profiles(action, token, agents_root, state_root, now=None):
    plan = load_plan(token, "profiles.{0}".format(action), Path(state_root) / "plans", now=now)
    return _apply_profiles(
        action, token, agents_root, state_root,
        approval="approve:" + approval_digest(plan), now=now,
    )


FIXTURES = Path(__file__).parent / "fixtures" / "profiles" / "v0.1.0"
V010_HASHES = {
    "laneorchestrator-luna-executor.toml": "1de0a4bf0ed0b3f32b8597991b8cc4ea5b3581d0736b4e7bb2dae47a8e9a5567",
    "laneorchestrator-router.toml": "c40f592272fb5ffe550c120fa48d1edb822a28b6b13085f9e30c8260c0d713a8",
    "laneorchestrator-sol-reviewer.toml": "078a82c418f1688b87b341463dcc59cf89c720e9434d4f3b897b991aa6f1b408",
    "laneorchestrator-terra-executor.toml": "5feb09a607e4b92b0cb251173e6ca9e6970f1fd3f256e2dcf58f90e6f972c88f",
}


class ProfileRenderingTests(unittest.TestCase):
    def test_profile_names_are_exactly_namespaced(self) -> None:
        self.assertEqual(
            PROFILE_NAMES,
            (
                "laneorchestrator-router.toml",
                "laneorchestrator-luna-executor.toml",
                "laneorchestrator-terra-executor.toml",
                "laneorchestrator-sol-reviewer.toml",
            ),
        )

    def test_v010_fixtures_match_commit_82a2577_hashes(self) -> None:
        self.assertEqual({path.name for path in FIXTURES.glob("*.toml")}, set(V010_HASHES))
        for name, expected in V010_HASHES.items():
            self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), expected)

    def test_render_is_deterministic_marked_and_maps_logical_roles(self) -> None:
        config = EffectiveConfig(
            1,
            {
                **DEFAULT_ROLES,
                "router": RoleConfig("example-router", "max"),
                "main_implementer": RoleConfig("example-main", "medium"),
            },
            "file",
        )
        first = render_profiles(config)
        second = render_profiles(config)
        self.assertEqual(first, second)
        self.assertEqual(tuple(first), PROFILE_NAMES)
        self.assertTrue(all(value.startswith(b"# managed-by: laneorchestrator 0.2.0\n") for value in first.values()))
        self.assertIn('model = "example-router"', render_profile("laneorchestrator-router.toml", config))
        self.assertIn('model_reasoning_effort = "medium"', render_profile("laneorchestrator-terra-executor.toml", config))

    def test_default_render_matches_checked_in_templates_and_roles_are_isolated(self) -> None:
        root = Path(__file__).resolve().parents[1]
        defaults = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
        rendered = render_profiles(defaults)
        for name in PROFILE_NAMES:
            self.assertEqual(rendered[name], (root / "agents" / name).read_bytes())
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("different-router", "low")
        changed = render_profiles(EffectiveConfig(1, roles, "file"))
        self.assertNotEqual(changed[PROFILE_NAMES[0]], rendered[PROFILE_NAMES[0]])
        for name in PROFILE_NAMES[1:]:
            self.assertEqual(changed[name], rendered[name])

    def test_luna_profile_is_read_only_at_the_host_boundary(self) -> None:
        rendered = render_profiles(EffectiveConfig(1, DEFAULT_ROLES, "defaults"))
        self.assertIn(b'sandbox_mode = "read-only"', rendered["laneorchestrator-luna-executor.toml"])

    def test_unknown_profile_and_incomplete_config_are_rejected(self) -> None:
        config = load_config(Path("/definitely/missing/laneorchestrator-state"))
        with self.assertRaises(ValueError):
            render_profile("foreign.toml", config)
        incomplete = EffectiveConfig(1, {"router": DEFAULT_ROLES["router"]}, "file")
        with self.assertRaises(ValueError):
            render_profiles(incomplete)


@unittest.skipUnless(os.name == "posix", "managed profile mutation is POSIX-only")
class ProfileLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.agents = self.root / "agents"
        self.state = self.root / "state"
        self.agents.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.config = load_config(self.state)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _preview_apply(self, action: str, config: Optional[EffectiveConfig] = None, now: int = 100):
        token, preview = preview_profiles(action, config or self.config, self.agents, self.state, now=now)
        result = apply_profiles(action, token, self.agents, self.state, now=now + 1)
        self.assertTrue(preview.ok)
        self.assertTrue(result.ok)
        return preview, result

    def _receipt(self) -> dict:
        return json.loads((self.state / "receipts.json").read_text(encoding="utf-8"))

    def test_clean_install_is_private_receipted_and_idempotent(self) -> None:
        config_file = self.state / "config.json"
        config_file.write_text('{"keep":"unchanged"}\n', encoding="utf-8")
        unrelated = self.agents / "third-party.toml"
        unrelated.write_text('name = "third-party"\n', encoding="utf-8")

        preview, result = self._preview_apply("install")
        self.assertEqual(preview.data["change_count"], 4)
        self.assertEqual(result.data["change_count"], 4)
        for name, expected in render_profiles(self.config).items():
            destination = self.agents / name
            self.assertEqual(destination.read_bytes(), expected)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        receipt_bytes = (self.state / "receipts.json").read_bytes()
        self.assertEqual(stat.S_IMODE((self.state / "receipts.json").stat().st_mode), 0o600)
        self.assertNotIn(b"developer_instructions", receipt_bytes)
        self.assertNotIn(b"credential", receipt_bytes.lower())
        receipt = self._receipt()
        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual({item["name"] for item in receipt["profiles"]}, set(PROFILE_NAMES))
        self.assertEqual(set(receipt), {"schema_version", "profiles"})
        expected_entry_keys = {
            "name", "destination", "template_version", "content_sha256",
            "config_sha256", "prior_backup_sha256", "operation",
        }
        self.assertTrue(all(set(item) == expected_entry_keys for item in receipt["profiles"]))
        self.assertEqual(config_file.read_text(), '{"keep":"unchanged"}\n')
        self.assertEqual(unrelated.read_text(), 'name = "third-party"\n')

        first_receipt = receipt_bytes
        token, second_preview = preview_profiles("install", self.config, self.agents, self.state, now=200)
        second = apply_profiles("install", token, self.agents, self.state, now=201)
        self.assertEqual(second_preview.data["change_count"], 0)
        self.assertEqual(second.data["change_count"], 0)
        self.assertEqual((self.state / "receipts.json").read_bytes(), first_receipt)
        self.assertFalse((self.state / "backups").exists())
        self.assertEqual(json.loads(render_json(second_preview))["data"]["phase"], "preview")
        self.assertEqual(second_preview.data["token"], token)
        self.assertEqual(json.loads(render_json(second))["data"]["phase"], "apply")

    def test_install_refuses_an_unmanaged_collision_without_partial_changes(self) -> None:
        collision = self.agents / PROFILE_NAMES[1]
        collision.write_text("foreign\n", encoding="utf-8")
        with self.assertRaisesRegex(ProfileConflict, "unmanaged"):
            preview_profiles("install", self.config, self.agents, self.state, now=100)
        self.assertEqual(collision.read_text(), "foreign\n")
        self.assertFalse((self.agents / PROFILE_NAMES[0]).exists())
        self.assertFalse((self.state / "receipts.json").exists())

    def test_exact_v010_profiles_can_be_adopted_but_near_match_is_refused(self) -> None:
        for name in PROFILE_NAMES:
            (self.agents / name).write_bytes((FIXTURES / name).read_bytes())
        self._preview_apply("adopt")
        for name, expected in render_profiles(self.config).items():
            self.assertEqual((self.agents / name).read_bytes(), expected)
        self.assertTrue(all(item["operation"] == "adopt" for item in self._receipt()["profiles"]))

        other_agents = self.root / "other-agents"
        other_state = self.root / "other-state"
        other_agents.mkdir(mode=0o700)
        other_state.mkdir(mode=0o700)
        for name in PROFILE_NAMES:
            (other_agents / name).write_bytes((FIXTURES / name).read_bytes())
        (other_agents / PROFILE_NAMES[0]).write_text(
            (other_agents / PROFILE_NAMES[0]).read_text() + "# near match\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProfileConflict, "exact v0.1.0"):
            preview_profiles("adopt", self.config, other_agents, other_state, now=100)

    def test_update_creates_private_exact_backups_and_new_receipt(self) -> None:
        self._preview_apply("install")
        before = {name: (self.agents / name).read_bytes() for name in PROFILE_NAMES}
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("configured-router", "ultra")
        changed = EffectiveConfig(1, roles, "file")
        preview, _result = self._preview_apply("update", changed, now=200)
        self.assertGreaterEqual(preview.data["change_count"], 1)
        receipt = self._receipt()
        router = next(item for item in receipt["profiles"] if item["name"] == PROFILE_NAMES[0])
        self.assertEqual(router["operation"], "update")
        self.assertEqual(router["prior_backup_sha256"], hashlib.sha256(before[PROFILE_NAMES[0]]).hexdigest())
        backup = self.state / "backups" / (PROFILE_NAMES[0] + "." + router["prior_backup_sha256"] + ".bak")
        self.assertEqual(backup.read_bytes(), before[PROFILE_NAMES[0]])
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertIn('model = "configured-router"', (self.agents / PROFILE_NAMES[0]).read_text())

    def test_update_preview_does_not_create_backup_directory(self) -> None:
        self._preview_apply("install")
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("preview-only-router", "high")
        changed = EffectiveConfig(1, roles, "file")
        token, preview = preview_profiles(
            "update", changed, self.agents, self.state, now=200
        )
        self.assertGreater(preview.data["change_count"], 0)
        self.assertFalse((self.state / "backups").exists())
        with self.assertRaisesRegex(Exception, "expired"):
            apply_profiles("update", token, self.agents, self.state, now=801)
        self.assertFalse((self.state / "backups").exists())

    def test_changed_managed_file_is_never_updated_or_uninstalled(self) -> None:
        self._preview_apply("install")
        destination = self.agents / "laneorchestrator-router.toml"
        destination.write_text(destination.read_text() + "# user change\n")
        with self.assertRaisesRegex(ProfileConflict, "receipt"):
            preview_profiles("update", self.config, self.agents, self.state, now=102)
        with self.assertRaisesRegex(ProfileConflict, "receipt"):
            preview_profiles("uninstall", self.config, self.agents, self.state, now=102)

    def test_receipt_drift_is_refused(self) -> None:
        self._preview_apply("install")
        receipt = self._receipt()
        receipt["profiles"][0]["content_sha256"] = "0" * 64
        (self.state / "receipts.json").write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ProfileConflict, "receipt"):
            preview_profiles("update", self.config, self.agents, self.state, now=200)

    def test_receipt_schema_is_strict_and_rejects_untrusted_metadata(self) -> None:
        self._preview_apply("install")
        receipt_path = self.state / "receipts.json"
        valid = self._receipt()
        variants = []
        missing = json.loads(json.dumps(valid))
        del missing["profiles"][0]["config_sha256"]
        variants.append(missing)
        extra = json.loads(json.dumps(valid))
        extra["profiles"][0]["content"] = "secret profile body"
        variants.append(extra)
        credential = json.loads(json.dumps(valid))
        credential["profiles"][0]["api_token"] = "do-not-store"
        variants.append(credential)
        duplicate = json.loads(json.dumps(valid))
        duplicate["profiles"].append(dict(duplicate["profiles"][0]))
        variants.append(duplicate)
        foreign = json.loads(json.dumps(valid))
        foreign["profiles"][0]["name"] = "foreign.toml"
        variants.append(foreign)
        bad_hash = json.loads(json.dumps(valid))
        bad_hash["profiles"][0]["content_sha256"] = "not-a-hash"
        variants.append(bad_hash)
        wrong_destination = json.loads(json.dumps(valid))
        wrong_destination["profiles"][0]["destination"] = "/tmp/foreign.toml"
        variants.append(wrong_destination)
        boolean_schema = json.loads(json.dumps(valid))
        boolean_schema["schema_version"] = True
        variants.append(boolean_schema)
        for field, bad_value in (
            ("name", {}),
            ("destination", 7),
            ("template_version", []),
            ("content_sha256", []),
            ("config_sha256", {}),
            ("prior_backup_sha256", True),
            ("operation", []),
        ):
            malformed = json.loads(json.dumps(valid))
            malformed["profiles"][0][field] = bad_value
            variants.append(malformed)
        for variant in variants:
            with self.subTest(variant=variant):
                receipt_path.write_text(json.dumps(variant), encoding="utf-8")
                with self.assertRaisesRegex(ProfileConflict, "receipt"):
                    preview_profiles("update", self.config, self.agents, self.state, now=200)
        duplicate_json = receipt_path.read_text(encoding="utf-8").replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1
        )
        receipt_path.write_text(duplicate_json, encoding="utf-8")
        with self.assertRaisesRegex(ProfileConflict, "duplicate"):
            preview_profiles("update", self.config, self.agents, self.state, now=200)

    def test_deeply_nested_receipt_is_a_domain_failure_not_recursion_error(self) -> None:
        self._preview_apply("install")
        receipt_path = self.state / "receipts.json"
        receipt_path.write_bytes((b"[" * 1200) + b"0" + (b"]" * 1200))
        receipt_path.chmod(0o600)
        with self.assertRaisesRegex(ProfileConflict, "receipt.*nesting"):
            preview_profiles("update", self.config, self.agents, self.state, now=200)

    def test_noop_plans_still_bind_receipt_bytes(self) -> None:
        self._preview_apply("install")
        receipt = self.state / "receipts.json"
        for action in ("install", "update"):
            with self.subTest(action=action):
                token, preview = preview_profiles(action, self.config, self.agents, self.state, now=200)
                self.assertEqual(preview.data["change_count"], 0)
                original = receipt.read_bytes()
                receipt.write_bytes(original + b" ")
                with self.assertRaisesRegex(ProfileConflict, "changed after preview"):
                    apply_profiles(action, token, self.agents, self.state, now=201)
                receipt.write_bytes(original)

                token, _ = preview_profiles(action, self.config, self.agents, self.state, now=300)
                profile = self.agents / PROFILE_NAMES[0]
                original_profile = profile.read_bytes()
                profile.write_bytes(original_profile + b"# changed\n")
                with self.assertRaisesRegex(ProfileConflict, "changed after preview"):
                    apply_profiles(action, token, self.agents, self.state, now=301)
                profile.write_bytes(original_profile)
                profile.chmod(0o600)

    def test_managed_profile_and_receipt_permission_drift_is_refused(self) -> None:
        self._preview_apply("install")
        profile = self.agents / PROFILE_NAMES[0]
        profile.chmod(0o644)
        with self.assertRaisesRegex(ProfileConflict, "permissions"):
            preview_profiles("update", self.config, self.agents, self.state, now=200)
        profile.chmod(0o600)
        receipt = self.state / "receipts.json"
        receipt.chmod(0o644)
        with self.assertRaisesRegex(ProfileConflict, "unsafe"):
            preview_profiles("update", self.config, self.agents, self.state, now=200)

    def test_inspect_reports_configuration_and_mode_drift(self) -> None:
        self._preview_apply("install")
        receipt_path = self.state / "receipts.json"
        original_receipt = receipt_path.read_bytes()
        receipt = self._receipt()
        for entry in receipt["profiles"]:
            entry["config_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(
            set(inspect_profiles(self.config, self.agents, self.state).values()),
            {"conflict"},
        )
        receipt_path.write_bytes(original_receipt)
        changed = self.agents / PROFILE_NAMES[0]
        changed.chmod(0o644)
        statuses = inspect_profiles(self.config, self.agents, self.state)
        self.assertEqual(statuses[PROFILE_NAMES[0]], "conflict")
        self.assertTrue(
            all(statuses[name] == "unchanged" for name in PROFILE_NAMES[1:])
        )

    def test_safe_owned_0755_agents_root_supports_full_lifecycle(self) -> None:
        self.agents.chmod(0o755)
        self._preview_apply("install")
        lock = self.agents / ".laneorchestrator-state.lock"
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("safe-0755-router", "high")
        changed = EffectiveConfig(1, roles, "file")
        self._preview_apply("update", changed, now=200)
        self._preview_apply("uninstall", changed, now=300)

    def test_group_or_other_writable_agents_root_is_refused(self) -> None:
        for mode in (0o770, 0o775, 0o777):
            with self.subTest(mode=oct(mode)):
                self.agents.chmod(mode)
                with self.assertRaisesRegex(ProfileConflict, "agents root|writable"):
                    preview_profiles(
                        "install", self.config, self.agents, self.state, now=100
                    )
        self.agents.chmod(0o700)

    def test_reusing_an_exact_content_addressed_backup_is_safe(self) -> None:
        self._preview_apply("install")
        roles_a = dict(DEFAULT_ROLES)
        roles_a["router"] = RoleConfig("router-a", "high")
        config_a = EffectiveConfig(1, roles_a, "file")
        self._preview_apply("update", config_a, now=200)
        self._preview_apply("update", self.config, now=300)
        self._preview_apply("update", config_a, now=400)
        self.assertIn('model = "router-a"', (self.agents / PROFILE_NAMES[0]).read_text())

    def test_config_and_receipt_are_rechecked_at_apply(self) -> None:
        (self.state / "config.json").write_bytes(serialize_config(self.config))
        token, _ = preview_profiles("install", self.config, self.agents, self.state, now=100)
        (self.state / "config.json").write_bytes(serialize_config(self.config) + b" ")
        with self.assertRaisesRegex(ProfileConflict, "changed after preview"):
            apply_profiles("install", token, self.agents, self.state, now=101)
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))
        self.assertFalse((self.state / "receipts.json").exists())

        (self.state / "config.json").write_bytes(serialize_config(self.config))
        self._preview_apply("install", now=200)
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("configured-router", "high")
        changed = EffectiveConfig(1, roles, "file")
        token, _ = preview_profiles("update", changed, self.agents, self.state, now=300)
        receipt_path = self.state / "receipts.json"
        original_receipt = receipt_path.read_bytes()
        receipt_path.write_bytes(original_receipt + b" ")
        before = {name: (self.agents / name).read_bytes() for name in PROFILE_NAMES}
        with self.assertRaisesRegex(ProfileConflict, "changed after preview"):
            apply_profiles("update", token, self.agents, self.state, now=301)
        self.assertEqual({name: (self.agents / name).read_bytes() for name in PROFILE_NAMES}, before)

    def test_uninstall_removes_only_managed_profiles_and_preserves_configuration(self) -> None:
        self._preview_apply("install")
        config_file = self.state / "config.json"
        config_file.write_text("configuration stays\n", encoding="utf-8")
        unrelated = self.agents / "unrelated.toml"
        unrelated.write_text("third party\n", encoding="utf-8")
        self._preview_apply("uninstall", now=200)
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))
        self.assertEqual(unrelated.read_text(), "third party\n")
        self.assertEqual(config_file.read_text(), "configuration stays\n")
        self.assertTrue(all(item["operation"] == "uninstall" for item in self._receipt()["profiles"]))

    def test_apply_refuses_changed_preview_state_and_action_mismatch(self) -> None:
        token, _ = preview_profiles("install", self.config, self.agents, self.state, now=100)
        (self.agents / PROFILE_NAMES[0]).write_text("appeared later\n", encoding="utf-8")
        with self.assertRaisesRegex(ProfileConflict, "preview"):
            apply_profiles("install", token, self.agents, self.state, now=101)

        other_state = self.root / "fresh-state"
        other_agents = self.root / "fresh-agents"
        other_state.mkdir(mode=0o700)
        other_agents.mkdir(mode=0o700)
        token, _ = preview_profiles("install", self.config, other_agents, other_state, now=100)
        with self.assertRaisesRegex(Exception, "kind|requested"):
            apply_profiles("update", token, other_agents, other_state, now=101)

    def test_apply_refuses_different_roots_and_foreign_plan_paths(self) -> None:
        token, _ = preview_profiles("install", self.config, self.agents, self.state, now=100)
        other_agents = self.root / "different-agents"
        other_agents.mkdir(mode=0o700)
        with self.assertRaisesRegex(ProfileConflict, "unexpected|binding"):
            apply_profiles("install", token, other_agents, self.state, now=101)

        plans_root = self.state / "plans"
        foreign = self.root / "foreign.txt"
        malicious = create_plan(
            "profiles.install",
            (Operation(os.fspath(foreign), None, None, None),),
            plans_root,
            now=200,
        )
        with self.assertRaisesRegex(ProfileConflict, "unexpected|binding"):
            apply_profiles("install", malicious, self.agents, self.state, now=201)
        self.assertFalse(foreign.exists())

        traversal = create_plan(
            "profiles.install",
            (Operation(os.fspath(self.agents / ".." / "foreign.txt"), None, None, None),),
            plans_root,
            now=300,
        )
        with self.assertRaisesRegex(ProfileConflict, "unexpected|binding"):
            apply_profiles("install", traversal, self.agents, self.state, now=301)
        self.assertFalse(foreign.exists())

    def test_injected_install_failure_rolls_back_every_visible_mutation(self) -> None:
        token, _ = preview_profiles("install", self.config, self.agents, self.state, now=100)
        original = profiles_module._write_at_locked
        calls = {"count": 0, "raised": False}

        def fail_once(parent_fd, name, content):
            calls["count"] += 1
            if calls["count"] == 3 and not calls["raised"]:
                calls["raised"] = True
                raise OSError("injected write failure")
            return original(parent_fd, name, content)

        with mock.patch("laneorchestrator.profiles._write_at_locked", side_effect=fail_once):
            with self.assertRaisesRegex(ProfileConflict, "failed safely"):
                apply_profiles("install", token, self.agents, self.state, now=101)
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))
        self.assertFalse((self.state / "receipts.json").exists())

    def test_injected_update_receipt_failure_restores_profiles_and_removes_backup(self) -> None:
        self._preview_apply("install")
        original_receipt = (self.state / "receipts.json").read_bytes()
        original_profiles = {name: (self.agents / name).read_bytes() for name in PROFILE_NAMES}
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("configured-router", "ultra")
        changed = EffectiveConfig(1, roles, "file")
        token, _ = preview_profiles("update", changed, self.agents, self.state, now=200)
        original = profiles_module._write_at_locked
        raised = {"value": False}

        def fail_receipt_once(parent_fd, name, content):
            if name == "receipts.json" and not raised["value"]:
                raised["value"] = True
                original(parent_fd, name, content)
                raise OSError("injected receipt failure")
            return original(parent_fd, name, content)

        with mock.patch("laneorchestrator.profiles._write_at_locked", side_effect=fail_receipt_once):
            with self.assertRaisesRegex(ProfileConflict, "failed safely"):
                apply_profiles("update", token, self.agents, self.state, now=201)
        self.assertEqual((self.state / "receipts.json").read_bytes(), original_receipt)
        self.assertEqual({name: (self.agents / name).read_bytes() for name in PROFILE_NAMES}, original_profiles)
        backups = self.state / "backups"
        self.assertFalse(backups.exists() and any(backups.glob("*.bak")))

    def test_post_publication_install_and_uninstall_failures_restore_exact_prestate(self) -> None:
        for failing_name in (PROFILE_NAMES[0], PROFILE_NAMES[2], "receipts.json"):
            with self.subTest(install=failing_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                agents = root / "agents"
                state = root / "state"
                agents.mkdir(mode=0o700)
                state.mkdir(mode=0o700)
                config = load_config(state)
                token, _ = preview_profiles("install", config, agents, state, now=100)
                original = profiles_module._write_at_locked
                raised = {"value": False}

                def fail_after_publish(parent_fd, name, content):
                    original(parent_fd, name, content)
                    if name == failing_name and not raised["value"]:
                        raised["value"] = True
                        raise OSError("post-publication durability failure")

                with mock.patch("laneorchestrator.profiles._write_at_locked", side_effect=fail_after_publish):
                    with self.assertRaisesRegex(ProfileConflict, "failed safely"):
                        apply_profiles("install", token, agents, state, now=101)
                self.assertTrue(all(not (agents / name).exists() for name in PROFILE_NAMES))
                self.assertFalse((state / "receipts.json").exists())

        for failing_name in (PROFILE_NAMES[0], PROFILE_NAMES[2]):
            with self.subTest(uninstall=failing_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                agents = root / "agents"
                state = root / "state"
                agents.mkdir(mode=0o700)
                state.mkdir(mode=0o700)
                config = load_config(state)
                token, _ = preview_profiles("install", config, agents, state, now=100)
                apply_profiles("install", token, agents, state, now=101)
                before_profiles = {name: (agents / name).read_bytes() for name in PROFILE_NAMES}
                before_receipt = (state / "receipts.json").read_bytes()
                token, _ = preview_profiles("uninstall", config, agents, state, now=200)
                original_delete = profiles_module._delete_at_locked
                raised = {"value": False}

                def fail_after_unlink(parent_fd, name):
                    original_delete(parent_fd, name)
                    if name == failing_name and not raised["value"]:
                        raised["value"] = True
                        raise OSError("post-unlink durability failure")

                with mock.patch("laneorchestrator.profiles._delete_at_locked", side_effect=fail_after_unlink):
                    with self.assertRaisesRegex(ProfileConflict, "failed safely"):
                        apply_profiles("uninstall", token, agents, state, now=201)
                self.assertEqual({name: (agents / name).read_bytes() for name in PROFILE_NAMES}, before_profiles)
                self.assertEqual((state / "receipts.json").read_bytes(), before_receipt)

    def test_concurrent_update_and_uninstall_never_leave_mixed_state(self) -> None:
        self._preview_apply("install")
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("configured-router", "ultra")
        changed = EffectiveConfig(1, roles, "file")
        update_token, _ = preview_profiles("update", changed, self.agents, self.state, now=200)
        uninstall_token, _ = preview_profiles("uninstall", self.config, self.agents, self.state, now=200)
        barrier = threading.Barrier(3)
        outcomes = []

        def run(action, token):
            barrier.wait()
            try:
                apply_profiles(action, token, self.agents, self.state, now=201)
            except Exception as error:  # noqa: BLE001 - outcome is asserted below.
                outcomes.append((action, "error", str(error)))
            else:
                outcomes.append((action, "ok", ""))

        threads = [
            threading.Thread(target=run, args=("update", update_token)),
            threading.Thread(target=run, args=("uninstall", uninstall_token)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(item[1] == "ok" for item in outcomes), 1)
        existing = [(self.agents / name).exists() for name in PROFILE_NAMES]
        self.assertIn(existing, ([False] * 4, [True] * 4))
        receipt = self._receipt()
        operations = {item["operation"] for item in receipt["profiles"]}
        self.assertEqual(operations, {"update"} if all(existing) else {"uninstall"})

    def test_shared_0755_agents_root_serializes_different_state_roots(self) -> None:
        self.agents.chmod(0o755)
        self._preview_apply("install")
        second_state = self.root / "second-state"
        second_state.mkdir(mode=0o700)
        second_receipt = second_state / "receipts.json"
        second_receipt.write_bytes((self.state / "receipts.json").read_bytes())
        second_receipt.chmod(0o600)
        roles = dict(DEFAULT_ROLES)
        roles["router"] = RoleConfig("shared-root-router", "high")
        changed = EffectiveConfig(1, roles, "file")
        update_token, _ = preview_profiles(
            "update", changed, self.agents, self.state, now=200
        )
        uninstall_token, _ = preview_profiles(
            "uninstall", self.config, self.agents, second_state, now=200
        )
        barrier = threading.Barrier(3)
        outcomes = []

        def run(action, token, state):
            barrier.wait()
            try:
                apply_profiles(action, token, self.agents, state, now=201)
            except Exception as error:  # noqa: BLE001 - asserted outcome.
                outcomes.append((action, "error", str(error)))
            else:
                outcomes.append((action, "ok", ""))

        threads = [
            threading.Thread(
                target=run, args=("update", update_token, self.state)
            ),
            threading.Thread(
                target=run,
                args=("uninstall", uninstall_token, second_state),
            ),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(item[1] == "ok" for item in outcomes), 1)
        existing = [(self.agents / name).exists() for name in PROFILE_NAMES]
        self.assertIn(existing, ([False] * 4, [True] * 4))

    def test_links_and_non_regular_destinations_are_refused(self) -> None:
        outside = self.root / "outside"
        outside.write_text("outside\n", encoding="utf-8")
        (self.agents / PROFILE_NAMES[0]).symlink_to(outside)
        with self.assertRaisesRegex(ProfileConflict, "symbolic link"):
            preview_profiles("install", self.config, self.agents, self.state, now=100)
        (self.agents / PROFILE_NAMES[0]).unlink()
        (self.agents / PROFILE_NAMES[0]).mkdir()
        with self.assertRaisesRegex(ProfileConflict, "regular file"):
            preview_profiles("install", self.config, self.agents, self.state, now=100)

    def test_unsafe_ancestor_is_refused(self) -> None:
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o700)
        unsafe.chmod(0o777)
        agents = unsafe / "agents"
        state = unsafe / "state"
        agents.mkdir(mode=0o700)
        state.mkdir(mode=0o700)
        with self.assertRaisesRegex(ProfileConflict, "ancestor"):
            preview_profiles("install", self.config, agents, state, now=100)

    def test_cross_device_and_native_windows_mutation_are_refused(self) -> None:
        with mock.patch("laneorchestrator.profiles._root_device", side_effect=(1, 2)):
            with self.assertRaisesRegex(ProfileConflict, "cross-device"):
                preview_profiles("install", self.config, self.agents, self.state, now=100)
        with mock.patch(
            "laneorchestrator.profiles.platform_mutation_supported",
            return_value=(False, "native Windows mutation is unsupported in v0.2.0"),
        ):
            with self.assertRaisesRegex(ProfileConflict, "native Windows"):
                preview_profiles("install", self.config, self.agents, self.state, now=100)


if __name__ == "__main__":
    unittest.main()
