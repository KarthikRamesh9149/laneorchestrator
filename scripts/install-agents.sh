#!/bin/sh
set -eu

usage() { printf '%s\n' 'Usage: install-agents.sh [--check] [--target DIRECTORY]'; exit 64; }
check_only=false
target="${HOME}/.codex/agents"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) check_only=true ;;
    --target) shift; [ "$#" -gt 0 ] || usage; target=$1 ;;
    *) usage ;;
  esac
  shift
done

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
templates_dir=$(CDPATH='' cd -- "$script_dir/../agents" && pwd)
python_bin=${PYTHON:-python3}
exec "$python_bin" - "$templates_dir" "$target" "$check_only" <<'PY'
import os
import re
import stat
import sys
from pathlib import Path


templates_dir = Path(sys.argv[1])
target = Path(sys.argv[2])
check_only = sys.argv[3] == "true"
field = re.compile(r'^\s*(name|description|model|model_reasoning_effort|sandbox_mode)\s*=\s*"(.+)"\s*$', re.MULTILINE)
templates = sorted(templates_dir.glob("*.toml"))
for path in templates:
    data = dict(field.findall(path.read_text(encoding="utf-8")))
    for key in ("name", "description", "model", "model_reasoning_effort", "sandbox_mode"):
        if not data.get(key):
            raise SystemExit(f"Invalid {path.name}: missing {key}")


def canonical_system_path(path: Path) -> str:
    """Resolve root-owned platform aliases, but reject caller-controlled links."""
    raw = os.path.abspath(os.fspath(path))
    for _ in range(32):
        current = os.path.sep
        components = Path(raw).parts[1:]
        for index, component in enumerate(components):
            current = os.path.join(current, component)
            try:
                details = os.lstat(current)
            except FileNotFoundError:
                return raw
            if not stat.S_ISLNK(details.st_mode):
                continue
            if details.st_uid != 0:
                raise SystemExit(f"Unsafe target directory {path}: symbolic links are not allowed")
            raw = os.path.join(os.path.realpath(current), *components[index + 1:])
            break
        else:
            return raw
    raise SystemExit(f"Unsafe target directory {path}: too many symbolic links")


def open_target_directory(path: Path, create: bool):
    """Open every target component without following a symbolic link."""
    raw = canonical_system_path(path)
    if os.path.isabs(raw):
        directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        components = Path(raw).parts[1:]
    else:
        directory_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
        components = Path(raw).parts
    try:
        for component in components:
            if component in {"", "."}:
                continue
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create:
                    os.close(directory_fd)
                    return None
                os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except OSError as error:
        os.close(directory_fd)
        raise SystemExit(f"Unsafe target directory {path}: {error.strerror or error}") from error


target_fd = open_target_directory(target, create=not check_only)
if target_fd is None:
    for template in templates:
        print(f"missing {target / template.name}")
    raise SystemExit(0)

conflict = False
try:
    for template in templates:
        name = template.name
        try:
            stat_result = os.stat(name, dir_fd=target_fd, follow_symlinks=False)
        except FileNotFoundError:
            if check_only:
                print(f"missing {target / name}")
                continue
            try:
                destination_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=target_fd)
            except FileExistsError:
                print(f"conflict {target / name} (left untouched)", file=sys.stderr)
                conflict = True
                continue
            with template.open("rb") as source, os.fdopen(destination_fd, "wb") as destination:
                while chunk := source.read(64 * 1024):
                    destination.write(chunk)
            print(f"installed {name}")
            continue
        if not stat.S_ISREG(stat_result.st_mode):
            print(f"conflict {target / name} (left untouched)", file=sys.stderr)
            conflict = True
            continue
        try:
            destination_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=target_fd)
        except OSError:
            print(f"conflict {target / name} (left untouched)", file=sys.stderr)
            conflict = True
            continue
        with os.fdopen(destination_fd, "rb") as destination:
            identical = destination.read() == template.read_bytes()
        if identical:
            print(f"unchanged {name}")
        else:
            print(f"conflict {target / name} (left untouched)", file=sys.stderr)
            conflict = True
finally:
    os.close(target_fd)

raise SystemExit(2 if conflict else 0)
PY
