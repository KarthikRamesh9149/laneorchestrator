#!/usr/bin/env python3
"""Check a LaneOrchestrator checkout for required, internally consistent files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / ".codex-plugin" / "plugin.json",
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / "CHANGELOG.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "RELEASING.md",
    ROOT / "SECURITY.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "security-model.md",
    ROOT / "skills" / "laneorchestrator" / "SKILL.md",
    ROOT / "skills" / "laneorchestrator" / "scripts" / "catalog.py",
    ROOT / "skills" / "laneorchestrator" / "scripts" / "route.py",
    ROOT / "scripts" / "install-agents.sh",
    ROOT / "scripts" / "install_agents.py",
    ROOT / "scripts" / "validate.sh",
]
AGENT_FIELD = re.compile(r'^\s*(name|model|model_reasoning_effort|sandbox_mode)\s*=\s*"(.+)"\s*$', re.MULTILINE)
EXPECTED_MODELS = {
    "laneorchestrator-router.toml": ("gpt-5.6-sol", "read-only"),
    "laneorchestrator-luna-executor.toml": ("gpt-5.6-luna", "workspace-write"),
    "laneorchestrator-terra-executor.toml": ("gpt-5.6-terra", "workspace-write"),
    "laneorchestrator-sol-reviewer.toml": ("gpt-5.6-sol", "read-only"),
}


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")
    try:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        if manifest.get("name") != "laneorchestrator":
            errors.append("plugin manifest name must be laneorchestrator")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
            errors.append("plugin manifest version must use semantic versioning")
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid plugin manifest: {error}")
    for filename, (model, sandbox) in EXPECTED_MODELS.items():
        path = ROOT / "agents" / filename
        fields = dict(AGENT_FIELD.findall(path.read_text(encoding="utf-8"))) if path.is_file() else {}
        if fields.get("model") != model or fields.get("model_reasoning_effort") != "high" or fields.get("sandbox_mode") != sandbox:
            errors.append(f"invalid agent profile: agents/{filename}")
    if errors:
        print("LaneOrchestrator health check failed:", *errors, sep="\n- ")
        return 1
    print("LaneOrchestrator health check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
