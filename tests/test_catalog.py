#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "laneorchestrator" / "scripts" / "catalog.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        skills, agents = fixture / "skills", fixture / "agents"
        write(skills / "react-accessibility" / "SKILL.md", "---\nname: react-accessibility\ndescription: Review React UI for keyboard and screen-reader accessibility.\n---\n")
        write(skills / "database" / "SKILL.md", "---\nname: database\ndescription: Design and migrate relational databases.\n---\n")
        write(agents / "accessibility-tester.toml", 'name = "accessibility-tester"\ndescription = "Audit keyboard and screen-reader behavior in UI changes."\nmodel = "gpt-5.6-terra"\n')
        result = subprocess.run(["python3", str(SCRIPT), "--query", "fix React accessibility", "--cwd", str(fixture), "--no-default-roots", "--skills-root", str(skills), "--agents-root", str(agents)], check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        assert payload["skills"][0]["name"] == "react-accessibility", payload
        assert payload["agents"][0]["name"] == "accessibility-tester", payload
        assert payload["counts"]["skills"] >= 2, payload
    print("catalog fixture passed")


if __name__ == "__main__":
    main()
