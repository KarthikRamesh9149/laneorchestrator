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
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        action_uses = ACTION_USE.findall(text)
        self.assertGreaterEqual(len(action_uses), 7)
        self.assertTrue(all(re.search(r"@[0-9a-f]{40}$", action) for action in action_uses))
        for path in workflows:
            workflow = path.read_text(encoding="utf-8")
            self.assertRegex(workflow, r"@[0-9a-f]{40}\s+# v[0-9]", path.name)
            self.assertIn("timeout-minutes:", workflow, path.name)
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("macos-latest", ci)
        self.assertIn("windows-latest", ci)
        self.assertIn('python: ["3.9", "3.14"]', ci)
        self.assertIn("windows-control-plane", ci)
        windows_partition = ci.split("windows-control-plane:", 1)[1].split("release-evidence:", 1)[0]
        self.assertNotIn("sh scripts/validate.sh", windows_partition)
        for posix_suite in ("tests.test_release_tools", "tests.test_security_primitives", "tests.test_profiles", "tests.test_installer"):
            self.assertNotIn(posix_suite, windows_partition)
        self.assertNotIn("tests.test_benchmark", windows_partition)
        self.assertIn("steps.release-assets.outputs.tar", ci)
        self.assertNotIn("laneorchestrator-0.2.0.tar.gz", ci)
        self.assertIn("permissions:\n  contents: read", ci)
        self.assertIn("persist-credentials: false", ci)
        self.assertIn("timeout-minutes: 10", ci)
        security = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
        self.assertIn("actions: read", security)
        self.assertIn("contents: read", security)
        self.assertIn("security-events: write", security)
        self.assertIn("output: ${{ runner.temp }}/codeql-sarif", security)
        self.assertIn("upload: ${{ github.event.repository.private && 'never' || 'always' }}", security)
        self.assertIn("- name: Require SARIF from successful private analysis", security)
        self.assertIn("if: ${{ !cancelled() && github.event.repository.private }}", security)
        self.assertIn("if: ${{ success() && github.event.repository.private }}", security)
        self.assertIn("if-no-files-found: warn", security)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1", security)

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
