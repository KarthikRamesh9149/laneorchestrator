from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory)
    except ValueError:
        return False
    return True


def _contains_plugin(entries: object) -> bool:
    return isinstance(entries, list) and any(
        isinstance(entry, dict)
        and entry.get("name", entry.get("pluginId")) == "laneorchestrator"
        for entry in entries
    )


class MarketplaceSmokeTests(unittest.TestCase):
    def test_local_marketplace_lifecycle_uses_an_isolated_codex_home(self) -> None:
        codex = shutil.which("codex")
        if codex is None:
            self.skipTest("codex is not installed")

        with tempfile.TemporaryDirectory(prefix="laneorchestrator-codex-home-") as temporary:
            codex_home = (Path(temporary) / "home" / ".codex").resolve()
            codex_home.mkdir(parents=True)
            unrelated_workspace = Path(temporary) / "unrelated-workspace"
            unrelated_workspace.mkdir()
            temporary_dir = (Path(temporary) / "tmp").resolve()
            temporary_dir.mkdir()
            xdg_paths = {
                "XDG_CONFIG_HOME": Path(temporary) / "home" / ".config",
                "XDG_CACHE_HOME": Path(temporary) / "home" / ".cache",
                "XDG_DATA_HOME": Path(temporary) / "home" / ".local" / "share",
                "XDG_STATE_HOME": Path(temporary) / "home" / ".local" / "state",
            }
            for path in xdg_paths.values():
                path.mkdir(parents=True)
            self.assertFalse(codex_home.is_symlink())
            environment = {
                "CODEX_HOME": str(codex_home),
                "HOME": str(codex_home.parent),
                "LANG": os.environ.get("LANG", "C"),
                "PATH": os.defpath,
                "TMPDIR": str(temporary_dir),
            }
            environment.update({name: str(path) for name, path in xdg_paths.items()})

            def run(*arguments: str) -> subprocess.CompletedProcess[str]:
                completed = subprocess.run(
                    [codex, *arguments],
                    check=False,
                    cwd=unrelated_workspace,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    "\n".join((completed.stdout[-4000:], completed.stderr[-4000:])),
                )
                return completed

            run("plugin", "marketplace", "add", str(ROOT), "--json")
            listed = run("plugin", "list", "--available", "--json")
            self.assertTrue(_contains_plugin(json.loads(listed.stdout)["available"]))
            installed_result = json.loads(
                run("plugin", "add", "laneorchestrator@laneorchestrator", "--json").stdout
            )
            installed_path = Path(installed_result["installedPath"]).resolve()
            self.assertTrue(_is_within(installed_path, codex_home), installed_path)
            self.assertTrue(installed_path.is_dir())
            self.assertTrue((codex_home / "config.toml").is_file())
            self.assertIn("laneorchestrator", (codex_home / "config.toml").read_text(encoding="utf-8"))
            installed = run("plugin", "list", "--json")
            self.assertTrue(_contains_plugin(json.loads(installed.stdout)["installed"]))
            self.assertNotEqual(unrelated_workspace.resolve(), installed_path)
            unrelated_module = subprocess.run(
                ["python3", "-m", "laneorchestrator", "doctor", "--json"],
                check=False,
                cwd=unrelated_workspace,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertNotEqual(unrelated_module.returncode, 0)
            self.assertIn("No module named laneorchestrator", unrelated_module.stderr)
            doctor = subprocess.run(
                ["python3", "-m", "laneorchestrator", "doctor", "--json"],
                check=False,
                cwd=installed_path,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertNotIn("No module named laneorchestrator", doctor.stderr)
            doctor_payload = json.loads(doctor.stdout)
            self.assertEqual(doctor_payload["command"], "doctor")
            run("plugin", "remove", "laneorchestrator@laneorchestrator", "--json")
            removed = run("plugin", "list", "--json")
            self.assertFalse(_contains_plugin(json.loads(removed.stdout)["installed"]))
            self.assertFalse(installed_path.exists())
            run("plugin", "marketplace", "remove", "laneorchestrator", "--json")
            marketplaces = run("plugin", "marketplace", "list", "--json")
            self.assertNotIn("laneorchestrator", marketplaces.stdout)
            self.assertNotIn("laneorchestrator", (codex_home / "config.toml").read_text(encoding="utf-8"))

            temporary_root = Path(temporary).resolve()
            for created in temporary_root.rglob("*"):
                self.assertFalse(created.is_symlink(), created)
                self.assertTrue(_is_within(created, temporary_root), created)


if __name__ == "__main__":
    unittest.main()
