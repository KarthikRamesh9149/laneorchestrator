from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s]+)", re.MULTILINE)


class RepositoryTests(unittest.TestCase):
    def test_manifest_has_release_metadata(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        public_manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "laneorchestrator")
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual(public_manifest["name"], manifest["name"])
        self.assertEqual(public_manifest["version"], manifest["version"])
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["repository"], "https://github.com/KarthikRamesh9149/laneorchestrator")
        self.assertEqual(manifest["skills"], "./skills/")

    def test_all_relative_markdown_links_resolve(self) -> None:
        failures: list[str] = []
        for document in sorted(ROOT.rglob("*.md")):
            if ".superpowers" in document.parts:
                continue
            text = document.read_text(encoding="utf-8")
            for target in MARKDOWN_LINK.findall(text):
                clean = target.strip().split("#", 1)[0]
                if not clean or "://" in clean or clean.startswith("mailto:"):
                    continue
                if not (document.parent / clean).resolve().exists():
                    failures.append(f"{document.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [])

    def test_ci_actions_are_immutable_and_matrix_covers_supported_platforms(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        action_uses = ACTION_USE.findall(workflow)
        self.assertGreaterEqual(len(action_uses), 2)
        self.assertTrue(all(re.search(r"@[0-9a-f]{40}$", action) for action in action_uses))
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertIn('python: ["3.9", "3.13"]', workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("timeout-minutes: 10", workflow)

    def test_validation_entry_points_are_executable(self) -> None:
        for relative in ("scripts/install-agents.sh", "scripts/install_agents.py", "scripts/validate.sh"):
            path = ROOT / relative
            self.assertTrue(os.access(path, os.X_OK), relative)

    def test_agent_profiles_are_namespaced_and_unique(self) -> None:
        names: list[str] = []
        for profile in sorted((ROOT / "agents").glob("*.toml")):
            match = re.search(r'^name\s*=\s*"([^"]+)"', profile.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertIsNotNone(match, profile.name)
            names.append(match.group(1))
        self.assertEqual(len(names), 4)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(name.startswith("laneorchestrator-") for name in names))

    def test_high_risk_model_unavailability_fails_closed(self) -> None:
        skill = (ROOT / "skills" / "laneorchestrator" / "SKILL.md").read_text(encoding="utf-8")
        router = (ROOT / "agents" / "laneorchestrator-router.toml").read_text(encoding="utf-8")
        for policy in (skill, router):
            self.assertIn("If Terra", policy)
            self.assertIn("If Sol", policy)
            self.assertIn("pause", policy)


if __name__ == "__main__":
    unittest.main()
