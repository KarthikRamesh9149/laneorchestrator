#!/usr/bin/env python3
"""Validate release manifest identity and repository-contained components."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, List, Sequence


def _safe_path(value: object, allow_dot: bool = False) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if value == ".":
        return allow_dot
    if value.startswith("./"):
        value = value[2:]
        if not value:
            return False
    if value.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", value):
        return False
    return not any(part in ("", ".", "..") for part in PurePosixPath(value).parts)


def _load(root: Path, relative: str, errors: List[str]) -> Any:
    try:
        return json.loads((root / relative).read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append("{0}: missing".format(relative))
    except (OSError, json.JSONDecodeError):
        errors.append("{0}: invalid JSON".format(relative))
    return None


def check_manifests(root: Path) -> List[str]:
    """Return deterministic release-manifest errors without dereferencing paths."""

    root = Path(root).resolve()
    errors: List[str] = []
    public = _load(root, "plugin.json", errors)
    compatibility = _load(root, ".codex-plugin/plugin.json", errors)
    marketplace = _load(root, ".agents/plugins/marketplace.json", errors)
    if not isinstance(public, dict) or not isinstance(compatibility, dict) or not isinstance(marketplace, dict):
        return sorted(errors)
    version = public.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        errors.append("plugin.json: invalid version")
    if compatibility.get("version") != version:
        errors.append(".codex-plugin/plugin.json: version mismatch")
    if public.get("name") != "laneorchestrator" or compatibility.get("name") != "laneorchestrator":
        errors.append("plugin manifests: invalid name")
    skills = compatibility.get("skills")
    if not _safe_path(skills.rstrip("/") if isinstance(skills, str) else skills):
        errors.append(".codex-plugin/plugin.json: unsafe skills path")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        errors.append(".agents/plugins/marketplace.json: invalid plugins")
    else:
        source = plugins[0].get("source")
        if not isinstance(source, dict) or source.get("source") != "local" or not _safe_path(source.get("path"), allow_dot=True):
            errors.append(".agents/plugins/marketplace.json: unsafe source path")
    return sorted(errors)


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate plugin manifests.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = check_manifests(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
