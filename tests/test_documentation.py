from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable, List, Tuple

from laneorchestrator import __version__
ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?(?:\[[^]]*\])\(([^)]+)\)")
SHELL_FENCE = re.compile(r"```(?:sh|bash|shell)\n(.*?)```", re.DOTALL)
LOCAL_PATH = re.compile(r"/(?:Users|home)/|[A-Z]:\\\\Users\\\\")
SUPERLATIVE = re.compile(r"\b(?:best|fastest|world-class|unbeatable|guaranteed)\b", re.IGNORECASE)
SECRET = re.compile(r"(?:Bearer\s+\S+|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|AKIA[0-9A-Z]{16})")
UNSAFE_SVG = re.compile(
    r"<script|<foreignObject|\son\w+\s*=|(?:href|src|xlink:href)\s*=\s*[\"'](?:https?:|//|data:|javascript:)",
    re.IGNORECASE,
)

REQUIRED = (
    "README.md",
    "docs/getting-started.md",
    "docs/concepts.md",
    "docs/configuration.md",
    "docs/commands.md",
    "docs/examples/small-change.md",
    "docs/examples/normal-feature.md",
    "docs/examples/high-risk-change.md",
    "docs/threat-model.md",
    "docs/benchmarks.md",
    "docs/troubleshooting.md",
    "docs/compatibility.md",
    "docs/roadmap.md",
    "docs/assets/demo.cast",
    "docs/assets/architecture.mmd",
    "docs/assets/social-preview.svg",
    "docs/transcripts/quickstart.txt",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/pull_request_template.md",
)

DOCUMENTED_LOCAL_COMMANDS = (
    "python3 -m laneorchestrator --help",
    "python3 -m laneorchestrator version --json",
    "python3 -m laneorchestrator doctor --json",
    "python3 -m laneorchestrator status --json",
    'python3 -m laneorchestrator route --json --objective "Fix a README typo" --known-area --acceptance-criteria --files 1 --risk-assessment low',
)


def public_text_files() -> Iterable[Path]:
    yield ROOT / "README.md"
    yield from sorted(path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts)
    yield from sorted((ROOT / "docs" / "assets").glob("*"))
    yield from sorted((ROOT / "docs" / "transcripts").glob("*"))
    yield ROOT / "CHANGELOG.md"
    yield ROOT / "CONTRIBUTING.md"
    yield ROOT / "RELEASING.md"
    yield ROOT / "SECURITY.md"
    yield ROOT / "SUPPORT.md"
    yield from sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))


