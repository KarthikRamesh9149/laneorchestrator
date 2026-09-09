from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from laneorchestrator.config import load_config, serialize_config
from laneorchestrator.profiles import PROFILE_NAMES, render_profiles


ROOT = Path(__file__).resolve().parents[1]
V010 = ROOT / "tests" / "fixtures" / "profiles" / "v0.1.0"
INITIAL_ROUTER_SHA256 = "06b31988a6dcd6092cb43731f3d25a560dfb365d9895c675d45a38d3c5b43c39"
V024_MARKER = b"# managed-by: laneorchestrator 0.2.4\n"
V030_MARKER = b"# managed-by: laneorchestrator 0.3.0\n"


@unittest.skipUnless(os.name == "posix", "managed installation journeys are POSIX-only")
class InstallJourneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-install-journey-")
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "codex-home"
        self.home.mkdir(mode=0o700)
        self.agents = self.home / "agents"
        self.state = self.home / "laneorchestrator"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update({"CODEX_HOME": os.fspath(self.home), "HOME": os.fspath(self.home)})
        return subprocess.run(
            [sys.executable, "-m", "laneorchestrator", *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return json.loads(result.stdout)

    def preview_apply(self, action: str) -> dict[str, Any]:
        preview = self.run_cli("profiles", action, "preview", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_data = self.payload(preview)["data"]
        applied = self.run_cli(
            "profiles",
            action,
            "apply",
            "--token",
            preview_data["token"],
            "--approval",
            "approve:" + preview_data["approval_digest"],
            "--json",
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertNotIn(preview_data["token"], applied.stdout + applied.stderr)
        return self.payload(applied)

    def test_initial_commit_profile_mix_adopts_without_manual_repair(self) -> None:
        self.agents.mkdir(mode=0o700)
        initial_router = (V010 / "laneorchestrator-router.toml").read_bytes().replace(
            b"\nIf Luna or an optional specialist is unavailable, fall back to Terra / High and report it. "
            b"If Terra is unavailable, pause because implementation cannot proceed. If Sol is unavailable "
            b"for required high-risk planning or independent review, pause rather than weakening the high-risk route.\n",
            b"",
        )
        self.assertEqual(hashlib.sha256(initial_router).hexdigest(), INITIAL_ROUTER_SHA256)
        for name in PROFILE_NAMES:
            content = initial_router if name == "laneorchestrator-router.toml" else (V010 / name).read_bytes()
            (self.agents / name).write_bytes(content)
            self.assertEqual(stat.S_IMODE((self.agents / name).stat().st_mode), 0o644)

        before = self.payload(self.run_cli("status", "--json"))["data"]
        self.assertEqual(set(before["managed_profile_state"].values()), {"bad_mode"})

        adopted = self.preview_apply("adopt")
        self.assertEqual(adopted["data"]["change_count"], 4)
        after = self.payload(self.run_cli("status", "--json"))["data"]
        self.assertEqual(set(after["managed_profile_state"].values()), {"managed"})
        for name in PROFILE_NAMES:
            path = self.agents / name
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertTrue(path.read_bytes().startswith(V030_MARKER))

        unrelated = self.agents / "user-owned.toml"
        unrelated.write_text('name = "user-owned"\n', encoding="utf-8")
        self.preview_apply("uninstall")
        self.assertTrue(unrelated.is_file())
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))

    def test_v024_managed_profiles_update_with_backups_then_uninstall(self) -> None:
        self.agents.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        config = load_config(self.state)
        current = render_profiles(config)
        previous = {name: content.replace(V030_MARKER, V024_MARKER, 1) for name, content in current.items()}
        config_hash = hashlib.sha256(serialize_config(config)).hexdigest()
        receipt = {
            "schema_version": 1,
            "profiles": [
                {
                    "name": name,
                    "destination": os.fspath(self.agents / name),
                    "template_version": "0.2.4",
                    "content_sha256": hashlib.sha256(previous[name]).hexdigest(),
                    "config_sha256": config_hash,
                    "prior_backup_sha256": None,
                    "operation": "install",
                }
                for name in PROFILE_NAMES
            ],
        }
        for name, content in previous.items():
            (self.agents / name).write_bytes(content)
            (self.agents / name).chmod(0o600)
        receipt_path = self.state / "receipts.json"
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        receipt_path.chmod(0o600)

        before = self.payload(self.run_cli("status", "--json"))["data"]
        self.assertEqual(set(before["managed_profile_state"].values()), {"drift"})
        updated = self.preview_apply("update")
        self.assertEqual(updated["data"]["change_count"], 4)
        backups = sorted((self.state / "backups").glob("*.bak"))
        self.assertEqual(len(backups), 4)
        self.assertEqual({path.read_bytes() for path in backups}, set(previous.values()))
        status = self.payload(self.run_cli("status", "--json"))["data"]
        self.assertEqual(set(status["managed_profile_state"].values()), {"managed"})
        self.assertEqual(status["latest_receipt"]["template_version"], "0.3.0")

        self.preview_apply("uninstall")
        self.assertTrue(all(not (self.agents / name).exists() for name in PROFILE_NAMES))
        self.assertEqual(len(backups), 4)


if __name__ == "__main__":
    unittest.main()
