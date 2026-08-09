from __future__ import annotations

import subprocess
import tempfile
import unittest
import stat
import os
import shutil
from pathlib import Path

from laneorchestrator.config import DEFAULT_ROLES, load_config
from laneorchestrator.models import EffectiveConfig, RoleConfig
from laneorchestrator.profiles import apply_profiles, preview_profiles
from scripts.install_agents import load_templates, state_root_for_target

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-agents.sh"
PRESENTATION_NAMES = (
    "laneorchestrator-luna-executor.toml",
    "laneorchestrator-router.toml",
    "laneorchestrator-sol-reviewer.toml",
    "laneorchestrator-terra-executor.toml",
)


class InstallerTests(unittest.TestCase):
    def test_collision_safe_installer(self) -> None:
        subprocess.run(["sh", str(ROOT / "tests" / "test_installer.sh")], check=True)

    def test_check_mode_reports_missing_profiles_without_creating_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing" / "agents"
            result = subprocess.run(["sh", str(INSTALLER), "--check", "--target", str(target)], check=True, capture_output=True, text=True)
            self.assertFalse(target.exists())
        self.assertEqual(result.stdout.count("missing "), 4)
        self.assertEqual(
            result.stdout.splitlines(),
            ["missing {0}".format(target / name) for name in PRESENTATION_NAMES],
        )

    def test_new_profiles_are_private_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "agents"
            subprocess.run(["sh", str(INSTALLER), "--target", str(target)], check=True, capture_output=True, text=True)
            installed = sorted(target.glob("laneorchestrator-*.toml"))
            self.assertEqual(len(installed), 4)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in installed))

    def test_help_documents_safe_modes(self) -> None:
        result = subprocess.run(["sh", str(INSTALLER), "--help"], check=True, capture_output=True, text=True)
        self.assertIn("--check", result.stdout)
        self.assertIn("--target", result.stdout)

    def test_rejects_filesystem_root_as_target(self) -> None:
        result = subprocess.run(["sh", str(INSTALLER), "--target", "/"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("filesystem root", result.stderr)

    def test_installer_creates_canonical_receipt_then_update_and_uninstall_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "agents"
            target.mkdir(mode=0o755)
            result = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.stdout.splitlines(),
                ["installed " + name for name in PRESENTATION_NAMES],
            )
            state = state_root_for_target(target)
            self.assertTrue((state / "receipts.json").is_file())
            config = load_config(state)
            roles = dict(DEFAULT_ROLES)
            roles["router"] = RoleConfig("adapter-router", "high")
            changed = EffectiveConfig(1, roles, "file")
            token, _ = preview_profiles("update", changed, target, state, now=100)
            apply_profiles("update", token, target, state, now=101)
            token, _ = preview_profiles("uninstall", changed, target, state, now=200)
            apply_profiles("uninstall", token, target, state, now=201)
            self.assertTrue(all(not path.exists() for path in target.glob("laneorchestrator-*.toml")))

    def test_legacy_output_order_and_collision_streams_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "agents"
            first = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                first.stdout.splitlines(),
                ["installed " + name for name in PRESENTATION_NAMES],
            )
            second = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                second.stdout.splitlines(),
                ["unchanged " + name for name in PRESENTATION_NAMES],
            )
            router = target / "laneorchestrator-router.toml"
            router.write_text(router.read_text() + "# drift\n", encoding="utf-8")
            conflict = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(conflict.returncode, 2)
            self.assertEqual(
                conflict.stdout.splitlines(),
                [
                    "unchanged laneorchestrator-luna-executor.toml",
                    "unchanged laneorchestrator-sol-reviewer.toml",
                    "unchanged laneorchestrator-terra-executor.toml",
                ],
            )
            self.assertEqual(
                conflict.stderr,
                "conflict {0} (left untouched)\n".format(router),
            )

    def test_exact_v010_set_is_adopted_but_near_match_is_exit_two_and_untouched(self) -> None:
        fixtures = ROOT / "tests" / "fixtures" / "profiles" / "v0.1.0"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "agents"
            target.mkdir(mode=0o755)
            for source in fixtures.glob("*.toml"):
                shutil.copyfile(source, target / source.name)
            result = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stdout.count("installed "), 4)
            self.assertTrue(all(path.read_text().startswith("# managed-by:") for path in target.glob("laneorchestrator-*.toml")))
            self.assertTrue((state_root_for_target(target) / "receipts.json").exists())

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "agents"
            target.mkdir(mode=0o700)
            for source in fixtures.glob("*.toml"):
                shutil.copyfile(source, target / source.name)
            changed = target / "laneorchestrator-router.toml"
            changed.write_text(changed.read_text() + "# near\n", encoding="utf-8")
            before = changed.read_bytes()
            result = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("conflict ", result.stderr)
            self.assertEqual(changed.read_bytes(), before)
            self.assertFalse(state_root_for_target(target).exists())

    def test_source_loading_ignores_a_fifth_unrelated_toml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            templates = Path(directory)
            for name in (
                "laneorchestrator-router.toml",
                "laneorchestrator-luna-executor.toml",
                "laneorchestrator-terra-executor.toml",
                "laneorchestrator-sol-reviewer.toml",
            ):
                shutil.copyfile(ROOT / "agents" / name, templates / name)
            (templates / "third-party.toml").write_text('name = "third-party"\n', encoding="utf-8")
            loaded = load_templates(templates)
            self.assertEqual([path.name for path in loaded], [
                "laneorchestrator-router.toml",
                "laneorchestrator-luna-executor.toml",
                "laneorchestrator-terra-executor.toml",
                "laneorchestrator-sol-reviewer.toml",
            ])

    def test_default_check_uses_isolated_home_and_remains_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment["HOME"] = directory
            result = subprocess.run(
                ["sh", str(INSTALLER), "--check"],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.stdout.count("missing "), 4)
            self.assertFalse((Path(directory) / ".codex").exists())

    def test_malformed_derived_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "agents"
            subprocess.run(["sh", str(INSTALLER), "--target", str(target)], check=True, capture_output=True)
            state = state_root_for_target(target)
            (state / "config.json").write_text("{malformed", encoding="utf-8")
            result = subprocess.run(
                ["sh", str(INSTALLER), "--target", str(target)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("configuration", result.stderr.lower())

    def test_partial_legacy_and_non_regular_sets_fail_without_tracebacks(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "profiles" / "v0.1.0" / "laneorchestrator-router.toml"
        for leaf_kind in ("partial", "directory", "symlink"):
            with self.subTest(leaf_kind=leaf_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                target = root / "agents"
                target.mkdir(mode=0o700)
                shutil.copyfile(fixture, target / fixture.name)
                if leaf_kind == "directory":
                    (target / "laneorchestrator-luna-executor.toml").mkdir()
                elif leaf_kind == "symlink":
                    (target / "laneorchestrator-luna-executor.toml").symlink_to(root / "outside")
                result = subprocess.run(
                    ["sh", str(INSTALLER), "--target", str(target)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("conflict ", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(state_root_for_target(target).exists())

    def test_group_or_other_writable_target_is_rejected_before_state_creation(self) -> None:
        for mode in (0o770, 0o775, 0o777):
            with self.subTest(mode=oct(mode)), tempfile.TemporaryDirectory() as directory:
                target = Path(directory).resolve() / "agents"
                target.mkdir(mode=mode)
                target.chmod(mode)
                result = subprocess.run(
                    ["sh", str(INSTALLER), "--target", str(target)],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsafe target directory", result.stderr)
                self.assertFalse(state_root_for_target(target).exists())


if __name__ == "__main__":
    unittest.main()
