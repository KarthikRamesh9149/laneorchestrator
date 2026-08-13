from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as etree
from pathlib import Path
from typing import Iterable, List, Tuple

from laneorchestrator import __version__
ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?(?:\[[^]]*\])\(([^)]+)\)")
SHELL_FENCE = re.compile(r"```(?:sh|bash|shell)\n(.*?)```", re.DOTALL)
INLINE_CODE = re.compile(r"`([^`\n]+)`")
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
    "docs/assets/laneorchestrator-demo.gif",
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
    "python3 -m laneorchestrator setup",
    "python3 -m laneorchestrator setup --json",
    'python3 -m laneorchestrator route --json --objective "Fix a README typo" --known-area --acceptance-criteria --files 1 --risk-assessment low',
    "python3 -m laneorchestrator voltagent inventory --json",
    "python3 -m laneorchestrator voltagent install preview --json",
    "python3 -m laneorchestrator voltagent install apply --token <bound-token> --approval approve:<approval-digest> --json",
    "python3 -m laneorchestrator benchmark --json",
    "python3 -m unittest tests.test_acceptance_100 -v",
    "python3 scripts/healthcheck.py",
    "sh scripts/validate.sh",
)


def public_text_files() -> Iterable[Path]:
    yield ROOT / "README.md"
    yield from sorted(path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts)
    yield from sorted(path for path in (ROOT / "docs" / "assets").glob("*") if path.suffix != ".gif")
    yield from sorted((ROOT / "docs" / "transcripts").glob("*"))
    yield ROOT / "CHANGELOG.md"
    yield ROOT / "CONTRIBUTING.md"
    yield ROOT / "RELEASING.md"
    yield ROOT / "SECURITY.md"
    yield ROOT / "SUPPORT.md"
    yield from sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))


def operational_markdown() -> Iterable[Path]:
    yield ROOT / "README.md"
    yield ROOT / "CONTRIBUTING.md"
    yield ROOT / "SUPPORT.md"
    yield ROOT / "RELEASING.md"
    yield ROOT / "benchmarks" / "README.md"
    yield from sorted(path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts)


def documented_local_commands() -> Iterable[str]:
    def command_lines(text: str) -> Iterable[str]:
        for line in text.splitlines():
            command = line.strip()
            if command.startswith("python3 ") or command.startswith("sh "):
                yield command

    for document in operational_markdown():
        text = document.read_text(encoding="utf-8")
        for block in SHELL_FENCE.findall(text):
            yield from command_lines(block)
        for command in INLINE_CODE.findall(text):
            if command == "python3 -m laneorchestrator":
                continue
            yield from command_lines(command)


