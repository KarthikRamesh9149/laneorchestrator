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
    def test_local_marketplace_lifecycle_stays_inside_isolated_codex_home(self) -> None:
        codex = shutil.which("codex")
        if codex is None:
            self.skipTest("codex is not installed")

        with tempfile.TemporaryDirectory(prefix="laneorchestrator-codex-home-") as temporary:
            codex_home = (Path(temporary) / "home" / ".codex").resolve()
            codex_home.mkdir(parents=True)
            temporary_dir = (Path(temporary) / "tmp").resolve()
            temporary_dir.mkdir()
            self.assertFalse(codex_home.is_symlink())
            environment = {
                "CODEX_HOME": str(codex_home),
                "HOME": str(codex_home.parent),
                "LANG": os.environ.get("LANG", "C"),
                "PATH": os.defpath,
                "TMPDIR": str(temporary_dir),
            }

            def run(*arguments: str) -> subprocess.CompletedProcess[str]:
                completed = subprocess.run(
                    [codex, *arguments],
                    check=False,
                    cwd=ROOT,
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
            run("plugin", "add", "laneorchestrator@laneorchestrator", "--json")
            installed = run("plugin", "list", "--json")
            self.assertTrue(_contains_plugin(json.loads(installed.stdout)["installed"]))
            run("plugin", "remove", "laneorchestrator@laneorchestrator", "--json")
            removed = run("plugin", "list", "--json")
            self.assertFalse(_contains_plugin(json.loads(removed.stdout)["installed"]))
            run("plugin", "marketplace", "remove", "laneorchestrator", "--json")
            marketplaces = run("plugin", "marketplace", "list", "--json")
            self.assertNotIn("laneorchestrator", marketplaces.stdout)

            temporary_root = Path(temporary).resolve()
            for created in temporary_root.rglob("*"):
                self.assertFalse(created.is_symlink(), created)
                self.assertTrue(_is_within(created, temporary_root), created)


if __name__ == "__main__":
    unittest.main()
