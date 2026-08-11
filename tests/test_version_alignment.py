from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import laneorchestrator
from scripts.build_release import build_release, release_version
from scripts.verify_release import verify_release


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"
TAG = "v" + VERSION
TOPICS = (
    "codex", "ai-agents", "agent-routing", "developer-tools", "python", "security", "open-source",
)


class VersionAlignmentTests(unittest.TestCase):
    def test_v020_is_aligned_across_release_surfaces_and_archives(self) -> None:
        self.assertEqual(laneorchestrator.__version__, VERSION)
        self.assertEqual(release_version(ROOT), VERSION)
        for relative in ("plugin.json", ".codex-plugin/plugin.json"):
            manifest = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], VERSION)
            self.assertEqual(tuple(manifest["keywords"]), TOPICS)
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["name"], "laneorchestrator")
        self.assertEqual(marketplace["plugins"][0]["name"], "laneorchestrator")
        self.assertEqual(marketplace["plugins"][0]["source"], {"path": ".", "source": "local"})
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.2.0]", changelog)
        self.assertIn("## [0.2.0] - 2026-08-11", changelog)
        notes = (ROOT / "docs" / "releases" / "v0.2.0.md").read_text(encoding="utf-8")
        self.assertIn(TAG, notes)
        self.assertIn("SHA256SUMS", notes)
        self.assertNotRegex(notes, re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE))
        for banned in ("security perfection", "guaranteed stars", "published", "released", "all platforms"):
            self.assertNotIn(banned, notes.lower())
        with tempfile.TemporaryDirectory() as temporary:
            release = build_release(ROOT, Path(temporary))
            verify_release(Path(temporary), root=ROOT)
            self.assertEqual(release.tar_path.name, "laneorchestrator-{0}.tar.gz".format(VERSION))
            self.assertEqual(release.zip_path.name, "laneorchestrator-{0}.zip".format(VERSION))
            self.assertEqual(release.sums_path.name, "SHA256SUMS")
            self.assertEqual(len(release.sums_path.read_text(encoding="ascii").splitlines()), 2)

    def test_release_configuration_contract_is_exact(self) -> None:
        codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        self.assertEqual(codeowners.strip(), "* @KarthikRamesh9149")
        self.assertNotRegex(codeowners, r"[/@].+\s+.+")
        settings = (ROOT / "docs" / "github-settings.md").read_text(encoding="utf-8")
        self.assertIn("Secure, evidence-driven model and agent routing for Codex.", settings)
        self.assertIn("https://github.com/KarthikRamesh9149/laneorchestrator#readme", settings)
        for topic in TOPICS:
            self.assertIn("`{0}`".format(topic), settings)
        self.assertIn("Discussions: enable", settings)
        self.assertIn("only `main`", settings)
        self.assertIn("inspect the live github api", settings.lower())
        for check in (
            "POSIX Python 3.9 on ubuntu-latest", "POSIX Python 3.14 on ubuntu-latest",
            "POSIX Python 3.9 on macos-latest", "POSIX Python 3.14 on macos-latest",
            "Windows read-only control plane Python 3.9", "Windows read-only control plane Python 3.14",
            "Verify candidate distribution", "private-static-analysis", "public-codeql",
        ):
            self.assertRegex(
                settings,
                r"`{0}` — expected source: `GitHub Actions` app\.".format(re.escape(check)),
            )
        self.assertIn("never `Any source`", settings)
        self.assertIn("force pushes: block", settings)
        self.assertIn("deletions: block", settings)
        self.assertIn("post-apply verification", settings.lower())
        self.assertIn("every required check's `GitHub Actions` expected-source binding", settings)


if __name__ == "__main__":
    unittest.main()
