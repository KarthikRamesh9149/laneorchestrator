from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V010 = ROOT / "tests" / "fixtures" / "profiles" / "v0.1.0"
PROFILE_NAMES = (
    "laneorchestrator-router.toml",
    "laneorchestrator-luna-executor.toml",
    "laneorchestrator-terra-executor.toml",
    "laneorchestrator-sol-reviewer.toml",
)


class UserJourneyTests(unittest.TestCase):
    """The launch journeys use a fresh state home for every test method."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-journey-")
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "codex-home"
        self.home.mkdir(mode=0o700)
        self.xdg = {name: self.root / name.lower() for name in (
            "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
        )}
        for path in self.xdg.values():
            path.mkdir(mode=0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def state(self) -> Path:
        return self.home / "laneorchestrator"

    @property
    def agents(self) -> Path:
        return self.home / "agents"

    def environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update({"CODEX_HOME": str(self.home), "HOME": str(self.home)})
        environment.update({name: str(path) for name, path in self.xdg.items()})
        return environment

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "laneorchestrator", *arguments],
            cwd=ROOT,
            env=self.environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return json.loads(result.stdout)

    def snapshot(self) -> tuple[tuple[str, str, bytes | None, int], ...]:
        entries: list[tuple[str, str, bytes | None, int]] = []
        for path in sorted(self.root.rglob("*")):
            metadata = path.lstat()
            relative = str(path.relative_to(self.root))
            if stat.S_ISREG(metadata.st_mode):
                entries.append((relative, "file", path.read_bytes(), stat.S_IMODE(metadata.st_mode)))
            elif stat.S_ISDIR(metadata.st_mode):
                entries.append((relative, "directory", None, stat.S_IMODE(metadata.st_mode)))
            elif stat.S_ISLNK(metadata.st_mode):
                entries.append((relative, "symlink", os.fsencode(os.readlink(path)), stat.S_IMODE(metadata.st_mode)))
            else:
                entries.append((relative, "other", None, stat.S_IMODE(metadata.st_mode)))
        return tuple(entries)

    def managed_snapshot(self, root: Path) -> tuple[tuple[str, str, bytes | None, int], ...]:
        return tuple(item for item in self.snapshot_root(root) if not item[0].endswith(".laneorchestrator-state.lock"))

    def snapshot_root(self, root: Path) -> tuple[tuple[str, str, bytes | None, int], ...]:
        entries: list[tuple[str, str, bytes | None, int]] = []
        for path in sorted(root.rglob("*")):
            metadata = path.lstat()
            relative = str(path.relative_to(root))
            if stat.S_ISREG(metadata.st_mode):
                entries.append((relative, "file", path.read_bytes(), stat.S_IMODE(metadata.st_mode)))
            elif stat.S_ISDIR(metadata.st_mode):
                entries.append((relative, "directory", None, stat.S_IMODE(metadata.st_mode)))
            elif stat.S_ISLNK(metadata.st_mode):
                entries.append((relative, "symlink", os.fsencode(os.readlink(path)), stat.S_IMODE(metadata.st_mode)))
            else:
                entries.append((relative, "other", None, stat.S_IMODE(metadata.st_mode)))
        return tuple(entries)

    def preview_apply(self, action: str) -> dict[str, Any]:
        preview = self.run_cli("profiles", action, "preview", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        token = self.payload(preview)["data"]["token"]
        applied = self.run_cli("profiles", action, "apply", "--token", token, "--json")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertNotIn(token, applied.stdout + applied.stderr)
        return self.payload(applied)

    def install_profiles(self) -> None:
        self.assertEqual(self.preview_apply("install")["data"]["change_count"], 4)

    def test_clean_user_routes_without_external_agent_pack(self) -> None:
        self.install_profiles()
        route = self.run_cli(
            "route", "--objective", "Add a dashboard filter", "--files", "3",
            "--risk-assessment", "normal", "--json",
        )
        catalog = self.run_cli(
            "catalog", "--query", "Add a dashboard filter", "--cwd", str(self.root),
            "--no-default-roots", "--skills-root", str(self.root / "empty-skills"), "--json",
        )
        self.assertEqual(route.returncode, 0, route.stderr)
        self.assertEqual(self.payload(route)["data"]["route"]["lane"], "terra")
        self.assertEqual(catalog.returncode, 0, catalog.stderr)
        catalog_data = self.payload(catalog)["data"]["catalog"]
        self.assertEqual(catalog_data["skills"], [])
        self.assertEqual(catalog_data["agents"], [])

    def test_user_with_optional_specialists_discovers_only_metadata(self) -> None:
        self.install_profiles()
        skills = self.home / "skills"
        skill = skills / "dashboard-observability" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: dashboard-observability\ndescription: Build dashboard observability filters.\n---\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "catalog", "--query", "dashboard observability filter", "--cwd", str(self.root),
            "--no-default-roots", "--skills-root", str(skills), "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.payload(result)["data"]["catalog"]
        self.assertEqual([item["name"] for item in payload["skills"]], ["dashboard-observability"])
        self.assertNotIn("instruction", payload)
        self.assertEqual({path.name for path in self.agents.glob("laneorchestrator-*.toml")}, set(PROFILE_NAMES))

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_unmanaged_collision_is_refused_without_partial_state(self) -> None:
        self.state.mkdir(mode=0o700)
        self.agents.mkdir(mode=0o700)
        collision = self.agents / "laneorchestrator-router.toml"
        collision.write_bytes(b"foreign profile\n")
        before = (self.managed_snapshot(self.agents), self.managed_snapshot(self.state))
        result = self.run_cli("profiles", "install", "preview", "--json")
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload["errors"][0]["code"], "PROFILE_CONFLICT")
        self.assertEqual(collision.read_bytes(), b"foreign profile\n")
        self.assertFalse((self.state / "receipts.json").exists())
        self.assertFalse((self.state / "plans").exists())
        self.assertEqual((self.managed_snapshot(self.agents), self.managed_snapshot(self.state)), before)

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_exact_v010_adoption_creates_managed_receipt(self) -> None:
        self.agents.mkdir(mode=0o700)
        expected = {path.name: path.read_bytes() for path in V010.glob("*.toml")}
        for name, content in expected.items():
            (self.agents / name).write_bytes(content)
        applied = self.preview_apply("adopt")
        receipt = json.loads((self.state / "receipts.json").read_text(encoding="utf-8"))
        self.assertEqual(applied["data"]["change_count"], 4)
        self.assertEqual({entry["operation"] for entry in receipt["profiles"]}, {"adopt"})
        self.assertTrue(all((self.agents / name).read_text(encoding="utf-8").startswith("# managed-by:") for name in expected))

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_configuration_preview_then_apply_is_one_time_and_private(self) -> None:
        preview = self.run_cli(
            "configure", "preview", "--set", "router.reasoning_effort=ultra", "--json"
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        token = self.payload(preview)["data"]["token"]
        applied = self.run_cli("configure", "apply", "--token", token, "--json")
        replay = self.run_cli("configure", "apply", "--token", token, "--json")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(replay.returncode, 1)
        self.assertEqual(self.payload(replay)["errors"][0]["code"], "PLAN_CONSUMED")
        self.assertNotIn(token, replay.stdout + replay.stderr)
        self.assertEqual(json.loads((self.state / "config.json").read_text())["roles"]["router"]["reasoning_effort"], "ultra")
        self.assertEqual((self.state / "config.json").stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_managed_update_creates_private_backup(self) -> None:
        self.install_profiles()
        previous = (self.agents / "laneorchestrator-router.toml").read_bytes()
        preview = self.run_cli("configure", "preview", "--set", "router.model=journey-router", "--json")
        token = self.payload(preview)["data"]["token"]
        self.assertEqual(self.run_cli("configure", "apply", "--token", token, "--json").returncode, 0)
        self.preview_apply("update")
        receipt = json.loads((self.state / "receipts.json").read_text())
        entry = next(item for item in receipt["profiles"] if item["name"] == "laneorchestrator-router.toml")
        backup = self.state / "backups" / (entry["name"] + "." + entry["prior_backup_sha256"] + ".bak")
        self.assertEqual(entry["operation"], "update")
        self.assertEqual(backup.read_bytes(), previous)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_drift_refusal_preserves_all_prior_bytes(self) -> None:
        self.install_profiles()
        target = self.agents / "laneorchestrator-router.toml"
        target.write_bytes(target.read_bytes() + b"# local drift\n")
        before = self.snapshot()
        result = self.run_cli("profiles", "update", "preview", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.payload(result)["errors"][0]["code"], "PROFILE_CONFLICT")
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_safe_uninstall_preserves_unrelated_file_and_configuration(self) -> None:
        self.install_profiles()
        preview = self.run_cli("configure", "preview", "--set", "router.model=uninstall-router", "--json")
        token = self.payload(preview)["data"]["token"]
        self.assertEqual(self.run_cli("configure", "apply", "--token", token, "--json").returncode, 0)
        unrelated = self.agents / "third-party.toml"
        unrelated.write_bytes(b"name = 'third-party'\n")
        config = (self.state / "config.json").read_bytes()
        self.preview_apply("uninstall")
        self.assertTrue(unrelated.is_file())
        self.assertEqual(unrelated.read_bytes(), b"name = 'third-party'\n")
        self.assertEqual((self.state / "config.json").read_bytes(), config)
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_high_risk_route_fails_closed_when_sol_is_missing(self) -> None:
        self.install_profiles()
        (self.agents / "laneorchestrator-sol-reviewer.toml").unlink()
        result = self.run_cli("route", "--objective", "Migrate OAuth tokens", "--files", "2", "--risk-assessment", "high", "--json")
        self.assertEqual(result.returncode, 1)
        payload = self.payload(result)
        self.assertEqual(payload["data"]["route"]["lane"], "sol-plan-terra-sol-review")
        self.assertEqual(payload["errors"][0]["code"], "REVIEWER_MISSING")

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_normal_route_fails_closed_when_terra_is_missing(self) -> None:
        self.install_profiles()
        (self.agents / "laneorchestrator-terra-executor.toml").unlink()
        result = self.run_cli("route", "--objective", "Add a dashboard filter", "--files", "3", "--risk-assessment", "normal", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.payload(result)["errors"][0]["code"], "MAIN_IMPLEMENTER_MISSING")

    @unittest.skipUnless(os.name == "posix", "profile mutation is POSIX-only")
    def test_luna_missing_falls_back_to_terra(self) -> None:
        self.install_profiles()
        (self.agents / "laneorchestrator-luna-executor.toml").unlink()
        result = self.run_cli(
            "route", "--objective", "Fix a README typo", "--known-area", "--acceptance-criteria",
            "--files", "1", "--risk-assessment", "low", "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.payload(result)["data"]
        self.assertEqual(payload["route"]["lane"], "luna")
        self.assertEqual(payload["effective_lane"], "terra")
        self.assertEqual(payload["fallback"], "small_task_executor->main_implementer")

    def test_local_marketplace_add_install_list_remove_is_isolated(self) -> None:
        codex = shutil.which("codex")
        if codex is None:
            self.skipTest("requires the local Codex CLI to exercise marketplace integration")
        workspace = self.root / "unrelated-workspace"
        workspace.mkdir()

        def run(*arguments: str) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [codex, *arguments], cwd=workspace, env=self.environment(), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
            return result

        run("plugin", "marketplace", "add", str(ROOT), "--json")
        available = json.loads(run("plugin", "list", "--available", "--json").stdout)["available"]
        self.assertTrue(any(item.get("name", item.get("pluginId")) == "laneorchestrator" for item in available))
        installed = json.loads(run("plugin", "add", "laneorchestrator@laneorchestrator", "--json").stdout)
        installed_path = Path(installed["installedPath"]).resolve()
        self.assertTrue(installed_path.is_relative_to(self.home))
        self.assertTrue(installed_path.is_dir())
        listed = json.loads(run("plugin", "list", "--json").stdout)["installed"]
        self.assertTrue(any(item.get("name", item.get("pluginId")) == "laneorchestrator" for item in listed))
        run("plugin", "remove", "laneorchestrator@laneorchestrator", "--json")
        self.assertFalse(installed_path.exists())
        run("plugin", "marketplace", "remove", "laneorchestrator", "--json")
        self.assertNotIn("laneorchestrator", run("plugin", "marketplace", "list", "--json").stdout)


if __name__ == "__main__":
    unittest.main()
