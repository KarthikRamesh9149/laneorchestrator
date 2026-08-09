from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from laneorchestrator.config import DEFAULT_ROLES, serialize_config
from laneorchestrator.diagnostics import Level
from laneorchestrator.doctor import check_codex_cli, inspect_role_evidence, run_doctor
from laneorchestrator.models import Availability, EffectiveConfig
from laneorchestrator.profiles import PROFILE_NAMES, TEMPLATE_VERSION, render_profiles


EXPECTED_CODES = [
    "PYTHON_VERSION",
    "PLATFORM_SUPPORT",
    "CODEX_CLI",
    "PLUGIN_MANIFEST",
    "BUNDLED_PROFILES",
    "INSTALLED_PROFILES",
    "CONFIG_SCHEMA",
    "STATE_PATH_SAFETY",
    "ROLE_ROUTER",
    "ROLE_SMALL",
    "ROLE_MAIN",
    "ROLE_REVIEWER",
    "CAPABILITY_DISCOVERY",
    "MODEL_ENTITLEMENT",
]


def _write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)


def _profile_fixture(root: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    root = root.resolve()
    repo = root / "repo"
    state = root / "state"
    agents = root / "agents"
    repo.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    agents.mkdir(mode=0o700)
    config = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
    rendered = render_profiles(config)
    for name, content in rendered.items():
        _write(repo / "agents" / name, content)
        _write(agents / name, content)
    manifests = {
        repo / ".codex-plugin" / "plugin.json": {
            "name": "laneorchestrator",
            "version": "0.2.0",
        },
        repo / "plugin.json": {
            "name": "laneorchestrator",
            "version": "0.2.0",
        },
        repo / ".agents" / "plugins" / "marketplace.json": {
            "name": "laneorchestrator",
            "plugins": [
                {
                    "name": "laneorchestrator",
                    "source": {"path": ".", "source": "local"},
                }
            ],
        },
    }
    for path, payload in manifests.items():
        _write(path, (json.dumps(payload) + "\n").encode("utf-8"), 0o644)
    _write(
        repo / "skills" / "laneorchestrator" / "SKILL.md",
        b"---\nname: laneorchestrator\ndescription: Safe routing.\n---\n",
        0o644,
    )
    config_hash = hashlib.sha256(serialize_config(config)).hexdigest()
    entries = []
    for name in PROFILE_NAMES:
        entries.append(
            {
                "name": name,
                "destination": str(agents / name),
                "template_version": TEMPLATE_VERSION,
                "content_sha256": hashlib.sha256(rendered[name]).hexdigest(),
                "config_sha256": config_hash,
                "prior_backup_sha256": None,
                "operation": "install",
            }
        )
    receipt = {"schema_version": 1, "profiles": entries}
    _write(state / "receipts.json", (json.dumps(receipt) + "\n").encode("utf-8"))
    binary = root / "bin" / "codex"
    _write(binary, b"#!/bin/sh\nprintf 'codex-cli 1.2.3\\n'\n", 0o700)
    return repo, state, agents, {"PATH": str(binary.parent)}


def _diagnostic(result: object, code: str) -> object:
    return next(item for item in result.diagnostics if item.code == code)  # type: ignore[attr-defined]


def _tree_snapshot(root: Path) -> list[tuple[str, str, int, str]]:
    snapshot: list[tuple[str, str, int, str]] = []
    pending = [root]
    while pending:
        path = pending.pop()
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            snapshot.append((str(path.relative_to(root.parent)), "missing", 0, ""))
            continue
        relative = str(path.relative_to(root.parent))
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            snapshot.append((relative, "link", mode, os.readlink(path)))
        elif stat.S_ISDIR(metadata.st_mode):
            snapshot.append((relative, "directory", mode, ""))
            pending.extend(sorted(path.iterdir(), reverse=True))
        elif stat.S_ISREG(metadata.st_mode):
            snapshot.append((relative, "file", mode, hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            snapshot.append((relative, "other", mode, ""))
    return sorted(snapshot)


class DoctorContractTests(unittest.TestCase):
    def test_doctor_emits_the_exact_stable_diagnostic_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            result = run_doctor(root / "repo", root / "state", root / "agents", env={"PATH": ""})
        self.assertEqual([item.code for item in result.diagnostics], EXPECTED_CODES)

    def test_unobservable_entitlement_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            result = run_doctor(root / "repo", root / "state", root / "agents", env={"PATH": ""})
        entitlement = next(item for item in result.diagnostics if item.code == "MODEL_ENTITLEMENT")
        self.assertEqual(entitlement.level, Level.UNKNOWN)
        self.assertNotIn("available", entitlement.message.casefold())

    def test_verified_fixture_passes_except_authoritative_entitlement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            result = run_doctor(repo, state, agents, env=env)
        self.assertTrue(result.ok)
        self.assertEqual(
            [item.level for item in result.diagnostics],
            [Level.PASS] * 13 + [Level.UNKNOWN],
        )

    def test_missing_optional_small_role_warns_and_falls_back_to_terra(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            (agents / "laneorchestrator-luna-executor.toml").unlink()
            result = run_doctor(repo, state, agents, env=env)
        small = _diagnostic(result, "ROLE_SMALL")
        self.assertEqual(small.level, Level.WARN)
        self.assertEqual(small.evidence["fallback_role"], "main_implementer")
        self.assertTrue(result.ok)

    def test_each_required_role_fails_when_its_profile_is_missing(self) -> None:
        cases = (
            ("laneorchestrator-router.toml", "ROLE_ROUTER"),
            ("laneorchestrator-terra-executor.toml", "ROLE_MAIN"),
            ("laneorchestrator-sol-reviewer.toml", "ROLE_REVIEWER"),
        )
        for name, code in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                repo, state, agents, env = _profile_fixture(Path(temporary))
                (agents / name).unlink()
                result = run_doctor(repo, state, agents, env=env)
                diagnostic = _diagnostic(result, code)
                self.assertEqual(diagnostic.level, Level.FAIL)
                self.assertFalse(result.ok)
                if code == "ROLE_REVIEWER":
                    self.assertIn("high-risk", diagnostic.message)

    def test_role_evidence_is_profile_evidence_not_model_entitlement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _repo, _state, agents, _env = _profile_fixture(Path(temporary))
            config = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
            evidence = inspect_role_evidence(config, agents)
            self.assertEqual(evidence["router"].availability, Availability.AVAILABLE)
            (agents / "laneorchestrator-router.toml").write_text("not managed\n", encoding="utf-8")
            self.assertEqual(
                inspect_role_evidence(config, agents)["router"].availability,
                Availability.UNKNOWN,
            )

    def test_missing_malformed_flooding_and_timed_out_codex_are_bounded_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            empty = check_codex_cli({"PATH": ""})
            self.assertEqual(empty.level, Level.FAIL)
            scripts = {
                "malformed": b"#!/bin/sh\nprintf 'not-a-version\\n'\n",
                "flood": b"#!/bin/sh\nwhile :; do printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' >&2; done\n",
                "timeout": b"#!/bin/sh\n/bin/sleep 30\n",
            }
            for name, content in scripts.items():
                with self.subTest(name=name):
                    binary = root / name / "codex"
                    _write(binary, content, 0o700)
                    started = time.monotonic()
                    diagnostic = check_codex_cli({"PATH": str(binary.parent)})
                    elapsed = time.monotonic() - started
                    self.assertEqual(diagnostic.level, Level.FAIL)
                    self.assertLess(elapsed, 7.0)
                    self.assertLess(len(json.dumps(diagnostic.to_dict())), 4096)
                    self.assertNotIn("xxxxxxxx", diagnostic.message)
                    if name == "flood":
                        self.assertEqual(diagnostic.evidence["retained_bytes"], 64 * 1024)

    def test_codex_probe_rejects_relative_and_empty_path_entries(self) -> None:
        for path_value in (".", "relative/bin", os.pathsep + "/usr/bin", "/usr/bin" + os.pathsep):
            with self.subTest(path=path_value):
                diagnostic = check_codex_cli({"PATH": path_value})
                self.assertEqual(diagnostic.level, Level.FAIL)
                self.assertEqual(diagnostic.evidence["probe"], "unsafe_path")

    def test_codex_probe_rejects_malformed_environment_and_linked_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary = root / "real-codex"
            _write(binary, b"#!/bin/sh\nprintf 'codex-cli 1.2.3\\n'\n", 0o700)
            bin_root = root / "bin"
            bin_root.mkdir()
            (bin_root / "codex").symlink_to(binary)
            linked = check_codex_cli({"PATH": str(bin_root)})
            self.assertEqual(linked.level, Level.FAIL)
            self.assertEqual(linked.evidence["probe"], "unsafe_executable")

            malformed = check_codex_cli({"PATH": str(bin_root), "BAD": None})  # type: ignore[dict-item]
            self.assertEqual(malformed.level, Level.FAIL)
            self.assertEqual(malformed.evidence["probe"], "invalid_environment")

    def test_codex_probe_kills_background_descendants_that_retain_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sentinel = root / "escaped"
            binary = root / "bin" / "codex"
            _write(
                binary,
                b"#!/bin/sh\n( /bin/sleep 1; /usr/bin/touch \"$SENTINEL\" ) &\nexit 0\n",
                0o700,
            )
            diagnostic = check_codex_cli({"PATH": str(binary.parent), "SENTINEL": str(sentinel)})
            time.sleep(1.2)
            self.assertEqual(diagnostic.level, Level.FAIL)
            self.assertFalse(sentinel.exists())

    def test_codex_probe_platform_pipe_failure_is_a_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary = root / "bin" / "codex"
            _write(binary, b"#!/bin/sh\nprintf 'codex-cli 1.2.3\\n'\n", 0o700)
            with mock.patch("laneorchestrator.doctor.selectors.DefaultSelector", side_effect=OSError("unsupported")):
                diagnostic = check_codex_cli({"PATH": str(binary.parent)})
            self.assertEqual(diagnostic.level, Level.FAIL)
            self.assertEqual(diagnostic.evidence["probe"], "execution_error")

    def test_profile_drift_bad_mode_and_invalid_receipt_fail_truthfully(self) -> None:
        mutations = (
            lambda state, agents: (agents / PROFILE_NAMES[0]).write_bytes(b"drift\n"),
            lambda state, agents: (agents / PROFILE_NAMES[0]).chmod(0o644),
            lambda state, agents: (state / "receipts.json").write_bytes(b"{bad"),
        )
        expected = ("drift", "bad_mode", "invalid_receipt")
        for mutate, status_name in zip(mutations, expected):
            with self.subTest(status=status_name), tempfile.TemporaryDirectory() as temporary:
                repo, state, agents, env = _profile_fixture(Path(temporary))
                mutate(state, agents)
                result = run_doctor(repo, state, agents, env=env)
                profiles = _diagnostic(result, "INSTALLED_PROFILES")
                self.assertEqual(profiles.level, Level.FAIL)
                self.assertIn(status_name, set(profiles.evidence["profiles"].values()))

    def test_hostile_profile_and_receipt_objects_are_never_treated_as_managed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            profile = agents / PROFILE_NAMES[0]
            profile.unlink()
            profile.symlink_to(agents / PROFILE_NAMES[1])
            result = run_doctor(repo, state, agents, env=env)
            self.assertIn(
                "unsafe",
                set(_diagnostic(result, "INSTALLED_PROFILES").evidence["profiles"].values()),
            )

        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            receipt_path = state / "receipts.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["profiles"][0]["operation"] = "update"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipt_path.chmod(0o600)
            result = run_doctor(repo, state, agents, env=env)
            self.assertIn(
                "invalid_receipt",
                set(_diagnostic(result, "INSTALLED_PROFILES").evidence["profiles"].values()),
            )

        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            receipt_path = state / "receipts.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["profiles"][0]["operation"] = []
            _write(receipt_path, json.dumps(receipt).encode("utf-8"))
            result = run_doctor(repo, state, agents, env=env)
            self.assertIn(
                "invalid_receipt",
                set(_diagnostic(result, "INSTALLED_PROFILES").evidence["profiles"].values()),
            )

    def test_malformed_and_linked_configuration_become_diagnostics(self) -> None:
        for linked in (False, True):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as temporary:
                repo, state, agents, env = _profile_fixture(Path(temporary))
                config = state / "config.json"
                if linked:
                    target = Path(temporary) / "outside.json"
                    target.write_text("{}", encoding="utf-8")
                    config.symlink_to(target)
                else:
                    config.write_text("{bad", encoding="utf-8")
                result = run_doctor(repo, state, agents, env=env)
                self.assertEqual(_diagnostic(result, "CONFIG_SCHEMA").level, Level.FAIL)
                self.assertFalse(result.ok)

    def test_configuration_permissions_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            config = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
            _write(state / "config.json", serialize_config(config), 0o644)
            result = run_doctor(repo, state, agents, env=env)
        diagnostic = _diagnostic(result, "CONFIG_SCHEMA")
        self.assertEqual(diagnostic.level, Level.FAIL)
        self.assertEqual(diagnostic.evidence["inspection"], "bad_mode")

    def test_configuration_and_receipt_hash_drift_blocks_managed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            changed_roles = dict(DEFAULT_ROLES)
            changed_roles["router"] = type(DEFAULT_ROLES["router"])("changed-router", "high")
            changed = EffectiveConfig(1, changed_roles, "file")
            _write(state / "config.json", serialize_config(changed))
            result = run_doctor(repo, state, agents, env=env)
            self.assertEqual(_diagnostic(result, "INSTALLED_PROFILES").level, Level.FAIL)
            self.assertIn("drift", set(_diagnostic(result, "INSTALLED_PROFILES").evidence["profiles"].values()))

        with tempfile.TemporaryDirectory() as temporary:
            repo, state, agents, env = _profile_fixture(Path(temporary))
            receipt_path = state / "receipts.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            for entry in receipt["profiles"]:
                entry["config_sha256"] = "0" * 64
            _write(receipt_path, (json.dumps(receipt) + "\n").encode("utf-8"))
            result = run_doctor(repo, state, agents, env=env)
            self.assertEqual(_diagnostic(result, "INSTALLED_PROFILES").level, Level.FAIL)
            self.assertEqual(set(_diagnostic(result, "INSTALLED_PROFILES").evidence["profiles"].values()), {"drift"})

    def test_missing_and_unsafe_roots_are_strictly_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo = root / "repo"
            repo.mkdir()
            before = _tree_snapshot(root)
            first = run_doctor(repo, root / "missing-state", root / "missing-agents", env={"PATH": ""})
            second = run_doctor(repo, root / "missing-state", root / "missing-agents", env={"PATH": ""})
            self.assertEqual(before, _tree_snapshot(root))
            self.assertEqual(first.to_dict(), second.to_dict())

            safe_state = root / "safe-state"
            safe_state.mkdir(mode=0o700)
            linked_state = root / "linked-state"
            linked_state.symlink_to(safe_state, target_is_directory=True)
            before = _tree_snapshot(root)
            result = run_doctor(repo, linked_state, root / "missing-agents", env={"PATH": ""})
            self.assertEqual(_diagnostic(result, "STATE_PATH_SAFETY").level, Level.FAIL)
            self.assertEqual(before, _tree_snapshot(root))

    def test_unsafe_ancestor_and_directory_permissions_fail_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo, state, agents, env = _profile_fixture(root)
            state.chmod(0o755)
            before = _tree_snapshot(root)
            result = run_doctor(repo, state, agents, env=env)
            self.assertEqual(_diagnostic(result, "STATE_PATH_SAFETY").level, Level.FAIL)
            self.assertEqual(before, _tree_snapshot(root))

            actual = root / "actual"
            actual.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(actual, target_is_directory=True)
            result = run_doctor(repo, linked_parent / "state", agents, env=env)
            self.assertEqual(_diagnostic(result, "STATE_PATH_SAFETY").level, Level.FAIL)

            state.chmod(0o700)
            agents.chmod(0o777)
            before = _tree_snapshot(root)
            result = run_doctor(repo, state, agents, env=env)
            self.assertEqual(_diagnostic(result, "STATE_PATH_SAFETY").level, Level.FAIL)
            self.assertEqual(before, _tree_snapshot(root))


if __name__ == "__main__":
    unittest.main()
