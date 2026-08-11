#!/usr/bin/env python3
"""Check a LaneOrchestrator checkout for required, internally consistent files."""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from laneorchestrator.security import (
    DuplicateJSONKeyError,
    SecurityError,
    parse_json_object,
    read_regular_nofollow,
)

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
    "laneorchestrator-luna-executor.toml": ("gpt-5.6-luna", "read-only"),
    "laneorchestrator-terra-executor.toml": ("gpt-5.6-terra", "workspace-write"),
    "laneorchestrator-sol-reviewer.toml": ("gpt-5.6-sol", "read-only"),
}
MAX_HEALTHCHECK_FILE_BYTES = 1024 * 1024


def _is_regular_nofollow(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode)


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not _is_regular_nofollow(path):
            errors.append(f"missing required file: {path.relative_to(ROOT)}")
    try:
        manifest = parse_json_object(
            read_regular_nofollow(ROOT / ".codex-plugin" / "plugin.json", MAX_HEALTHCHECK_FILE_BYTES).decode("utf-8")
        )
        if manifest.get("name") != "laneorchestrator":
            errors.append("plugin manifest name must be laneorchestrator")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
            errors.append("plugin manifest version must use semantic versioning")
    except (DuplicateJSONKeyError, OSError, SecurityError, UnicodeError, ValueError) as error:
        errors.append(f"invalid plugin manifest: {error}")
    for filename, (model, sandbox) in EXPECTED_MODELS.items():
        path = ROOT / "agents" / filename
        try:
            content = read_regular_nofollow(path, MAX_HEALTHCHECK_FILE_BYTES).decode("utf-8")
            fields = dict(AGENT_FIELD.findall(content))
        except (OSError, SecurityError, UnicodeError):
            fields = {}
        if fields.get("model") != model or fields.get("model_reasoning_effort") != "high" or fields.get("sandbox_mode") != sandbox:
            errors.append(f"invalid agent profile: agents/{filename}")
    if errors:
        print("LaneOrchestrator health check failed:", *errors, sep="\n- ")
        return 1
    print("LaneOrchestrator health check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
