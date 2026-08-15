#!/usr/bin/env python3
"""Check the tracked public documentation surface without network access."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from laneorchestrator.security import SecurityError, read_regular_nofollow


MARKDOWN_LINK = re.compile(r"!?(?:\[[^]]*\])\(([^)]+)\)")
LOCAL_PATH = re.compile(r"/(?:Users|home)/[^\s`'\"]+|[A-Za-z]:\\\\Users\\\\")
SECRET = re.compile(r"(?:-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b)")
UNSAFE = re.compile(r"<script|<foreignObject|\son\w+\s*=|(?:href|src|xlink:href)\s*=\s*[\"'](?:data:|javascript:)", re.IGNORECASE)
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_DOCUMENT_TOTAL_BYTES = 12 * 1024 * 1024
MAX_DOCUMENT_ENTRIES = 512
MAX_DOCUMENT_DEPTH = 32
MEDIA_LIMITS = {".gif": 5 * 1024 * 1024, ".mp4": 10 * 1024 * 1024}


class DocumentationError(ValueError):
    """Raised when public documentation cannot be checked safely."""


def _regular_nofollow(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DocumentationError("could not inspect {0}".format(path)) from error
    if stat.S_ISLNK(metadata.st_mode):
        raise DocumentationError("symbolic links are not allowed")
    if not stat.S_ISREG(metadata.st_mode):
        raise DocumentationError("path is not a regular file")
    return True


def _public_files(root: Path) -> Iterable[Path]:
    names = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "RELEASING.md", "SECURITY.md", "SUPPORT.md")
    for name in names:
        path = root / name
        try:
            if _regular_nofollow(path):
                yield path
        except DocumentationError as error:
            raise DocumentationError("{0}: {1}".format(name, error)) from error

    docs = root / "docs"
    try:
        metadata = os.lstat(docs)
    except FileNotFoundError:
        return
    except OSError as error:
        raise DocumentationError("docs: could not inspect") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise DocumentationError("docs: symbolic links are not allowed")
    if not stat.S_ISDIR(metadata.st_mode):
        raise DocumentationError("docs: path is not a directory")

    pending = [(docs, 0)]
    entries_seen = 0
    while pending:
        directory, depth = pending.pop()
        entries = []
        try:
            with os.scandir(directory) as stream:
                for entry in stream:
                    entries_seen += 1
                    if entries_seen > MAX_DOCUMENT_ENTRIES:
                        raise DocumentationError("docs: traversal exceeds entry limit")
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if "superpowers" in path.relative_to(docs).parts:
                        continue
                    try:
                        entry_metadata = entry.stat(follow_symlinks=False)
                    except OSError as error:
                        raise DocumentationError("{0}: could not inspect".format(relative)) from error
                    if stat.S_ISLNK(entry_metadata.st_mode):
                        raise DocumentationError("{0}: symbolic links are not allowed".format(relative))
                    if stat.S_ISDIR(entry_metadata.st_mode):
                        if depth >= MAX_DOCUMENT_DEPTH:
                            raise DocumentationError("docs: traversal exceeds directory depth")
                        entries.append((entry.name, path))
                    elif stat.S_ISREG(entry_metadata.st_mode):
                        yield path
                    else:
                        raise DocumentationError("{0}: path is not a regular file".format(relative))
        except OSError as error:
            raise DocumentationError("docs: could not traverse") from error
        for _name, child in reversed(sorted(entries, key=lambda item: item[0])):
            pending.append((child, depth + 1))


def check_docs(root: Path) -> List[str]:
    """Return sorted public-doc errors; planning inputs are deliberately excluded."""

    supplied = Path(root)
    try:
        root_metadata = os.lstat(supplied)
    except OSError:
        return ["documentation root: cannot inspect"]
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        return ["documentation root: unsafe"]
    root = supplied.resolve()
    errors: List[str] = []
    total_bytes = 0
    try:
        for path in _public_files(root):
            relative = path.relative_to(root).as_posix()
            suffix = path.suffix.lower()
            try:
                content = read_regular_nofollow(path, MEDIA_LIMITS.get(suffix, MAX_DOCUMENT_BYTES))
            except SecurityError as error:
                errors.append("{0}: cannot read ({1})".format(relative, error))
                continue
            total_bytes += len(content)
            if total_bytes > MAX_DOCUMENT_TOTAL_BYTES:
                errors.append("documentation: total byte limit exceeded")
                break
            if suffix == ".gif":
                if content[:6] not in {b"GIF87a", b"GIF89a"}:
                    errors.append("{0}: invalid GIF signature".format(relative))
                continue
            if suffix == ".mp4":
                if len(content) < 12 or content[4:8] != b"ftyp":
                    errors.append("{0}: invalid MP4 signature".format(relative))
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if SECRET.search(text):
                errors.append("{0}: credential-like content".format(relative))
            if LOCAL_PATH.search(text):
                errors.append("{0}: local machine path".format(relative))
            if UNSAFE.search(text):
                errors.append("{0}: unsafe active content".format(relative))
            if path.suffix == ".md":
                for target in MARKDOWN_LINK.findall(text):
                    clean = target.strip().split("#", 1)[0]
                    if not clean or "://" in clean or clean.startswith("mailto:"):
                        continue
                    lexical = path.parent / clean
                    try:
                        target_metadata = os.lstat(lexical)
                    except FileNotFoundError:
                        target_metadata = None
                    except OSError:
                        errors.append("{0}: cannot inspect relative link ({1})".format(relative, target))
                        continue
                    if target_metadata is not None and stat.S_ISLNK(target_metadata.st_mode):
                        errors.append("{0}: relative link is symbolic ({1})".format(relative, target))
                        continue
                    candidate = lexical.resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        errors.append("{0}: link escapes root ({1})".format(relative, target))
                        continue
                    if target_metadata is None:
                        errors.append("{0}: broken relative link ({1})".format(relative, target))
    except DocumentationError as error:
        errors.append(str(error))
    return sorted(set(errors))


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate public documentation.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = check_docs(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
