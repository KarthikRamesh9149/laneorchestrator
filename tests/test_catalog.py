from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "laneorchestrator" / "scripts" / "catalog.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CatalogTests(unittest.TestCase):
    def test_ranks_direct_match_and_excludes_vendor_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            skills, agents = fixture / "skills", fixture / "agents"
            write(skills / "react-accessibility" / "SKILL.md", "---\nname: react-accessibility\ndescription: Review React UI for keyboard and screen-reader accessibility.\n---\n")
            write(skills / "zoom-oauth" / "SKILL.md", "---\nname: zoom-oauth\ndescription: Configure Zoom OAuth credentials and refresh tokens.\n---\n")
            write(skills / "database" / "SKILL.md", "---\nname: database\ndescription: Design and migrate relational databases.\n---\n")
            write(agents / "accessibility-tester.toml", 'name = "accessibility-tester"\ndescription = "Audit keyboard and screen-reader behavior in UI changes."\nmodel = "gpt-5.6-terra"\n')
            result = subprocess.run(["python3", str(SCRIPT), "--query", "fix React accessibility", "--cwd", str(fixture), "--no-default-roots", "--skills-root", str(skills), "--agents-root", str(agents)], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
        self.assertEqual(payload["skills"][0]["name"], "react-accessibility")
        self.assertEqual(payload["agents"][0]["name"], "accessibility-tester")
        self.assertNotIn("zoom-oauth", [item["name"] for item in payload["skills"]])

    def test_rejects_generic_review_when_domain_terms_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            skills = fixture / "skills"
            write(skills / "generic-review" / "SKILL.md", "---\nname: generic-review\ndescription: Review work before it ships.\n---\n")
            write(skills / "auth-migration" / "SKILL.md", "---\nname: auth-migration\ndescription: Plan OAuth authentication migrations and backwards compatibility.\n---\n")
            result = subprocess.run(["python3", str(SCRIPT), "--query", "OAuth migration review", "--cwd", str(fixture), "--no-default-roots", "--skills-root", str(skills)], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
        self.assertEqual([item["name"] for item in payload["skills"]], ["auth-migration"])

    def test_requires_strong_match_for_complex_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            skills = fixture / "skills"
            write(skills / "generic-auth" / "SKILL.md", "---\nname: generic-auth\ndescription: Authentication guidance.\n---\n")
            write(skills / "oauth-migration" / "SKILL.md", "---\nname: oauth-migration\ndescription: Migrate OAuth authentication and maintain compatibility.\n---\n")
            result = subprocess.run(["python3", str(SCRIPT), "--query", "OAuth authentication migration review", "--cwd", str(fixture), "--no-default-roots", "--skills-root", str(skills)], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
        self.assertEqual([item["name"] for item in payload["skills"]], ["oauth-migration"])

    def test_reports_lane_agents_separately_from_specialists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            agents = fixture / "agents"
            for name in ("laneorchestrator-router", "laneorchestrator-terra-executor", "laneorchestrator-sol-reviewer"):
                write(agents / f"{name}.toml", f'name = "{name}"\ndescription = "Control plane role."\nmodel = "gpt-5.6-sol"\n')
            result = subprocess.run(["python3", str(SCRIPT), "--query", "OAuth authentication migration", "--cwd", str(fixture), "--no-default-roots", "--agents-root", str(agents), "--unscoped-high-risk"], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
        self.assertEqual([item["name"] for item in payload["lane_agents"]], ["laneorchestrator-router", "laneorchestrator-sol-reviewer", "laneorchestrator-terra-executor"])
        self.assertEqual(payload["agents"], [])
        self.assertEqual(payload["skills"], [])
        self.assertTrue(all(item["score"] is None and item["role"] == "required-lane" for item in payload["lane_agents"]))


if __name__ == "__main__":
    unittest.main()
