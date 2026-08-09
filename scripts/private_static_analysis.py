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
        requested = workspace / candidate
        try:
            metadata = requested.lstat()
        except OSError as error:
            raise ScannerError("could not inspect source: {0}".format(value)) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ScannerError("source is not a regular directory: {0}".format(value))
        path = requested.resolve()
        try:
            path.relative_to(workspace)
        except ValueError as error:
            raise ScannerError("source escapes the workspace: {0}".format(value)) from error
        roots.append(path)
    if not roots:
        raise ScannerError("at least one source directory is required")
    return tuple(sorted(set(roots)))


def _python_files(roots: Iterable[Path], workspace: Path) -> Tuple[Path, ...]:
    files: List[Path] = []
    total_bytes = 0
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            try:
                metadata = path.lstat()
            except OSError as error:
                raise ScannerError("could not inspect source file: {0}".format(path)) from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ScannerError("source file is symbolic link: {0}".format(path.relative_to(workspace)))
            if not stat.S_ISREG(metadata.st_mode):
                continue
            if metadata.st_size > MAX_FILE_BYTES:
                raise ScannerError("source file exceeds byte limit: {0}".format(path.relative_to(workspace)))
            total_bytes += metadata.st_size
            if len(files) >= MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ScannerError("source analysis exceeds configured resource limits")
            files.append(path)
    return tuple(sorted(set(files)))


def analyze(sources: Sequence[str], workspace: Optional[Path] = None) -> Tuple[Tuple[Finding, ...], Tuple[str, ...]]:
    workspace = (workspace or _workspace_root()).resolve()
    roots = _source_roots(sources, workspace)
    findings: List[Finding] = []
    scanned: List[str] = []
    for path in _python_files(roots, workspace):
        relative = path.relative_to(workspace).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as error:
            line = getattr(error, "lineno", 1) or 1
            column = getattr(error, "offset", 1) or 1
            findings.append(Finding(
                "python/unparseable-source", "Could not parse source: {0}".format(error), relative, line, column,
            ))
            scanned.append(relative)
            continue
        visitor = SecurityVisitor(relative)
        visitor.visit(tree)
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
    except (OSError, ScannerError) as error:
        print("private static analysis failed: {0}".format(error), file=sys.stderr)
        return 2
    print("private static analysis: {0} result(s) across {1} Python file(s)".format(len(findings), len(scanned)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
