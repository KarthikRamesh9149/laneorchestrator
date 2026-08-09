#!/usr/bin/env python3
"""Check the tracked public documentation surface without network access."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Sequence


MARKDOWN_LINK = re.compile(r"!?(?:\[[^]]*\])\(([^)]+)\)")
LOCAL_PATH = re.compile(r"/(?:Users|home)/[^\s`'\"]+|[A-Za-z]:\\\\Users\\\\")
SECRET = re.compile(r"(?:-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b)")
UNSAFE = re.compile(r"<script|<foreignObject|\son\w+\s*=|(?:href|src|xlink:href)\s*=\s*[\"'](?:data:|javascript:)", re.IGNORECASE)


def _public_files(root: Path) -> Iterable[Path]:
    names = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "RELEASING.md", "SECURITY.md", "SUPPORT.md")
    for name in names:
        path = root / name
        if path.is_file():
            yield path
    docs = root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*")):
            if path.is_file() and "superpowers" not in path.relative_to(docs).parts:
                yield path


def check_docs(root: Path) -> List[str]:
    """Return sorted public-doc errors; planning inputs are deliberately excluded."""

    root = Path(root).resolve()
    errors: List[str] = []
    for path in _public_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as error:
            errors.append("{0}: cannot read ({1})".format(relative, error))
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
                candidate = (path.parent / clean).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    errors.append("{0}: link escapes root ({1})".format(relative, target))
                    continue
                if not candidate.exists():
                    errors.append("{0}: broken relative link ({1})".format(relative, target))
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
