#!/usr/bin/env python3
"""Produce bounded, deterministic SARIF evidence without network access.

This is deliberately a small high-confidence AST gate for private repositories
where GitHub Code Scanning is unavailable. It is not a replacement for CodeQL.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


MAX_FILES = 512
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_TREE_ENTRIES = 4096
MAX_DIRECTORY_DEPTH = 32
MAX_AST_NODES = 100000
TOOL_NAME = "laneorchestrator-private-static-analysis"

RULES = {
    "python/dynamic-code-execution": {
        "name": "dynamic-code-execution",
        "shortDescription": {"text": "Dynamic code execution"},
        "fullDescription": {"text": "Avoid eval, exec, or compile on data that may be untrusted."},
        "defaultConfiguration": {"level": "error"},
    },
    "python/subprocess-shell-true": {
        "name": "subprocess-shell-true",
        "shortDescription": {"text": "Subprocess shell enabled"},
        "fullDescription": {"text": "Avoid shell=True unless command construction is tightly controlled."},
        "defaultConfiguration": {"level": "error"},
    },
    "python/unsafe-deserialization": {
        "name": "unsafe-deserialization",
        "shortDescription": {"text": "Unsafe deserialization"},
        "fullDescription": {"text": "Avoid loading untrusted data with pickle or marshal."},
        "defaultConfiguration": {"level": "error"},
    },
    "python/tls-verification-disabled": {
        "name": "tls-verification-disabled",
        "shortDescription": {"text": "TLS verification disabled"},
        "fullDescription": {"text": "Do not create an SSL context that disables certificate verification."},
        "defaultConfiguration": {"level": "error"},
    },
}


class ScannerError(ValueError):
    """Raised when the requested source boundary cannot be analyzed safely."""


@dataclass(frozen=True)
class Finding:
    rule_id: str
    message: str
    path: str
    line: int
    column: int


class SecurityVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.aliases: Dict[str, str] = {}
        self.findings: List[Finding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for imported in node.names:
            self.aliases[imported.asname or imported.name.split(".", 1)[0]] = imported.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            for imported in node.names:
                self.aliases[imported.asname or imported.name] = "{0}.{1}".format(node.module, imported.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = self._target(node.func)
        if target in {"eval", "exec", "compile", "builtins.eval", "builtins.exec", "builtins.compile"}:
            self._add("python/dynamic-code-execution", "Dynamic code execution requires review.", node)
        elif target in {
            "subprocess.run", "subprocess.call", "subprocess.check_call",
            "subprocess.check_output", "subprocess.Popen",
        } and self._keyword_true(node, "shell"):
            self._add("python/subprocess-shell-true", "subprocess call enables shell=True.", node)
        elif target in {
            "pickle.load", "pickle.loads", "pickle.Unpickler",
            "marshal.load", "marshal.loads",
        }:
            self._add("python/unsafe-deserialization", "Unsafe deserialization requires review.", node)
        elif target == "ssl._create_unverified_context":
            self._add("python/tls-verification-disabled", "TLS certificate verification is disabled.", node)
        self.generic_visit(node)

    def _target(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = self._target(node.value)
            return "{0}.{1}".format(parent, node.attr) if parent else node.attr
        return ""

    @staticmethod
    def _keyword_true(node: ast.Call, name: str) -> bool:
        return any(
            keyword.arg == name and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in node.keywords
        )

    def _add(self, rule_id: str, message: str, node: ast.AST) -> None:
        self.findings.append(Finding(
            rule_id=rule_id,
            message=message,
            path=self.relative_path,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0) + 1,
        ))


def _workspace_root() -> Path:
    return Path.cwd().resolve()


def _source_roots(values: Sequence[str], workspace: Path) -> Tuple[Path, ...]:
    roots: List[Path] = []
    for value in values:
        candidate = Path(value)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ScannerError("source must be a relative path inside the workspace: {0}".format(value))
        requested = workspace
        for part in candidate.parts:
            requested = requested / part
            try:
                metadata = requested.lstat()
            except OSError as error:
                raise ScannerError("could not inspect source: {0}".format(value)) from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ScannerError("source path contains symbolic link: {0}".format(value))
        try:
            metadata = requested.lstat()
        except OSError as error:
            raise ScannerError("could not inspect source: {0}".format(value)) from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise ScannerError("source is not a regular directory: {0}".format(value))
        roots.append(requested)
    if not roots:
        raise ScannerError("at least one source directory is required")
    canonical: List[Path] = []
    for root in sorted(set(roots), key=lambda item: item.as_posix()):
        if any(_is_within(root, existing) for existing in canonical):
            continue
        canonical.append(root)
    return tuple(canonical)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _python_files(roots: Iterable[Path], workspace: Path) -> Tuple[Path, ...]:
    files: List[Path] = []
    total_bytes = 0
    tree_entries = 0
    pending: List[Tuple[Path, int]] = [(root, 0) for root in reversed(tuple(roots))]
    while pending:
        directory, depth = pending.pop()
        entries: List[Tuple[str, Path, os.stat_result]] = []
        try:
            with os.scandir(directory) as stream:
                for entry in stream:
                    tree_entries += 1
                    if tree_entries > MAX_TREE_ENTRIES:
                        raise ScannerError("source traversal exceeds configured entry limit")
                    try:
                        if entry.is_symlink():
                            raise ScannerError(
                                "source tree contains symbolic link: {0}".format(
                                    Path(entry.path).relative_to(workspace).as_posix()
                                )
                            )
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError as error:
                        raise ScannerError("could not inspect source entry: {0}".format(entry.path)) from error
                    path = Path(entry.path)
                    if stat.S_ISDIR(metadata.st_mode):
                        if depth >= MAX_DIRECTORY_DEPTH:
                            raise ScannerError("source traversal exceeds configured directory depth")
                    elif not stat.S_ISREG(metadata.st_mode):
                        raise ScannerError(
                            "source tree contains unsupported filesystem entry: {0}".format(
                                path.relative_to(workspace).as_posix()
                            )
                        )
                    entries.append((entry.name, path, metadata))
        except OSError as error:
            raise ScannerError("could not traverse source directory: {0}".format(directory)) from error

        for _name, path, metadata in reversed(sorted(entries, key=lambda item: item[0])):
            if stat.S_ISDIR(metadata.st_mode):
                pending.append((path, depth + 1))
                continue
            if path.suffix != ".py":
                continue
            try:
                metadata = path.lstat()
            except OSError as error:
                raise ScannerError("could not inspect source file: {0}".format(path)) from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ScannerError("source file is symbolic link: {0}".format(path.relative_to(workspace)))
            if not stat.S_ISREG(metadata.st_mode):
                raise ScannerError("source file is not regular: {0}".format(path.relative_to(workspace)))
            if metadata.st_size > MAX_FILE_BYTES:
                raise ScannerError("source file exceeds byte limit: {0}".format(path.relative_to(workspace)))
            total_bytes += metadata.st_size
            if len(files) >= MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ScannerError("source analysis exceeds configured resource limits")
            files.append(path)
    files = sorted(set(files), key=lambda item: item.relative_to(workspace).as_posix())
    if not files:
        raise ScannerError("source analysis found no Python files")
    return tuple(files)


def _read_source(path: Path, workspace: Path) -> str:
    """Read a regular source file without following a replacement symlink."""
    try:
        before = path.lstat()
    except OSError as error:
        raise ScannerError("could not inspect source file: {0}".format(path)) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ScannerError("source file is not a regular non-symbolic-link file: {0}".format(path.relative_to(workspace)))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(os.fspath(path), flags)
    except OSError as error:
        raise ScannerError("could not read source file: {0}".format(path.relative_to(workspace))) from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ScannerError("source file changed during analysis: {0}".format(path.relative_to(workspace)))
        chunks: List[bytes] = []
        size = 0
        while size <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, min(64 * 1024, MAX_FILE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise ScannerError("source file exceeds byte limit while reading: {0}".format(path.relative_to(workspace)))
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
        ):
            raise ScannerError("source file changed during analysis: {0}".format(path.relative_to(workspace)))
    finally:
        os.close(descriptor)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeError as error:
        raise ScannerError("source file is not UTF-8: {0}".format(path.relative_to(workspace))) from error


def _validate_ast_work(tree: ast.AST, relative: str) -> None:
    """Bound AST traversal before the recursive security visitor runs."""

    for count, _node in enumerate(ast.walk(tree), start=1):
        if count > MAX_AST_NODES:
            raise ScannerError("source AST analysis exceeds configured AST node limit: {0}".format(relative))


def analyze(sources: Sequence[str], workspace: Optional[Path] = None) -> Tuple[Tuple[Finding, ...], Tuple[str, ...]]:
    workspace = (workspace or _workspace_root()).resolve()
    roots = _source_roots(sources, workspace)
    findings: List[Finding] = []
    scanned: List[str] = []
    for path in _python_files(roots, workspace):
        relative = path.relative_to(workspace).as_posix()
        try:
            source = _read_source(path, workspace)
            tree = ast.parse(source, filename=relative)
            _validate_ast_work(tree, relative)
        except SyntaxError as error:
            line = getattr(error, "lineno", 1) or 1
            column = getattr(error, "offset", 1) or 1
            findings.append(Finding(
                "python/unparseable-source", "Could not parse source: {0}".format(error), relative, line, column,
            ))
            scanned.append(relative)
            continue
        except (MemoryError, RecursionError, SystemError, OverflowError) as error:
            raise ScannerError(
                "source AST analysis exceeded interpreter resource limits ({0}): {1}".format(
                    type(error).__name__, relative,
                )
            ) from error
        visitor = SecurityVisitor(relative)
        try:
            visitor.visit(tree)
        except (MemoryError, RecursionError, SystemError, OverflowError) as error:
            raise ScannerError(
                "source AST analysis exceeded interpreter resource limits ({0}): {1}".format(
                    type(error).__name__, relative,
                )
            ) from error
        findings.extend(visitor.findings)
        scanned.append(relative)
    return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.column, item.rule_id))), tuple(scanned)


def sarif(findings: Sequence[Finding], scanned: Sequence[str]) -> Dict[str, object]:
    rules = dict(RULES)
    if any(finding.rule_id == "python/unparseable-source" for finding in findings):
        rules["python/unparseable-source"] = {
            "name": "unparseable-source",
            "shortDescription": {"text": "Unparseable Python source"},
            "fullDescription": {"text": "Analysis cannot continue safely until Python source parses."},
            "defaultConfiguration": {"level": "error"},
        }
    if any(finding.rule_id == "python/analysis-failure" for finding in findings):
        rules["python/analysis-failure"] = {
            "name": "analysis-failure",
            "shortDescription": {"text": "Private static analysis could not complete"},
            "fullDescription": {"text": "The bounded source analysis failed closed before it could establish complete evidence."},
            "defaultConfiguration": {"level": "error"},
        }
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": TOOL_NAME, "rules": [rules[key] | {"id": key} for key in sorted(rules)]}},
            "artifacts": [{"location": {"uri": path}} for path in scanned],
            "results": [{
                "ruleId": finding.rule_id,
                "level": "error",
                "message": {"text": finding.message},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": finding.path},
                    "region": {"startLine": finding.line, "startColumn": finding.column},
                }}],
            } for finding in findings],
        }],
    }


def write_sarif(path: Path, findings: Sequence[Finding], scanned: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sarif(findings, scanned), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create bounded local static-analysis SARIF evidence.")
    parser.add_argument("--source", action="append", required=True, help="Relative source directory to analyze (repeatable).")
    parser.add_argument("--output", required=True, help="SARIF output path.")
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        findings, scanned = analyze(args.source)
        write_sarif(output, findings, scanned)
    except (MemoryError, OSError, ScannerError) as error:
        failure = Finding(
            "python/analysis-failure",
            "Private static analysis could not complete safely: {0}".format(error),
            "analysis://private-static-analysis",
            1,
            1,
        )
        try:
            write_sarif(output, (failure,), ())
        except OSError as write_error:
            print("private static analysis could not write failure SARIF: {0}".format(write_error), file=sys.stderr)
        print("private static analysis failed: {0}".format(error), file=sys.stderr)
        return 2
    print("private static analysis: {0} result(s) across {1} Python file(s)".format(len(findings), len(scanned)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