class DocumentationTests(unittest.TestCase):
    def test_required_public_surface_exists(self) -> None:
        self.assertEqual([name for name in REQUIRED if not (ROOT / name).is_file()], [])

    def test_readme_first_screen_has_a_clear_install_and_standalone_message(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        first_screen = "\n".join(readme.splitlines()[:100])
        self.assertIn("A risk-aware control plane for Codex—with 172 bundled specialist agents.", first_screen)
        self.assertIn("analyzes your prompt and repository context", first_screen)
        self.assertIn("GPT‑5.6 Luna, Terra, or Sol", first_screen)
        self.assertIn("172 bundled specialist agents", first_screen)
        self.assertIn("Sol plans → Terra + specialist → Sol reviews", first_screen)
        self.assertIn(
            "codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref v0.2.3",
            first_screen,
        )
        self.assertNotIn("--ref main", first_screen)
        self.assertIn("codex plugin add laneorchestrator@laneorchestrator", first_screen)
        self.assertIn("$laneorchestrator", first_screen)
        self.assertIn("No separate Volt download is required.", first_screen)
        self.assertIn("172 namespaced profiles", first_screen)
        self.assertIn("Activate the bundled specialists", first_screen)
        self.assertIn("voltagent inventory --json", first_screen)
        self.assertIn("Luna executes", first_screen)
        self.assertIn("Terra + specialist execute", first_screen)
        self.assertIn("preview and waits for your explicit approval", first_screen)
        self.assertIn("docs/assets/demo.cast", first_screen)
        self.assertEqual(first_screen.count("[!["), 4)
        self.assertNotRegex(readme, LOCAL_PATH)

    def test_readme_explains_lanes_features_and_trust_boundaries(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in ("## What it does", "## The three lanes", "## Trust, safety, and release evidence", "## FAQ"):
            self.assertIn(heading, readme)
        self.assertIn("One known, low-risk file", readme)
        self.assertIn("Normal features, integrations, multi-file work, or uncertainty", readme)
        self.assertIn("Security, credentials, migrations, persistent data, public contracts", readme)
        self.assertIn("Metadata can influence a shortlist", (ROOT / "docs" / "concepts.md").read_text(encoding="utf-8"))
        self.assertIn("artifact attestations", readme)
        self.assertIn("not a promise that every environment or future change is risk-free", readme)

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
        self.assertEqual(sorted(set(documented_local_commands())), sorted(DOCUMENTED_LOCAL_COMMANDS))
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            environment = dict(os.environ, CODEX_HOME=str(home), PATH="")
            preview = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "preview", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_data = json.loads(preview.stdout)["data"]
            token = preview_data["token"]
            approval = "approve:" + str(preview_data["approval_digest"])
            apply = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "apply", "--token", token, "--approval", approval, "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            volt_preview = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "voltagent", "install", "preview", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(volt_preview.returncode, 0, volt_preview.stderr)
            volt_preview_data = json.loads(volt_preview.stdout)["data"]
            volt_token = volt_preview_data["token"]
            volt_approval = "approve:" + str(volt_preview_data["approval_digest"])
            for command in DOCUMENTED_LOCAL_COMMANDS:
                if command == "sh scripts/validate.sh":
                    syntax = subprocess.run(
                        ["sh", "-n", "scripts/validate.sh"], cwd=ROOT, text=True, capture_output=True, check=False
                    )
                    self.assertEqual(syntax.returncode, 0, syntax.stderr)
                    self.assertIn("unittest discover", (ROOT / "scripts/validate.sh").read_text(encoding="utf-8"))
                    continue
                if command == "python3 -m laneorchestrator setup":
                    # The documented interactive command intentionally requires a real TTY;
                    # this contract test verifies its presence without attempting mutation.
                    continue
                arguments = shlex.split(command)
                if arguments[0] == "python3":
                    arguments[0] = sys.executable
                if command.startswith("python3 -m laneorchestrator voltagent install apply"):
                    arguments = [
                        sys.executable, "-m", "laneorchestrator", "voltagent", "install", "apply",
                        "--token", volt_token, "--approval", volt_approval, "--json",
                    ]
                result = subprocess.run(
                    arguments, cwd=ROOT, env=environment, text=True, capture_output=True, check=False
                )
                self.assertNotIn("Traceback", result.stderr, command)
                if command == "python3 -m laneorchestrator --help":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage: laneorchestrator", result.stdout)
                    continue
                if command == "python3 scripts/healthcheck.py":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("health check passed", result.stdout.lower())
                    continue
                if command == "python3 -m unittest tests.test_acceptance_100 -v":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("Ran 100 tests", result.stderr)
                    self.assertIn("OK", result.stderr)
                    continue
                payload = json.loads(result.stdout)
                if command == "python3 -m laneorchestrator setup --json":
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(payload["errors"][0]["code"], "SETUP_INTERACTIVE_REQUIRED")
                    self.assertIn("interactive_command", payload["data"])
                    continue
                self.assertEqual(payload["schema_version"], 1, command)
                self.assertEqual(payload["command"], command.split()[3] if " -m " in command else "", command)
                if command == "python3 -m laneorchestrator doctor --json":
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse(payload["ok"])
                    self.assertEqual(payload["errors"], [])
                    failed = [item for item in payload["diagnostics"] if item["level"] == "FAIL"]
                    self.assertEqual(len(failed), 1)
                    self.assertEqual(failed[0]["code"], "CODEX_CLI")
                    self.assertEqual(failed[0]["evidence"].get("probe"), "missing")
                else:
                    self.assertEqual(result.returncode, 0, "{0}\n{1}".format(command, result.stderr))
                    self.assertTrue(payload["ok"], command)

    def test_missing_codex_produces_only_the_documented_doctor_degradation(self) -> None:
        getting_started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
        self.assertIn("CODEX_CLI", getting_started)
        self.assertIn("installed `$laneorchestrator` workflow stops", getting_started)
        self.assertIn("may still compute a local decision", getting_started)
        self.assertIn("cannot prove host readiness", getting_started)
        self.assertIn("cannot execute or authorize", getting_started)
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            environment = dict(os.environ, CODEX_HOME=str(home), PATH="")
            preview = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "preview", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_data = json.loads(preview.stdout)["data"]
            token = preview_data["token"]
            approval = "approve:" + str(preview_data["approval_digest"])
            apply = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "apply", "--token", token, "--approval", approval, "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            doctor = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "doctor", "--json"],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(doctor.returncode, 1)
            payload = json.loads(doctor.stdout)
            self.assertEqual(payload["command"], "doctor")
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["errors"], [])
            failed = [item for item in payload["diagnostics"] if item["level"] == "FAIL"]
            self.assertEqual([(item["code"], item["evidence"].get("probe")) for item in failed], [("CODEX_CLI", "missing")])
            route = subprocess.run(
                [
                    sys.executable, "-m", "laneorchestrator", "route", "--json", "--objective", "Fix a README typo",
                    "--known-area", "--acceptance-criteria", "--files", "1", "--risk-assessment", "low",
                ],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False
            )
            self.assertEqual(route.returncode, 0, route.stderr)
            route_payload = json.loads(route.stdout)
            self.assertTrue(route_payload["ok"])
            self.assertEqual(route_payload["errors"], [])
            self.assertEqual(route_payload["data"]["route"]["lane"], "luna")

    def test_installed_users_use_the_skill_from_an_arbitrary_workspace(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        getting_started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
        commands = (ROOT / "docs/commands.md").read_text(encoding="utf-8")
        compatibility = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
        self.assertIn("arbitrary workspace", readme)
        self.assertIn("$laneorchestrator", getting_started)
        for text in (getting_started, commands, compatibility):
            self.assertIn("source checkout", text)
            self.assertIn("resolved installed plugin root", text)

    def test_update_and_removal_docs_preserve_pinned_release_and_managed_state_boundaries(self) -> None:
        getting_started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
        compatibility = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
        self.assertIn("does **not** silently move a pinned installation", getting_started)
        self.assertIn("codex plugin remove laneorchestrator@laneorchestrator", getting_started)
        self.assertIn("codex plugin marketplace remove laneorchestrator", getting_started)
        self.assertIn("profiles uninstall preview", getting_started)
        self.assertIn("does not remove LaneOrchestrator-managed profiles or configuration", getting_started)
        self.assertIn("completed that matrix successfully on 2026-08-12", compatibility)
        self.assertNotIn("has not yet supplied live run evidence", compatibility)

    @unittest.skipUnless(os.name == "posix", "symlink fixture requires POSIX")
    def test_codex_home_docs_match_symlinked_absolute_failure(self) -> None:
        documentation = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("docs/configuration.md", "docs/compatibility.md", "docs/troubleshooting.md")
        ).lower()
        for phrase in ("absolute", "resolved", "user-owned", "non-symlink"):
            self.assertIn(phrase, documentation)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(outside, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable, "-m", "laneorchestrator", "configure", "preview", "--set",
                    "router.reasoning_effort=ultra", "--json",
                ],
                cwd=ROOT, env=dict(os.environ, CODEX_HOME=str(linked)), text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "CONFIG_INVALID")
            self.assertFalse((outside / "laneorchestrator").exists())

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
            preview_data = json.loads(preview.stdout)["data"]
            token = preview_data["token"]
            approval = "approve:" + str(preview_data["approval_digest"])
            apply = subprocess.run(
                [sys.executable, "-m", "laneorchestrator", "profiles", "install", "apply", "--token", token, "--approval", approval, "--json"],
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
        root = etree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIsNone(UNSAFE_SVG.search(svg))
        cast = (ROOT / "docs/assets/demo.cast").read_text(encoding="utf-8")
        cast_lines = cast.splitlines()
        self.assertEqual(json.loads(cast_lines[0])["version"], 2)
        events = [json.loads(line) for line in cast_lines[1:]]
        self.assertEqual(events[-1][0], 90.0)
        cast_text = "\n".join(str(event[2]) for event in events)
        transcript = (ROOT / "docs/transcripts/quickstart.txt").read_text(encoding="utf-8")
        for marker in ("doctor", "preview", "Route card"):
            self.assertIn(marker.lower(), cast_text.lower())
            self.assertIn(marker.lower(), transcript.lower())
        for path in (ROOT / "docs/assets/demo.cast", ROOT / "docs/transcripts/quickstart.txt"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\x1b", text)
            self.assertNotRegex(text, LOCAL_PATH)

    def test_readme_demo_is_animated_bounded_and_reproducible(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        relative = "docs/assets/laneorchestrator-demo.gif"
        self.assertIn(relative, readme)
        data = (ROOT / relative).read_bytes()
        self.assertLessEqual(len(data), 1_000_000)
        self.assertEqual(data[:6], b"GIF89a")
        self.assertEqual(int.from_bytes(data[6:8], "little"), 1200)
        self.assertEqual(int.from_bytes(data[8:10], "little"), 675)
        graphic_controls = [index for index in range(len(data)) if data.startswith(b"\x21\xf9\x04", index)]
        self.assertGreaterEqual(len(graphic_controls), 20)
        duration_centiseconds = sum(
            int.from_bytes(data[index + 4 : index + 6], "little") for index in graphic_controls
        )
        self.assertEqual(duration_centiseconds, 2_000)
        renderer = ROOT / "scripts" / "render_demo_gif.py"
        self.assertTrue(renderer.is_file())
        self.assertIn("Deterministic walkthrough", renderer.read_text(encoding="utf-8"))

    def test_issue_forms_and_security_policy_route_sensitive_reports_privately(self) -> None:
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("private vulnerability reporting", security)
        for path in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            self.assertIn("secrets", text.lower(), path.name)
            self.assertIn("SECURITY.md", text, path.name)


if __name__ == "__main__":
    unittest.main()
