#!/usr/bin/env python3
"""Verify LaneOrchestrator release archives without extracting untrusted data."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import stat
import struct
import sys
import tarfile
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Sequence, Tuple

try:
    from scripts.build_release import (
        MAX_MEMBER_BYTES,
        MAX_MEMBERS,
        MAX_TOTAL_BYTES,
        RELEASE_BINARY_FILES,
        RELEASE_EXECUTABLES,
        ReleaseError,
        _captured_members,
        release_version,
    )
except ModuleNotFoundError:  # Direct ``python scripts/verify_release.py`` execution.
    from build_release import (  # type: ignore
        MAX_MEMBER_BYTES,
        MAX_MEMBERS,
        MAX_TOTAL_BYTES,
        RELEASE_BINARY_FILES,
        RELEASE_EXECUTABLES,
        ReleaseError,
        _captured_members,
        release_version,
    )


MAX_ASSET_BYTES = 24 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_TAR_DECOMPRESSED_BYTES = MAX_TOTAL_BYTES + (MAX_MEMBERS * 1024) + 1024
MAX_ZIP_CENTRAL_DIRECTORY_BYTES = MAX_MEMBERS * 512
_DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (laneorchestrator-[0-9]+\.[0-9]+\.[0-9]+\.(?:tar\.gz|zip))$")
_WINDOWS_RESERVED = frozenset(
    ("con", "prn", "aux", "nul", "clock$")
    + tuple("com{0}".format(number) for number in range(1, 10))
    + tuple("lpt{0}".format(number) for number in range(1, 10))
)


class ReleaseVerificationError(ValueError):
    """Raised when a release asset does not satisfy the public contract."""


def _read_asset(path: Path, max_bytes: int = MAX_ASSET_BYTES) -> bytes:
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ReleaseVerificationError("asset is not a single regular file: {0}".format(path.name))
        if before.st_size > max_bytes:
            raise ReleaseVerificationError("asset exceeds size limit: {0}".format(path.name))
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError as error:
        raise ReleaseVerificationError("asset is missing: {0}".format(path.name)) from error
    except OSError as error:
        raise ReleaseVerificationError("could not open asset: {0}".format(path.name)) from error
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ReleaseVerificationError("asset changed while opening: {0}".format(path.name))
        chunks: List[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(content) > max_bytes:
        raise ReleaseVerificationError("asset exceeds size limit: {0}".format(path.name))
    return content


def _validate_name(name: str, prefix: str) -> str:
    if not isinstance(name, str) or not name or name != unicodedata.normalize("NFC", name):
        raise ReleaseVerificationError("archive member has invalid name")
    if "\\" in name or "\x00" in name or name.startswith("/") or name.startswith("//") or re.match(r"^[A-Za-z]:", name):
        raise ReleaseVerificationError("archive member has unsafe name: {0!r}".format(name))
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts) or any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ReleaseVerificationError("archive member has unsafe name: {0!r}".format(name))
    for part in parts:
        stem = unicodedata.normalize("NFKC", part.split(".", 1)[0]).casefold()
        if part.endswith((".", " ")) or ":" in part or stem in _WINDOWS_RESERVED:
            raise ReleaseVerificationError("archive member has unsafe Windows name: {0!r}".format(name))
    expected_prefix = prefix + "/"
    if not name.startswith(expected_prefix):
        raise ReleaseVerificationError("archive member has wrong release prefix: {0!r}".format(name))
    relative = name[len(expected_prefix):]
    if not relative or relative != PurePosixPath(relative).as_posix():
        raise ReleaseVerificationError("archive member has unsafe name: {0!r}".format(name))
    return relative


def _record(records: List[Tuple[str, bytes]], seen: set, name: str, content: bytes, prefix: str) -> None:
    relative = _validate_name(name, prefix)
    identity = unicodedata.normalize("NFKC", relative).casefold()
    if identity in seen:
        raise ReleaseVerificationError("duplicate archive member: {0}".format(name))
    seen.add(identity)
    if len(content) > MAX_MEMBER_BYTES:
        raise ReleaseVerificationError("archive member exceeds size limit: {0}".format(name))
    records.append((relative, content))
    if len(records) > MAX_MEMBERS or sum(len(item[1]) for item in records) > MAX_TOTAL_BYTES:
        raise ReleaseVerificationError("archive exceeds member resource limit")


def _tar_members(content: bytes, prefix: str) -> List[Tuple[str, bytes]]:
    records: List[Tuple[str, bytes]] = []
    seen = set()
    try:
        if len(content) < 10 or content[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff":
            raise ReleaseVerificationError("tar gzip header is not deterministic")
        decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        payload = decompressor.decompress(content, MAX_TAR_DECOMPRESSED_BYTES + 1)
        if len(payload) > MAX_TAR_DECOMPRESSED_BYTES:
            raise ReleaseVerificationError("tar archive exceeds decompression limit")
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            raise ReleaseVerificationError("tar archive has trailing or incomplete gzip data")
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            archive_end = 0
            for member in archive:
                if not member.isfile() or member.issym() or member.islnk() or member.linkname:
                    raise ReleaseVerificationError("tar member is not a regular file: {0}".format(member.name))
                relative = _validate_name(member.name, prefix)
                expected_mode = 0o755 if relative in RELEASE_EXECUTABLES else 0o644
                if member.mode != expected_mode or member.mtime != 0 or member.uid != 0 or member.gid != 0 or member.uname or member.gname or member.pax_headers:
                    raise ReleaseVerificationError("tar member has unsafe metadata: {0}".format(member.name))
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise ReleaseVerificationError("tar member exceeds size limit: {0}".format(member.name))
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseVerificationError("tar member cannot be read: {0}".format(member.name))
                data = source.read(MAX_MEMBER_BYTES + 1)
                archive_end = max(archive_end, member.offset_data + ((member.size + 511) // 512) * 512)
                _record(records, seen, member.name, data, prefix)
        if not records or len(payload) - archive_end < 1024 or payload[archive_end:].strip(b"\0"):
            raise ReleaseVerificationError("tar archive has trailing data")
    except (tarfile.TarError, OSError, zlib.error) as error:
        raise ReleaseVerificationError("invalid tar archive") from error
    return records


def _zip_members(content: bytes, prefix: str) -> List[Tuple[str, bytes]]:
    records: List[Tuple[str, bytes]] = []
    seen = set()
    try:
        directory_offset = _zip_entry_count(content)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            if archive.comment:
                raise ReleaseVerificationError("zip archive has a comment")
            for info in archive.infolist():
                if info.is_dir() or info.flag_bits & 0x1 or info.flag_bits & 0x8:
                    raise ReleaseVerificationError("zip member has unsupported flags: {0}".format(info.filename))
                if info.extra or info.comment or info.date_time != (1980, 1, 1, 0, 0, 0):
                    raise ReleaseVerificationError("zip member has unsafe metadata: {0}".format(info.filename))
                mode = (info.external_attr >> 16) & 0o777777
                relative = _validate_name(info.filename, prefix)
                expected_mode = 0o100000 | (0o755 if relative in RELEASE_EXECUTABLES else 0o644)
                if info.create_system != 3 or mode != expected_mode or info.compress_type != zipfile.ZIP_DEFLATED:
                    raise ReleaseVerificationError("zip member has unsafe metadata: {0}".format(info.filename))
                if info.file_size > MAX_MEMBER_BYTES or info.compress_size <= 0 or info.file_size > info.compress_size * MAX_COMPRESSION_RATIO:
                    raise ReleaseVerificationError("zip member exceeds resource limit: {0}".format(info.filename))
                _check_local_zip_header(content, info, directory_offset)
                data = archive.read(info, pwd=None)
                _record(records, seen, info.filename, data, prefix)
    except (zipfile.BadZipFile, OSError, RuntimeError) as error:
        raise ReleaseVerificationError("invalid zip archive") from error
    return records


def _check_local_zip_header(content: bytes, info: zipfile.ZipInfo, directory_offset: int) -> None:
    """Bind central-directory metadata to its bounded local file header."""

    offset = info.header_offset
    if offset < 0 or offset + 30 > directory_offset:
        raise ReleaseVerificationError("zip member has unsafe local header: {0}".format(info.filename))
    fields = struct.unpack("<4s5H3L2H", content[offset:offset + 30])
    signature, version, flags, method, _time, _date, crc, compressed_size, size, name_size, extra_size = fields
    end = offset + 30 + name_size + extra_size + compressed_size
    if signature != b"PK\x03\x04" or end > directory_offset:
        raise ReleaseVerificationError("zip member has unsafe local header: {0}".format(info.filename))
    encoding = "utf-8" if info.flag_bits & 0x800 else "cp437"
    try:
        local_name = content[offset + 30:offset + 30 + name_size].decode(encoding)
    except UnicodeDecodeError as error:
        raise ReleaseVerificationError("zip member has invalid local name: {0}".format(info.filename)) from error
    local_extra = content[offset + 30 + name_size:offset + 30 + name_size + extra_size]
    if (
        version != info.extract_version
        or flags != info.flag_bits
        or method != info.compress_type
        or crc != info.CRC
        or compressed_size != info.compress_size
        or size != info.file_size
        or local_name != info.filename
        or local_extra != info.extra
    ):
        raise ReleaseVerificationError("zip member local header differs from central directory: {0}".format(info.filename))


def _zip_entry_count(content: bytes) -> int:
    """Bound the central-directory count before constructing ``ZipFile``."""

    start = max(0, len(content) - 65557)
    offset = content.rfind(b"PK\x05\x06", start)
    if offset < 0 or offset + 22 > len(content):
        raise ReleaseVerificationError("zip archive has no valid EOCD")
    fields = struct.unpack("<4s4H2LH", content[offset:offset + 22])
    disk, directory_disk, disk_entries, total_entries, directory_size, directory_offset, comment_size = fields[1:]
    if offset + 22 + comment_size != len(content):
        raise ReleaseVerificationError("zip archive EOCD is malformed")
    if (
        disk != 0 or directory_disk != 0 or disk_entries != total_entries
        or total_entries > MAX_MEMBERS or total_entries == 0xFFFF
        or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF
    ):
        raise ReleaseVerificationError("zip archive exceeds entry limit")
    if directory_size > MAX_ZIP_CENTRAL_DIRECTORY_BYTES:
        raise ReleaseVerificationError("zip archive central directory exceeds resource limit")
    if directory_offset + directory_size != offset:
        raise ReleaseVerificationError("zip archive central directory is malformed")
    return directory_offset


def _parse_sums(content: bytes, expected_names: Sequence[str]) -> Dict[str, str]:
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as error:
        raise ReleaseVerificationError("SHA256SUMS is not ASCII") from error
    if not text.endswith("\n") or "\r" in text:
        raise ReleaseVerificationError("SHA256SUMS must use final LF-only records")
    lines = text.splitlines()
    if len(lines) != len(expected_names):
        raise ReleaseVerificationError("SHA256SUMS has wrong record count")
    parsed: Dict[str, str] = {}
    for line in lines:
        match = _DIGEST_LINE.fullmatch(line)
        if match is None:
            raise ReleaseVerificationError("SHA256SUMS has malformed record")
        digest, name = match.groups()
        if name in parsed:
            raise ReleaseVerificationError("SHA256SUMS has duplicate record")
        parsed[name] = digest
    if list(parsed) != sorted(expected_names) or set(parsed) != set(expected_names):
        raise ReleaseVerificationError("SHA256SUMS has unexpected asset names")
    return parsed


def _check_content(name: str, content: bytes) -> None:
    if name in RELEASE_BINARY_FILES:
        _check_demo_gif(name, content)
        text = content.decode("latin-1")
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReleaseVerificationError("release content is not UTF-8: {0}".format(name)) from error
    secret_patterns = (
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b",
        r"\bsk-proj-[A-Za-z0-9_-]{20,}\b",
        r"\bsk-[A-Za-z0-9]{20,}\b",
        r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
        r"\bglpat-[A-Za-z0-9_-]{20,}\b",
    )
    if any(re.search(pattern, text) for pattern in secret_patterns):
        raise ReleaseVerificationError("release content contains credential-like data: {0}".format(name))
    local_path = r"/(?:Users|home)/[^\s`'\"]+|/private" + r"/var/folders/[^\s`'\"]+|[A-Za-z]:\\Users\\"
    if re.search(local_path, text):
        raise ReleaseVerificationError("release content contains local path: {0}".format(name))


def _check_demo_gif(name: str, content: bytes) -> None:
    if len(content) > 1_000_000 or content[:6] != b"GIF89a" or content[-1:] != b"\x3b":
        raise ReleaseVerificationError("release GIF is malformed: {0}".format(name))
    if int.from_bytes(content[6:8], "little") != 1200 or int.from_bytes(content[8:10], "little") != 675:
        raise ReleaseVerificationError("release GIF has unexpected dimensions: {0}".format(name))
    controls = [index for index in range(len(content)) if content.startswith(b"\x21\xf9\x04", index)]
    if len(controls) < 20:
        raise ReleaseVerificationError("release GIF is not sufficiently animated: {0}".format(name))
    duration = sum(int.from_bytes(content[index + 4:index + 6], "little") for index in controls)
    if duration != 2_000 or b"NETSCAPE2.0" not in content:
        raise ReleaseVerificationError("release GIF has unexpected playback metadata: {0}".format(name))


def verify_release(dist_dir: Path, root: Path = None) -> None:
    """Validate exact release assets against an allowlisted source root.

    No archive member is extracted to disk.  Both formats must have the same
    ordered contents and must equal a fresh, no-follow source capture.
    """

    source_root = Path.cwd() if root is None else Path(root)
    source_root = source_root.resolve()
    version = release_version(source_root)
    prefix = "laneorchestrator-{0}".format(version)
    expected_assets = ("{0}.tar.gz".format(prefix), "{0}.zip".format(prefix))
    directory = Path(dist_dir)
    try:
        metadata = os.lstat(directory)
    except OSError as error:
        raise ReleaseVerificationError("distribution directory is missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ReleaseVerificationError("distribution directory is unsafe")
    actual = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                actual.append(entry.name)
                if len(actual) > len(expected_assets) + 1:
                    raise ReleaseVerificationError("distribution directory has missing or unexpected assets")
    except OSError as error:
        raise ReleaseVerificationError("could not inspect distribution directory") from error
    actual.sort()
    if actual != sorted(expected_assets + ("SHA256SUMS",)):
        raise ReleaseVerificationError("distribution directory has missing or unexpected assets")
    assets = {name: _read_asset(directory / name) for name in expected_assets}
    sums = _parse_sums(_read_asset(directory / "SHA256SUMS", max_bytes=4096), expected_assets)
    for name in expected_assets:
        if hashlib.sha256(assets[name]).hexdigest() != sums[name]:
            raise ReleaseVerificationError("checksum mismatch: {0}".format(name))
    tar_members = _tar_members(assets[expected_assets[0]], prefix)
    zip_members = _zip_members(assets[expected_assets[1]], prefix)
    expected_members = _captured_members(source_root)
    if tar_members != zip_members:
        raise ReleaseVerificationError("tar and zip archive content differs")
    if tar_members != expected_members:
        raise ReleaseVerificationError("archive content differs from release allowlist")
    for name, content in tar_members:
        _check_content(name, content)


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify deterministic LaneOrchestrator release assets.")
    parser.add_argument("dist_dir", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        verify_release(args.dist_dir, root=args.root)
    except (ReleaseVerificationError, ReleaseError) as error:
        print("verify_release: {0}".format(error), file=sys.stderr)
        return 1
    except OSError as error:
        print("verify_release: operational error: {0}".format(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