class DocumentationTests(unittest.TestCase):
    def test_required_public_surface_exists(self) -> None:
        self.assertEqual([name for name in REQUIRED if not (ROOT / name).is_file()], [])

    def test_readme_first_screen_has_install_and_standalone_message(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        first_screen = "\n".join(readme.splitlines()[:80])
        self.assertIn("Secure, evidence-driven model and agent routing for Codex.", first_screen)
        self.assertIn("codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref main", first_screen)
        self.assertIn("codex plugin add laneorchestrator@laneorchestrator", first_screen)
        self.assertIn("$laneorchestrator", first_screen)
        self.assertIn("Third-party agent packs are optional", first_screen)
        self.assertIn("docs/assets/demo.cast", first_screen)
        self.assertEqual(first_screen.count("[!["), 4)
        self.assertNotRegex(readme, LOCAL_PATH)

    def test_relative_markdown_links_resolve(self) -> None:
        failures: List[str] = []
        documents = [ROOT / "README.md"] + sorted(
            path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts
        )
        for document in documents:
            for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
                clean = target.strip().split("#", 1)[0]
                if not clean or "://" in clean or clean.startswith("mailto:"):
                    continue
                if not (document.parent / clean).resolve().exists():
                    failures.append("{0} -> {1}".format(document.relative_to(ROOT), target))
        self.assertEqual(failures, [])

    def test_documented_local_commands_are_allowlisted_and_exercised(self) -> None:
        commands: List[str] = []
        for document in [ROOT / "README.md"] + sorted(
            path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts
        ):
            for block in SHELL_FENCE.findall(document.read_text(encoding="utf-8")):
                commands.extend(line.strip() for line in block.splitlines() if line.strip().startswith("python3 "))
        self.assertEqual(sorted(set(commands)), sorted(DOCUMENTED_LOCAL_COMMANDS))
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            environment = dict(os.environ, CODEX_HOME=str(home))
            preview = subprocess.run(
                ["python3", "-m", "laneorchestrator", "profiles", "install", "preview", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            token = json.loads(preview.stdout)["data"]["token"]
            apply = subprocess.run(
                ["python3", "-m", "laneorchestrator", "profiles", "install", "apply", "--token", token, "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            for command in DOCUMENTED_LOCAL_COMMANDS:
                result = subprocess.run(
                    shlex.split(command), cwd=ROOT, env=environment, text=True, capture_output=True, check=False
                )
                self.assertEqual(result.returncode, 0, "{0}\n{1}".format(command, result.stderr))

    def test_examples_are_current_route_decisions(self) -> None:
        cases: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
            ("small-change.md", ("Fix a README typo", "1", "low")),
            ("normal-feature.md", ("Add export filtering to a report endpoint", "3", "normal")),
            ("high-risk-change.md", ("Rotate OAuth client credentials", "2", "high")),
        )
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ, CODEX_HOME=str(Path(temporary).resolve()))
            preview = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "preview", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            token = json.loads(preview.stdout)["data"]["token"]
            apply = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "apply", "--token", token, "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            for name, (objective, files, risk) in cases:
                result = subprocess.run(
                    [
                        sys.executable, "-m", "laneorchestrator", "route", "--json", "--objective", objective,
                        "--known-area", "--acceptance-criteria", "--files", files, "--risk-assessment", risk,
                    ],
                    cwd=ROOT, env=environment, text=True, capture_output=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                text = (ROOT / "docs" / "examples" / name).read_text(encoding="utf-8")
                matches = re.findall(r"```json\n(.*?)```", text, re.DOTALL)
                self.assertEqual(len(matches), 1, name)
                self.assertEqual(json.loads(matches[0]), json.loads(result.stdout)["data"]["route"], name)

    def test_versions_and_compatibility_are_in_parity(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(codex_manifest["version"], __version__)
        compatibility = (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8").lower()
        for requirement in ("Python 3.9-3.14", "WSL", "native Windows", "zero runtime dependencies"):
            self.assertIn(requirement.lower(), compatibility)

    def test_public_content_excludes_unverified_claims_and_sensitive_values(self) -> None:
        failures: List[str] = []
        for path in public_text_files():
            text = path.read_text(encoding="utf-8")
            for label, pattern in (("local path", LOCAL_PATH), ("superlative", SUPERLATIVE), ("secret", SECRET)):
                if pattern.search(text):
                    failures.append("{0}: {1}".format(path.relative_to(ROOT), label))
        self.assertEqual(failures, [])

    def test_assets_are_safe_and_transcripts_are_plain_text(self) -> None:
        svg = (ROOT / "docs/assets/social-preview.svg").read_text(encoding="utf-8")
        self.assertTrue(svg.lstrip().startswith("<?xml"))
        self.assertIsNone(UNSAFE_SVG.search(svg))
        for path in (ROOT / "docs/assets/demo.cast", ROOT / "docs/transcripts/quickstart.txt"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\x1b", text)
            self.assertNotRegex(text, LOCAL_PATH)

    def test_issue_forms_and_security_policy_route_sensitive_reports_privately(self) -> None:
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("private vulnerability reporting", security)
        for path in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            self.assertIn("secrets", text.lower(), path.name)
            self.assertIn("SECURITY.md", text, path.name)


if __name__ == "__main__":
    unittest.main()
