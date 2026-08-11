from __future__ import annotations

import json
import re
import unittest
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "laneorchestrator"
PLUGIN_VERSION = "0.2.1"
SKILL_COMMANDS = (
    "codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref v0.2.1",
    "codex plugin add laneorchestrator@laneorchestrator",
)
README_COMMANDS = (
    "codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref v0.2.1",
    "codex plugin add laneorchestrator@laneorchestrator",
)


def _repository_path(value: object) -> bool:
    """Return whether a manifest component path stays inside this repository."""
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if value.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", value):
        return False
    parts = PurePosixPath(value).parts
    if any(part in (".", "..") for part in parts):
        return False
    candidate = (ROOT / value).resolve(strict=False)
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return False
    return not (ROOT / value).is_symlink()


class PluginManifestTests(unittest.TestCase):
    def load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_marketplace_resolves_one_repository_local_plugin(self) -> None:
        marketplace = self.load_json(".agents/plugins/marketplace.json")
        self.assertEqual(marketplace["name"], PLUGIN_NAME)
        self.assertEqual(len(marketplace["plugins"]), 1)
        plugin = marketplace["plugins"][0]
        self.assertEqual(plugin["name"], PLUGIN_NAME)
        self.assertEqual(plugin["source"], {"path": ".", "source": "local"})
        manifest = self.load_json("plugin.json")
        self.assertEqual(manifest["version"], PLUGIN_VERSION)

    def test_manifests_have_matching_release_identity_and_schema(self) -> None:
        public = self.load_json("plugin.json")
        compatibility = self.load_json(".codex-plugin/plugin.json")
        self.assertEqual(public["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(public["name"], PLUGIN_NAME)
        self.assertEqual(compatibility["name"], PLUGIN_NAME)
        self.assertEqual(public["version"], PLUGIN_VERSION)
        self.assertEqual(compatibility["version"], PLUGIN_VERSION)
        self.assertEqual(public["repository"], "https://github.com/KarthikRamesh9149/laneorchestrator")
        self.assertEqual(compatibility["repository"], public["repository"])

    def test_component_declarations_are_unique_and_contained(self) -> None:
        manifest = self.load_json(".codex-plugin/plugin.json")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue(_repository_path(manifest["skills"]))
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        agents = sorted((ROOT / "skills").glob("*/agents/openai.yaml"))
        self.assertEqual([path.parent.name for path in skills], [PLUGIN_NAME])
        self.assertEqual([path.parent.parent.name for path in agents], [PLUGIN_NAME])
        self.assertEqual(len(skills), len({path.resolve() for path in skills}))
        self.assertEqual(len(agents), len({path.resolve() for path in agents}))
        self.assertTrue(all(not path.is_symlink() for path in (*skills, *agents)))

    def test_declared_paths_reject_escape_and_platform_specific_forms(self) -> None:
        for invalid in ("", "/tmp/plugin", "//server/share", "C:/plugin", "C:\\\\plugin", "..", "../skills", "skills/../agents", "skills\\agents"):
            with self.subTest(path=invalid):
                self.assertFalse(_repository_path(invalid))
        self.assertTrue(_repository_path("skills/laneorchestrator"))

    def test_no_manifest_declares_an_absolute_or_external_component_path(self) -> None:
        for relative in ("plugin.json", ".codex-plugin/plugin.json"):
            manifest = self.load_json(relative)
            for key in ("skills", "apps", "mcpServers", "hooks"):
                if key in manifest and isinstance(manifest[key], str):
                    with self.subTest(manifest=relative, key=key):
                        self.assertTrue(_repository_path(manifest[key]))
        marketplace = self.load_json(".agents/plugins/marketplace.json")
        source = marketplace["plugins"][0]["source"]
        self.assertEqual(source["source"], "local")
        self.assertEqual(source["path"], ".")

    def test_skill_documents_exact_public_commands_and_safe_first_run(self) -> None:
        skill = (ROOT / "skills/laneorchestrator/SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^codex plugin .+$", skill, re.MULTILINE), list(SKILL_COMMANDS))
        self.assertLess(skill.index("python3 -m laneorchestrator doctor --json"), skill.index("python3 -m laneorchestrator profiles install preview --json"))
        self.assertIn("profiles install apply --token <bound-token> --approval approve:<approval-digest> --json", skill)
        self.assertIn("never apply", skill.lower())
        self.assertIn("Third-party agent packs are optional", skill)
        self.assertIn("missing Terra", skill)
        self.assertIn("required Sol", skill)
        self.assertIn("ancestor of this `SKILL.md`", skill)
        self.assertIn("plugin root as the working directory", skill)
        self.assertIn("private local planning state", skill)
        self.assertIn("does not apply profile or configuration changes", skill)

    def test_readme_uses_only_the_supported_marketplace_and_token_flow(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(README_COMMANDS[0], readme)
        self.assertIn(README_COMMANDS[1], readme)
        self.assertNotIn("--ref main", readme)
        self.assertNotIn("sh scripts/install-agents.sh", readme)
        self.assertIn("doctor", readme)
        self.assertIn("preview", readme)
        self.assertIn("bound token", readme)
        self.assertIn("Plugin removal", readme)


if __name__ == "__main__":
    unittest.main()
