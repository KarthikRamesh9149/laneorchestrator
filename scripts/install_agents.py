#!/usr/bin/env python3
"""Install LaneOrchestrator agent profiles without following untrusted links."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from typing import Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY_ROOT))

from laneorchestrator.config import ConfigError, load_config
from laneorchestrator.profiles import (
    PROFILE_NAMES,
    ProfileConflict,
    apply_profiles,
    inspect_profiles,
    is_adoptable_profile,
    preview_profiles,
    render_profiles,
)
from laneorchestrator.security import SecurityError, read_regular_nofollow

PROFILE_FIELDS = (
    "name",
    "description",
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
)
FIELD_RE = re.compile(
    r'^\s*(name|description|model|model_reasoning_effort|sandbox_mode)\s*=\s*"(.+)"\s*$',
    re.MULTILINE,
)
MAX_SYSTEM_LINKS = 32
DIRECTORY_MODE = 0o700


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report profile status without changing files.")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".codex" / "agents",
        help=(
            "Agent profile directory (default: ~/.codex/agents). Canonical receipts "
            "use ~/.codex/laneorchestrator for the default target or a private "
            "state directory inside a custom target."
        ),
    )
    return parser.parse_args(argv)


def load_templates(templates_dir: Path) -> list[Path]:
    templates = [templates_dir / name for name in PROFILE_NAMES]
    for path in templates:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise SystemExit(f"Missing required managed agent template {path.name}") from error
        except OSError as error:
            raise SystemExit(f"Could not inspect {path.name}: {error}") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise SystemExit(f"Unsafe agent template {path.name}: expected a regular file")
        try:
            content = read_regular_nofollow(path, 256 * 1024).decode("utf-8")
            fields = dict(FIELD_RE.findall(content))
        except (OSError, SecurityError, UnicodeDecodeError) as error:
            raise SystemExit(f"Could not read {path.name}: {error}") from error
        missing = [field for field in PROFILE_FIELDS if not fields.get(field)]
        if missing:
            raise SystemExit(f"Invalid {path.name}: missing {', '.join(missing)}")
    return templates


def state_root_for_target(target: Path) -> Path:
    """Return the isolated canonical state root used by the legacy adapter."""

    candidate = Path(os.path.abspath(os.fspath(target)))
    default = Path(os.path.abspath(os.fspath(Path.home() / ".codex" / "agents")))
    if candidate == default:
        return default.parent / "laneorchestrator"
    return candidate / ".laneorchestrator-state"


def canonical_system_path(path: Path) -> str:
    """Resolve root-owned platform aliases while rejecting caller-owned links."""
    raw = os.path.abspath(os.fspath(path))
    for _ in range(MAX_SYSTEM_LINKS):
        current = os.path.sep
        components = Path(raw).parts[1:]
        for index, component in enumerate(components):
            current = os.path.join(current, component)
            try:
                details = os.lstat(current)
            except FileNotFoundError:
                return raw
            except OSError as error:
                raise SystemExit(f"Unsafe target directory {path}: {error}") from error
            if not stat.S_ISLNK(details.st_mode):
                continue
            if details.st_uid != 0:
                raise SystemExit(f"Unsafe target directory {path}: symbolic links are not allowed")
            raw = os.path.join(os.path.realpath(current), *components[index + 1 :])
            break
        else:
            return raw
    raise SystemExit(f"Unsafe target directory {path}: too many symbolic links")


def open_target_directory(path: Path, *, create: bool) -> Optional[int]:
    """Open every target component relative to a trusted directory descriptor."""
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, flag) for flag in required_flags):
        raise SystemExit("Secure profile installation requires POSIX O_DIRECTORY and O_NOFOLLOW support")

    raw = canonical_system_path(path)
    if Path(raw) == Path(os.path.sep):
        raise SystemExit("Unsafe target directory /: filesystem root is not an agent profile directory")
    directory_fd = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in Path(raw).parts[1:]:
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                if not create:
                    os.close(directory_fd)
                    return None
                os.mkdir(component, mode=DIRECTORY_MODE, dir_fd=directory_fd)
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except OSError as error:
        os.close(directory_fd)
        raise SystemExit(f"Unsafe target directory {path}: {error.strerror or error}") from error


def _ensure_private_root(
    path: Path, *, create: bool = True, managed_agents: bool = False
) -> Path:
    canonical = Path(canonical_system_path(path))
    descriptor = open_target_directory(canonical, create=create)
    if descriptor is None:
        raise SystemExit(f"Unsafe target directory {path}: directory disappeared")
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        unsafe_mode = mode & (stat.S_IWGRP | stat.S_IWOTH) if managed_agents else mode != DIRECTORY_MODE
        if metadata.st_uid != os.geteuid() or unsafe_mode:
            raise SystemExit(
                f"Unsafe target directory {path}: managed roots must be owned by the current user and not group or other writable"
                if managed_agents
                else f"Unsafe target directory {path}: private state roots require current-user ownership and mode 0700"
            )
    finally:
        os.close(descriptor)
    return canonical


def _read_compatibility_status(
    target: Path, config, *, state_exists: bool
) -> dict[str, str]:
    if state_exists:
        return dict(inspect_profiles(config, target, state_root_for_target(target)))
    rendered = render_profiles(config)
    statuses = {}
    for name in PROFILE_NAMES:
        path = target / name
        try:
            content = read_regular_nofollow(path, 256 * 1024)
        except FileNotFoundError:
            statuses[name] = "missing"
        except (OSError, SecurityError):
            statuses[name] = "conflict"
        else:
            statuses[name] = (
                "unchanged"
                if content == rendered[name] or is_adoptable_profile(name, content)
                else "conflict"
            )
    return statuses


def _print_statuses(target: Path, statuses: dict[str, str]) -> int:
    conflict = False
    for name in sorted(PROFILE_NAMES):
        status = statuses[name]
        if status == "conflict":
            print(f"conflict {target / name} (left untouched)", file=sys.stderr)
            conflict = True
        else:
            print(f"{status} {target / name if status == 'missing' else name}")
    return 2 if conflict else 0


def _all_adoptable(target: Path) -> bool:
    for name in PROFILE_NAMES:
        try:
            content = read_regular_nofollow(target / name, 256 * 1024)
        except (FileNotFoundError, OSError, SecurityError):
            return False
        if not is_adoptable_profile(name, content):
            return False
    return True


def _collision_statuses(target: Path) -> dict[str, str]:
    statuses = {}
    for name in PROFILE_NAMES:
        try:
            (target / name).lstat()
        except FileNotFoundError:
            statuses[name] = "missing"
        except OSError:
            statuses[name] = "conflict"
        else:
            statuses[name] = "conflict"
    return statuses


def _exists_nofollow(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise SystemExit(f"Could not inspect {path}: {error}") from error
    return True


def install_profiles(templates_dir: Path, target: Path, *, check_only: bool) -> int:
    load_templates(templates_dir)
    canonical_target = Path(canonical_system_path(target))
    target_fd = open_target_directory(canonical_target, create=False)
    if target_fd is None and check_only:
        for name in sorted(PROFILE_NAMES):
            print(f"missing {target / name}")
        return 0
    if target_fd is not None:
        os.close(target_fd)

    if check_only:
        canonical_target = _ensure_private_root(
            canonical_target, create=False, managed_agents=True
        )
        state = state_root_for_target(canonical_target)
        state_exists = _exists_nofollow(state)
        config = load_config(state) if state_exists else load_config(state)
        statuses = _read_compatibility_status(
            canonical_target, config, state_exists=state_exists
        )
        return _print_statuses(target, statuses)

    canonical_target = _ensure_private_root(
        canonical_target, managed_agents=True
    )
    state_path = state_root_for_target(canonical_target)
    state_exists = _exists_nofollow(state_path)
    if not state_exists:
        config = load_config(state_path)
        statuses = _read_compatibility_status(
            canonical_target, config, state_exists=False
        )
        if all(status == "missing" for status in statuses.values()):
            action = "install"
        elif _all_adoptable(canonical_target):
            action = "adopt"
        else:
            return _print_statuses(
                target, _collision_statuses(canonical_target)
            )
        state = _ensure_private_root(state_path)
    else:
        state = _ensure_private_root(state_path, create=False)
        config = load_config(state)
        try:
            statuses = _read_compatibility_status(
                canonical_target, config, state_exists=True
            )
        except ProfileConflict:
            return _print_statuses(target, _collision_statuses(canonical_target))
        action = "install"
    try:
        token, preview = preview_profiles(action, config, canonical_target, state)
        result = apply_profiles(action, token, canonical_target, state)
    except ProfileConflict:
        return _print_statuses(target, statuses)
    if not preview.ok or not result.ok:
        return 1
    label = "installed" if result.data["change_count"] else "unchanged"
    for name in sorted(PROFILE_NAMES):
        print(f"{label} {name}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    templates_dir = REPOSITORY_ROOT / "agents"
    try:
        return install_profiles(templates_dir, args.target, check_only=args.check)
    except ConfigError as error:
        print(f"Invalid LaneOrchestrator configuration: {error}", file=sys.stderr)
        return 1
    except ProfileConflict as error:
        print(f"Profile lifecycle refused the operation: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
