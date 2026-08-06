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
FILE_MODE = 0o600
DIRECTORY_MODE = 0o700


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report profile status without changing files.")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".codex" / "agents",
        help="Agent profile directory (default: ~/.codex/agents).",
    )
    return parser.parse_args(argv)


def load_templates(templates_dir: Path) -> list[Path]:
    templates = sorted(templates_dir.glob("*.toml"))
    if not templates:
        raise SystemExit(f"No agent templates found in {templates_dir}")
    for path in templates:
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Unsafe agent template {path.name}: expected a regular file")
        try:
            fields = dict(FIELD_RE.findall(path.read_text(encoding="utf-8")))
        except OSError as error:
            raise SystemExit(f"Could not read {path.name}: {error}") from error
        missing = [field for field in PROFILE_FIELDS if not fields.get(field)]
        if missing:
            raise SystemExit(f"Invalid {path.name}: missing {', '.join(missing)}")
    return templates


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


def files_match(template: Path, target_fd: int, name: str) -> bool:
    try:
        destination_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=target_fd)
    except OSError:
        return False
    with os.fdopen(destination_fd, "rb") as destination:
        return destination.read() == template.read_bytes()


def install_profiles(templates_dir: Path, target: Path, *, check_only: bool) -> int:
    templates = load_templates(templates_dir)
    target_fd = open_target_directory(target, create=not check_only)
    if target_fd is None:
        for template in templates:
            print(f"missing {target / template.name}")
        return 0

    conflict = False
    try:
        for template in templates:
            name = template.name
            try:
                details = os.stat(name, dir_fd=target_fd, follow_symlinks=False)
            except FileNotFoundError:
                if check_only:
                    print(f"missing {target / name}")
                    continue
                try:
                    destination_fd = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        FILE_MODE,
                        dir_fd=target_fd,
                    )
                except FileExistsError:
                    print(f"conflict {target / name} (left untouched)", file=sys.stderr)
                    conflict = True
                    continue
                with template.open("rb") as source, os.fdopen(destination_fd, "wb") as destination:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        destination.write(chunk)
                print(f"installed {name}")
                continue

            if not stat.S_ISREG(details.st_mode) or not files_match(template, target_fd, name):
                print(f"conflict {target / name} (left untouched)", file=sys.stderr)
                conflict = True
            else:
                print(f"unchanged {name}")
    finally:
        os.close(target_fd)
    return 2 if conflict else 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    templates_dir = Path(__file__).resolve().parents[1] / "agents"
    return install_profiles(templates_dir, args.target, check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
