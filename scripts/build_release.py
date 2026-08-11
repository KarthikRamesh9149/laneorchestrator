#!/usr/bin/env python3
"""Build deterministic, allowlisted LaneOrchestrator release archives.

Static roots, trees, and leaves are rejected when linked or non-regular.  As
with the repository's mutation primitives, hostile same-effective-UID races
are outside this release-tool boundary; the builder does not claim a portable
compare-and-replace guarantee for a hostile source checkout.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from laneorchestrator.security import (
    DuplicateJSONKeyError,
    SecurityError,
    parse_json_object,
    read_regular_nofollow,
)


RELEASE_FILES = (
    "CHANGELOG.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "LICENSE",
    "NOTICE", "README.md", "RELEASING.md", "SECURITY.md", "SUPPORT.md",
    "plugin.json", ".codex-plugin/plugin.json", ".agents/plugins/marketplace.json",
    ".github/CODEOWNERS", ".github/pull_request_template.md",
)
# This is a source release archive: included contributor/release guides invoke
# the validator and installer, so their scripts, tests, benchmark corpus and
# CI evidence definitions are deliberately shipped as bounded trees too.
RELEASE_TREES = (
    "agents", "laneorchestrator", "skills/laneorchestrator", "docs", "benchmarks",
    "scripts", "tests", ".github/ISSUE_TEMPLATE", ".github/workflows",
)
MAX_MEMBER_BYTES = 1024 * 1024
MAX_MEMBERS = 512
MAX_TOTAL_BYTES = 12 * 1024 * 1024
RELEASE_EXECUTABLES = frozenset((
    "scripts/install-agents.sh",
    "scripts/install_agents.py",
    "scripts/validate.sh",
))
_VERSION = re.compile(r'^__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', re.MULTILINE)
_WINDOWS_RESERVED = frozenset(
    ("con", "prn", "aux", "nul", "clock$")
    + tuple("com{0}".format(number) for number in range(1, 10))
    + tuple("lpt{0}".format(number) for number in range(1, 10))
)


class ReleaseError(ValueError):
    """Raised when release input cannot safely be packaged."""


@dataclass(frozen=True)
class ReleaseBuild:
    tar_path: Path
    zip_path: Path
    sums_path: Path
    sha256: Dict[str, str]


def release_version(root: Path) -> str:
    """Return the one source-tree version after checking all release identities."""

    root = _release_root(root)
    try:
        package = read_regular_nofollow(
            root / "laneorchestrator" / "__init__.py", MAX_MEMBER_BYTES
        ).decode("utf-8")
        match = _VERSION.search(package)
        if match is None:
            raise ReleaseError("laneorchestrator/__init__.py: version is missing")
        version = match.group(1)
        for name in ("plugin.json", ".codex-plugin/plugin.json"):
            payload = parse_json_object(
                read_regular_nofollow(root / name, MAX_MEMBER_BYTES).decode("utf-8")
            )
            if not isinstance(payload, dict) or payload.get("version") != version:
                raise ReleaseError("{0}: version does not equal package version".format(name))
    except DuplicateJSONKeyError as error:
        raise ReleaseError(str(error)) from error
    except (OSError, SecurityError, UnicodeError, ValueError) as error:
        raise ReleaseError("could not load release version") from error
    return version


def _release_root(root: Path) -> Path:
    supplied = Path(root)
    try:
        metadata = os.lstat(supplied)
    except OSError as error:
        raise ReleaseError("release root is missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ReleaseError("release root is not a regular directory")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReleaseError("release reads require no-follow support")
    return supplied.resolve()


def _relative_name(root: Path, candidate: Path) -> str:
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ReleaseError("candidate is outside release root") from error
    name = relative.as_posix()
    _validate_canonical_name(name)
    return name


def _validate_canonical_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ReleaseError("archive member name is empty")
    if name != unicodedata.normalize("NFC", name):
        raise ReleaseError("archive member name is not NFC normalized")
    if "\\" in name or "\x00" in name or name.startswith("/") or name.startswith("//"):
        raise ReleaseError("archive member name is unsafe")
    if re.match(r"^[A-Za-z]:", name) or any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ReleaseError("archive member name is unsafe")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ReleaseError("archive member name is unsafe")
    for part in parts:
        stem = unicodedata.normalize("NFKC", part.split(".", 1)[0]).casefold()
        if part.endswith((".", " ")) or ":" in part or stem in _WINDOWS_RESERVED:
            raise ReleaseError("archive member name is unsafe on Windows")


def _contains(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def validate_release_members(root: Path, candidates: Sequence[Path]) -> List[Path]:
    """Return regular, single-link, contained files or fail closed on unsafe input."""

    release_root = _release_root(root)
    validated: List[Tuple[str, Path]] = []
    seen = set()
    canonical_seen = set()
    for supplied in candidates:
        candidate = Path(supplied)
        absolute = candidate if candidate.is_absolute() else release_root / candidate
        canonical = absolute.resolve(strict=False)
        try:
            lexical = canonical.relative_to(release_root)
        except ValueError as error:
            raise ReleaseError("candidate is outside release root") from error
        try:
            resolved = absolute.resolve(strict=True)
        except FileNotFoundError as error:
            raise ReleaseError("candidate is missing") from error
        except OSError as error:
            raise ReleaseError("candidate could not be resolved") from error
        if not _contains(release_root, resolved):
            raise ReleaseError("candidate resolves outside release root")
        try:
            metadata = os.lstat(absolute)
        except OSError as error:
            raise ReleaseError("candidate is missing") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseError("candidate is a symbolic link")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ReleaseError("candidate is not a regular file")
        if metadata.st_nlink != 1:
            raise ReleaseError("candidate has multiple links")
        name = _relative_name(release_root, release_root / lexical)
        key = unicodedata.normalize("NFKC", name).casefold()
        if name in seen or key in canonical_seen:
            raise ReleaseError("duplicate release member")
        seen.add(name)
        canonical_seen.add(key)
        validated.append((name, release_root / lexical))
    if not validated:
        raise ReleaseError("release contains no files")
    return [path for _, path in sorted(validated, key=lambda item: item[0])]


def archive_members(root: Path) -> List[Path]:
    """List exactly the explicit public files and trees allowed in a release."""

    root = _release_root(root)
    explicit = [root / name for name in RELEASE_FILES]
    trees: List[Path] = []
    for tree in RELEASE_TREES:
        source = root / tree
        try:
            source_metadata = os.lstat(source)
        except OSError as error:
            raise ReleaseError("release tree is missing or unsafe: {0}".format(tree)) from error
        if stat.S_ISLNK(source_metadata.st_mode) or not stat.S_ISDIR(source_metadata.st_mode):
            raise ReleaseError("release tree is missing or unsafe: {0}".format(tree))
        pending = [source]
        traversed = 0
        while pending:
            directory = pending.pop()
            entries = []
            try:
                with os.scandir(directory) as stream:
                    for entry in stream:
                        traversed += 1
                        if traversed > MAX_MEMBERS:
                            raise ReleaseError("release tree traversal exceeds member limit")
                        path = Path(entry.path)
                        relative_parts = path.relative_to(source).parts
                        if tree == "docs" and "superpowers" in relative_parts:
                            continue
                        try:
                            metadata = entry.stat(follow_symlinks=False)
                        except OSError as error:
                            raise ReleaseError("could not inspect release tree member") from error
                        if stat.S_ISLNK(metadata.st_mode):
                            raise ReleaseError("release tree contains symbolic link")
                        if stat.S_ISDIR(metadata.st_mode):
                            entries.append((entry.name, path, True))
                        elif stat.S_ISREG(metadata.st_mode):
                            if "__pycache__" not in path.parts and path.suffix != ".pyc":
                                trees.append(path)
                        else:
                            raise ReleaseError("release tree contains non-regular member")
            except OSError as error:
                raise ReleaseError("could not traverse release tree") from error
            for _name, path, is_directory in reversed(sorted(entries, key=lambda item: item[0])):
                if is_directory:
                    pending.append(path)
    members = validate_release_members(root, explicit + trees)
    if len(members) > MAX_MEMBERS:
        raise ReleaseError("release has too many members")
    return members


def _read_member(path: Path) -> bytes:
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ReleaseError("source member is unsafe")
        if before.st_size > MAX_MEMBER_BYTES:
            raise ReleaseError("source member exceeds size limit")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReleaseError("could not open source member") from error
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ReleaseError("source member changed while opening")
        if opened.st_size > MAX_MEMBER_BYTES:
            raise ReleaseError("source member exceeds size limit")
        content = os.read(descriptor, MAX_MEMBER_BYTES + 1)
        while len(content) <= MAX_MEMBER_BYTES:
            chunk = os.read(descriptor, MAX_MEMBER_BYTES + 1 - len(content))
            if not chunk:
                break
            content += chunk
    finally:
        os.close(descriptor)
    if len(content) > MAX_MEMBER_BYTES:
        raise ReleaseError("source member exceeds size limit")
    return content


def _captured_members(root: Path) -> List[Tuple[str, bytes]]:
    result: List[Tuple[str, bytes]] = []
    total = 0
    for path in archive_members(root):
        content = _read_member(path)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ReleaseError("release exceeds total size limit")
        result.append((_relative_name(Path(root).resolve(), path), content))
    return result


def _archive_prefix(version: str) -> str:
    return "laneorchestrator-{0}".format(version)


def archive_mode(relative_name: str) -> int:
    """Return the sole executable-mode allowlist for source release members."""

    return 0o755 if relative_name in RELEASE_EXECUTABLES else 0o644


def _tar_bytes(prefix: str, members: Iterable[Tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as compressed:
        with tarfile.open(mode="w", fileobj=compressed, format=tarfile.USTAR_FORMAT) as archive:
            for name, content in members:
                info = tarfile.TarInfo("{0}/{1}".format(prefix, name))
                info.size = len(content)
                info.mtime = 0
                info.mode = archive_mode(name)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def _zip_bytes(prefix: str, members: Iterable[Tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        archive.comment = b""
        for name, content in members:
            info = zipfile.ZipInfo("{0}/{1}".format(prefix, name), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100000 | archive_mode(name)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            info.extra = b""
            info.comment = b""
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def _safe_output(root: Path, output: Path) -> Path:
    output = Path(output)
    resolved = output.resolve(strict=False)
    if resolved == root or _contains(root, resolved):
        raise ReleaseError("output directory must be outside the release root")
    if output.exists():
        metadata = os.lstat(output)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ReleaseError("output path is unsafe")
        if any(output.iterdir()):
            raise ReleaseError("output directory is not empty")
    else:
        output.mkdir(parents=True, mode=0o700)
    return output


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError as error:
        raise ReleaseError("release asset already exists") from error
    except OSError as error:
        raise ReleaseError("could not write release asset") from error


def build_release(root: Path, output: Path) -> ReleaseBuild:
    """Build the exact v0.2.1 archive pair and strict checksum manifest."""

    root = _release_root(root)
    version = release_version(root)
    destination = _safe_output(root, Path(output))
    members = _captured_members(root)
    prefix = _archive_prefix(version)
    tar_name = "{0}.tar.gz".format(prefix)
    zip_name = "{0}.zip".format(prefix)
    assets = {tar_name: _tar_bytes(prefix, members), zip_name: _zip_bytes(prefix, members)}
    sha256 = {name: hashlib.sha256(assets[name]).hexdigest() for name in sorted(assets)}
    sums = "".join("{0}  {1}\n".format(sha256[name], name) for name in sorted(assets))
    created: List[Path] = []
    try:
        for name in sorted(assets):
            path = destination / name
            _write_exclusive(path, assets[name])
            created.append(path)
        sums_path = destination / "SHA256SUMS"
        _write_exclusive(sums_path, sums.encode("ascii"))
        created.append(sums_path)
    except Exception:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return ReleaseBuild(destination / tar_name, destination / zip_name, destination / "SHA256SUMS", sha256)


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic LaneOrchestrator release assets.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        release = build_release(args.root, args.output)
    except ReleaseError as error:
        print("build_release: {0}".format(error), file=sys.stderr)
        return 1
    except OSError as error:
        print("build_release: operational error: {0}".format(error), file=sys.stderr)
        return 2
    print(release.sums_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
