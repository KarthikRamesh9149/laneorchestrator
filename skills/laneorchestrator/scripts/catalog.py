#!/usr/bin/env python3
"""Discover and rank local Codex skills and custom agents without dependencies."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

STOP_WORDS = {"a", "an", "and", "are", "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or", "please", "the", "this", "to", "use", "with", "write"}
VENDOR_TOKENS = {"airtable", "aws", "azure", "cloudflare", "datadog", "figma", "github", "gitlab", "google", "hubspot", "linear", "notion", "openai", "salesforce", "slack", "stripe", "supabase", "twilio", "vercel", "zoom"}
GENERIC_TASK_TOKENS = {"add", "bug", "change", "check", "code", "create", "feature", "fix", "help", "implement", "issue", "make", "review", "task", "test", "update", "work"}
GENERIC_CAPABILITY_TOKENS = {"agent", "assistant", "expert", "generic", "helper", "plan", "planning", "pro", "review", "specialist", "strategy", "test", "testing", "tool", "workflow"}
LANE_AGENT_NAMES = {"laneorchestrator-router", "laneorchestrator-luna-executor", "laneorchestrator-terra-executor", "laneorchestrator-sol-reviewer"}
WORD_RE = re.compile(r"[a-z0-9]+(?:[+#]+)?")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOML_FIELD_RE = re.compile(r'^\s*(name|description|model)\s*=\s*"(.*)"\s*$', re.MULTILINE)
MAX_SKILL_FILES = 2048
MAX_SKILL_DEPTH = 16
MAX_SKILL_DIRECTORIES = 8192
MAX_SKILL_ENTRIES = 65536
MAX_SKILL_FILE_BYTES = 16 * 1024
MAX_TOTAL_SKILL_BYTES = 32 * 1024 * 1024
MAX_AGENT_FILES = 1024
MAX_AGENT_ENTRIES = 8192
MAX_AGENT_FILE_BYTES = 256 * 1024
MAX_TOTAL_AGENT_BYTES = 8 * 1024 * 1024
MAX_RESULTS = 20
MAX_QUERY_CHARS = 16 * 1024
MAX_CONTEXT_ITEMS = 16
MAX_CONTEXT_CHARS = 32 * 1024
MAX_EXPLICIT_ROOTS = 64
MAX_CAPABILITY_NAME_CHARS = 128
MAX_CAPABILITY_DESCRIPTION_CHARS = 2 * 1024
MAX_WARNINGS = 100
TOKEN_ALIASES = {
    "a11y": "accessibility",
    "auth": "authentication",
    "js": "javascript",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "reactjs": "react",
    "ts": "typescript",
}
SOURCE_BONUS = {
    "project": 0.5,
    "user-or-project": 0.4,
    "system": 0.3,
    "plugin-cache": 0.2,
    "user": 0.1,
}


@dataclass
class Capability:
    kind: str
    name: str
    description: str
    path: str
    source: str
    score: float = 0
    matched_terms: list[str] = field(default_factory=list)


def tokens(value: str) -> set[str]:
    found = {word for word in WORD_RE.findall(value.lower()) if word not in STOP_WORDS and len(word) > 1}
    return {TOKEN_ALIASES.get(word, word) for word in found}


def source_for(root: Path) -> str:
    value = root.expanduser().as_posix()
    if "/.codex/skills/.system" in value:
        return "system"
    if "/.codex/plugins/cache" in value:
        return "plugin-cache"
    if "/.codex/skills" in value:
        return "user"
    if "/.codex/agents" in value:
        return "user"
    if "/.agents/skills" in value:
        return "user-or-project"
    return "project"


def read_bounded_utf8(path: Path, max_bytes: int, kind: str) -> tuple[Optional[str], int, Optional[str]]:
    if path.is_symlink():
        return None, 0, f"skipped symbolic-link {kind} file"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            data = source.read(max_bytes + 1)
    except OSError:
        return None, 0, f"could not read {kind} file"
    if len(data) > max_bytes:
        return None, len(data), f"skipped {kind} file larger than {max_bytes} bytes"
    try:
        return data.decode("utf-8"), len(data), None
    except UnicodeDecodeError:
        return None, len(data), f"skipped non-UTF-8 {kind} file"


def read_skill(path: Path, root: Path, max_bytes: int) -> tuple[Optional[Capability], int, Optional[str]]:
    if path.is_symlink():
        return None, 0, "skipped symbolic-link skill file"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            data = source.read(max_bytes + 1)
    except OSError:
        return None, 0, "could not read skill file"
    truncated = len(data) > max_bytes
    data = data[:max_bytes]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, len(data), "skipped non-UTF-8 skill metadata"
    bytes_read = len(data)
    match = FRONTMATTER_RE.match(text)
    if not match:
        if truncated:
            return None, bytes_read, f"skipped skill frontmatter exceeding {max_bytes} bytes"
        return None, bytes_read, None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"\'')
    if not fields.get("name") or not fields.get("description"):
        return None, bytes_read, None
    if len(fields["name"]) > MAX_CAPABILITY_NAME_CHARS or len(fields["description"]) > MAX_CAPABILITY_DESCRIPTION_CHARS:
        return None, bytes_read, "skipped skill metadata with oversized name or description"
    return Capability("skill", fields["name"], fields["description"], str(path.parent), source_for(root)), bytes_read, None


def read_agent(path: Path, root: Path, max_bytes: int) -> tuple[Optional[Capability], int, Optional[str]]:
    text, bytes_read, warning = read_bounded_utf8(path, max_bytes, "agent")
    if text is None:
        return None, bytes_read, warning
    fields = dict(TOML_FIELD_RE.findall(text))
    name, description = fields.get("name"), fields.get("description", "")
    if not name or not description:
        return None, bytes_read, None
    if len(name) > MAX_CAPABILITY_NAME_CHARS or len(description) > MAX_CAPABILITY_DESCRIPTION_CHARS:
        return None, bytes_read, "skipped agent metadata with oversized name or description"
    model = fields.get("model", "")
    suffix = f" model={model}" if model else ""
    return Capability("agent", name, description + suffix, str(path), source_for(root)), bytes_read, None


def roots_for(cwd: Path, extra: list[str], no_default_roots: bool) -> list[Path]:
    if no_default_roots:
        roots = [Path(item).expanduser() for item in extra]
        return list(dict.fromkeys(roots))
    roots = [directory / ".agents" / "skills" for directory in [cwd, *cwd.parents]]
    home = Path.home()
    roots.extend([home / ".agents" / "skills", home / ".codex" / "skills", home / ".codex" / "skills" / ".system", home / ".codex" / "plugins" / "cache"])
    roots.extend(Path(item).expanduser() for item in extra)
    return list(dict.fromkeys(roots))


def add_warning(warnings: list[str], message: str, max_warnings: int) -> None:
    if len(warnings) < max_warnings:
        warnings.append(message)
    elif len(warnings) == max_warnings:
        warnings.append("additional discovery warnings omitted")


def collect_skills(
    roots: list[Path],
    *,
    max_files: int = MAX_SKILL_FILES,
    max_depth: int = MAX_SKILL_DEPTH,
    max_directories: int = MAX_SKILL_DIRECTORIES,
    max_entries: int = MAX_SKILL_ENTRIES,
    max_file_bytes: int = MAX_SKILL_FILE_BYTES,
    max_total_bytes: int = MAX_TOTAL_SKILL_BYTES,
    max_warnings: int = MAX_WARNINGS,
) -> tuple[list[Capability], list[str]]:
    found: dict[str, Capability] = {}
    warnings: list[str] = []
    files_seen = 0
    total_bytes = 0
    directories_seen = 0
    entries_seen = 0
    for root in roots:
        if root.is_symlink():
            add_warning(warnings, f"skipped symbolic-link skill root: {root}", max_warnings)
            continue
        if not root.is_dir():
            continue
        pending = [(root, 0)]
        while pending:
            directory, depth = pending.pop()
            if directories_seen >= max_directories:
                add_warning(warnings, f"stopped skill discovery after {max_directories} directories", max_warnings)
                return list(found.values()), warnings
            directories_seen += 1
            try:
                with os.scandir(directory) as iterator:
                    entries = []
                    for entry in iterator:
                        if entries_seen >= max_entries:
                            add_warning(warnings, f"stopped skill discovery after {max_entries} directory entries", max_warnings)
                            return list(found.values()), warnings
                        entries_seen += 1
                        entries.append(entry)
            except OSError:
                add_warning(warnings, f"could not traverse skill directory: {directory}", max_warnings)
                continue

            child_directories: list[Path] = []
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if entry.name == "SKILL.md":
                    if files_seen >= max_files:
                        add_warning(warnings, f"stopped skill discovery after {max_files} files", max_warnings)
                        return list(found.values()), warnings
                    if total_bytes >= max_total_bytes:
                        add_warning(warnings, f"stopped skill discovery after {max_total_bytes} bytes", max_warnings)
                        return list(found.values()), warnings
                    capability, bytes_read, warning = read_skill(path, root, min(max_file_bytes, max_total_bytes - total_bytes))
                    files_seen += 1
                    total_bytes += bytes_read
                    if warning:
                        add_warning(warnings, f"{warning}: {path}", max_warnings)
                    if capability:
                        found.setdefault(capability.path, capability)
                elif not entry.is_symlink() and entry.is_dir(follow_symlinks=False):
                    child_directories.append(path)
            if depth >= max_depth:
                if child_directories:
                    add_warning(warnings, f"stopped skill traversal below depth {max_depth}: {directory}", max_warnings)
                continue
            pending.extend((child, depth + 1) for child in reversed(child_directories))
    return list(found.values()), warnings


def collect_agents(
    roots: list[Path],
    *,
    max_files: int = MAX_AGENT_FILES,
    max_entries: int = MAX_AGENT_ENTRIES,
    max_file_bytes: int = MAX_AGENT_FILE_BYTES,
    max_total_bytes: int = MAX_TOTAL_AGENT_BYTES,
    max_warnings: int = MAX_WARNINGS,
) -> tuple[list[Capability], list[str]]:
    found: dict[str, Capability] = {}
    warnings: list[str] = []
    files_seen = 0
    entries_seen = 0
    total_bytes = 0
    for root in roots:
        if root.is_symlink():
            add_warning(warnings, f"skipped symbolic-link agent root: {root}", max_warnings)
            continue
        if not root.is_dir():
            continue
        try:
            with os.scandir(root) as iterator:
                paths = []
                for entry in iterator:
                    if entries_seen >= max_entries:
                        add_warning(warnings, f"stopped agent discovery after {max_entries} directory entries", max_warnings)
                        return list(found.values()), warnings
                    entries_seen += 1
                    if entry.name.endswith(".toml"):
                        paths.append(Path(entry.path))
        except OSError:
            add_warning(warnings, f"could not traverse agent root: {root}", max_warnings)
            continue
        for path in sorted(paths):
            if files_seen >= max_files:
                add_warning(warnings, f"stopped agent discovery after {max_files} files", max_warnings)
                return list(found.values()), warnings
            if total_bytes >= max_total_bytes:
                add_warning(warnings, f"stopped agent discovery after {max_total_bytes} bytes", max_warnings)
                return list(found.values()), warnings
            capability, bytes_read, warning = read_agent(path, root, min(max_file_bytes, max_total_bytes - total_bytes))
            files_seen += 1
            total_bytes += bytes_read
            if warning:
                add_warning(warnings, f"{warning}: {path}", max_warnings)
            if capability:
                found[capability.path] = capability
    return list(found.values()), warnings


def rank(items: list[Capability], query: str, context: str = "") -> list[Capability]:
    query_tokens, phrase = tokens(query), query.lower().strip()
    context_tokens = tokens(context) - query_tokens
    selection_tokens = query_tokens | context_tokens
    specific_tokens = query_tokens - GENERIC_TASK_TOKENS
    document_tokens = [tokens(item.name.replace("-", " ")) | tokens(item.description) for item in items]
    document_frequency = {token: sum(token in document for document in document_tokens) for token in selection_tokens}
    for item in items:
        name_tokens = tokens(item.name.replace("-", " "))
        description_tokens = tokens(item.description)
        candidate_tokens = name_tokens | description_tokens
        candidate_vendors = (name_tokens | description_tokens) & VENDOR_TOKENS
        if candidate_vendors and not (candidate_vendors & selection_tokens):
            item.score = -1.0
            item.matched_terms = []
            continue
        specific_matches = specific_tokens & candidate_tokens
        if specific_tokens and not specific_matches:
            item.score = -1.0
            item.matched_terms = []
            continue
        if len(specific_tokens) >= 3 and len(specific_matches) < 2:
            item.score = -1.0
            item.matched_terms = []
            continue
        item.score = sum((3 if token in name_tokens else 1) * (math.log((len(items) + 1) / (document_frequency[token] + 1)) + 1) for token in query_tokens if token in candidate_tokens)
        item.score += 0.35 * sum((3 if token in name_tokens else 1) * (math.log((len(items) + 1) / (document_frequency[token] + 1)) + 1) for token in context_tokens if token in candidate_tokens)
        if phrase and phrase in item.name.lower().replace("-", " "):
            item.score += 4.0
        elif phrase and phrase in item.description.lower():
            item.score += 1.0
        unmatched_specialty = name_tokens - selection_tokens - GENERIC_TASK_TOKENS - GENERIC_CAPABILITY_TOKENS
        item.score -= 0.5 * len(unmatched_specialty)
        item.score += SOURCE_BONUS.get(item.source, 0)
        item.matched_terms = sorted(selection_tokens & candidate_tokens)
        item.score = round(item.score, 3)
    ranked = sorted((item for item in items if item.score > 0), key=lambda item: (-item.score, item.name, item.path))
    unique: dict[str, Capability] = {}
    for item in ranked:
        unique.setdefault(item.name.casefold(), item)
    return list(unique.values())


def result_limit(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not 0 <= count <= MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"must be between 0 and {MAX_RESULTS}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--context", action="append", default=[], help="Verified project or stack context used as a lower-weight ranking signal.")
    parser.add_argument("--skills-root", action="append", default=[])
    parser.add_argument("--agents-root", action="append", default=[])
    parser.add_argument("--no-default-roots", action="store_true")
    parser.add_argument("--top-skills", type=result_limit, default=6)
    parser.add_argument("--top-agents", type=result_limit, default=6)
    parser.add_argument("--unscoped-high-risk", action="store_true", help="Return only mandatory lane roles until project evidence is inspected.")
    args = parser.parse_args()
    if not args.query.strip():
        parser.error("--query must not be blank")
    if len(args.query) > MAX_QUERY_CHARS:
        parser.error(f"--query must not exceed {MAX_QUERY_CHARS} characters")
    if len(args.context) > MAX_CONTEXT_ITEMS:
        parser.error(f"--context may be repeated at most {MAX_CONTEXT_ITEMS} times")
    if sum(len(item) for item in args.context) > MAX_CONTEXT_CHARS:
        parser.error(f"combined --context must not exceed {MAX_CONTEXT_CHARS} characters")
    if len(args.skills_root) > MAX_EXPLICIT_ROOTS or len(args.agents_root) > MAX_EXPLICIT_ROOTS:
        parser.error(f"explicit roots must not exceed {MAX_EXPLICIT_ROOTS} per capability type")
    cwd = Path(args.cwd).resolve()
    context = " ".join(args.context)
    agent_roots = list(dict.fromkeys(Path(item).expanduser() for item in args.agents_root)) or [Path.home() / ".codex" / "agents"]
    discovered_skills, skill_warnings = collect_skills(roots_for(cwd, args.skills_root, args.no_default_roots))
    skills = rank(discovered_skills, args.query, context)
    discovered_agents, agent_warnings = collect_agents(agent_roots)
    lane_agents = sorted((item for item in discovered_agents if item.name in LANE_AGENT_NAMES), key=lambda item: item.name)
    agents = rank(discovered_agents, args.query, context)
    if args.unscoped_high_risk:
        skills, agents = [], []
    lane_agent_payload = []
    for item in lane_agents:
        payload = asdict(item)
        payload["score"] = None
        payload["role"] = "required-lane"
        lane_agent_payload.append(payload)
    print(json.dumps({"schema_version": 1, "query": args.query, "context": args.context, "cwd": str(cwd), "counts": {"skills": len(skills), "agents": len(agents), "lane_agents": len(lane_agents)}, "warnings": [*skill_warnings, *agent_warnings], "skills": [asdict(item) for item in skills[:args.top_skills]], "agents": [asdict(item) for item in agents[:args.top_agents]], "lane_agents": lane_agent_payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
