"""Bounded, deterministic discovery of local skills and custom agents.

Capability metadata is untrusted text.  This module reads only bounded local
metadata and ranks it as text; it never interprets metadata as instructions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .diagnostics import CommandResult, command_result
from .models import codex_home


STOP_WORDS = {"a", "an", "and", "are", "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or", "please", "the", "this", "to", "use", "with", "write"}
VENDOR_TOKENS = {"airtable", "aws", "azure", "cloudflare", "datadog", "figma", "github", "gitlab", "google", "hubspot", "linear", "notion", "openai", "salesforce", "slack", "stripe", "supabase", "twilio", "vercel", "zoom"}
GENERIC_TASK_TOKENS = {"add", "bug", "change", "check", "code", "create", "feature", "fix", "help", "implement", "issue", "make", "review", "task", "test", "update", "work"}
GENERIC_CAPABILITY_TOKENS = {"agent", "assistant", "expert", "generic", "helper", "plan", "planning", "pro", "review", "specialist", "strategy", "test", "testing", "tool", "workflow"}
LANE_AGENT_NAMES = {"laneorchestrator-router", "laneorchestrator-luna-executor", "laneorchestrator-terra-executor", "laneorchestrator-sol-reviewer"}
TRUSTED_SOURCES = {"system", "plugin-cache", "user"}
ROOT_SHARED_LIMITS = {
    "max_skill_files",
    "max_skill_directories",
    "max_skill_entries",
    "max_total_skill_bytes",
    "max_agent_files",
    "max_agent_entries",
    "max_total_agent_bytes",
}
WORD_RE = re.compile(r"[a-z0-9]+(?:[+#]+)?")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOML_FIELD_RE = re.compile(r'^\s*(name|description|model)\s*=\s*"(.*)"\s*$', re.MULTILINE)

# These values are the established discovery safety bounds.  Keep them in one
# immutable object so direct callers and the compatibility CLI share them.
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
MAX_DEFAULT_ANCESTOR_ROOTS = 8
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
    """A bounded local metadata record, never executable capability content."""

    kind: str
    name: str
    description: str
    path: str
    source: str
    score: float = 0
    matched_terms: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiscoveryLimits:
    """Explicit limits for every bounded discovery resource."""

    max_skill_files: int = MAX_SKILL_FILES
    max_skill_depth: int = MAX_SKILL_DEPTH
    max_skill_directories: int = MAX_SKILL_DIRECTORIES
    max_skill_entries: int = MAX_SKILL_ENTRIES
    max_skill_file_bytes: int = MAX_SKILL_FILE_BYTES
    max_total_skill_bytes: int = MAX_TOTAL_SKILL_BYTES
    max_agent_files: int = MAX_AGENT_FILES
    max_agent_entries: int = MAX_AGENT_ENTRIES
    max_agent_file_bytes: int = MAX_AGENT_FILE_BYTES
    max_total_agent_bytes: int = MAX_TOTAL_AGENT_BYTES
    max_results: int = MAX_RESULTS
    max_query_chars: int = MAX_QUERY_CHARS
    max_context_items: int = MAX_CONTEXT_ITEMS
    max_context_chars: int = MAX_CONTEXT_CHARS
    max_explicit_roots: int = MAX_EXPLICIT_ROOTS
    max_capability_name_chars: int = MAX_CAPABILITY_NAME_CHARS
    max_capability_description_chars: int = MAX_CAPABILITY_DESCRIPTION_CHARS
    max_warnings: int = MAX_WARNINGS


DEFAULT_LIMITS = DiscoveryLimits()


@dataclass(frozen=True)
class DiscoveryRequest:
    """An immutable request for bounded local capability discovery."""

    query: str
    roots: Sequence[Path]
    context: Sequence[str]
    limit: int

    def __post_init__(self) -> None:
        if type(self.query) is not str:
            raise ValueError("--query must be a string")
        if not isinstance(self.roots, Sequence) or isinstance(self.roots, (str, bytes)):
            raise ValueError("--roots must be a sequence of paths")
        if not isinstance(self.context, Sequence) or isinstance(self.context, (str, bytes)):
            raise ValueError("--context must be a sequence of strings")
        if type(self.limit) is not int:
            raise ValueError("--limit must be an integer")
        for root in self.roots:
            if not isinstance(root, (str, os.PathLike)):
                raise ValueError("--roots must contain only paths")
        if any(type(item) is not str for item in self.context):
            raise ValueError("--context must contain only strings")
        object.__setattr__(self, "roots", tuple(Path(root).expanduser() for root in self.roots))
        object.__setattr__(self, "context", tuple(self.context))


def tokens(value: str) -> set:
    found = {word for word in WORD_RE.findall(value.lower()) if word not in STOP_WORDS and len(word) > 1}
    return {TOKEN_ALIASES.get(word, word) for word in found}


def source_for(root: Path) -> str:
    """Classify provenance from the resolved location, not a caller path string.

    A path lexically below a managed root can still pass through an intermediate
    symbolic link to an attacker-controlled directory.  Resolving before the
    trust comparison prevents that directory from inheriting the managed root's
    provenance.  Resolution failures are conservatively treated as project
    content, which is not eligible for automatic selection.
    """
    try:
        root_path = root.expanduser().resolve(strict=False)
        home = Path.home().resolve(strict=False)
        configured_home = codex_home().expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return "project"
    if _is_within(root_path, configured_home / "skills" / ".system"):
        return "system"
    if _is_within(root_path, configured_home / "plugins" / "cache"):
        return "plugin-cache"
    if _is_within(root_path, configured_home / "skills"):
        return "user"
    if _is_within(root_path, configured_home / "agents"):
        return "user"
    if _is_within(root_path, home / ".agents" / "skills"):
        return "user"
    return "project"


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether a lexical absolute path is rooted under *parent*."""

    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _read_bounded_regular(path: Path, max_bytes: int, kind: str) -> Tuple[Optional[bytes], int, Optional[str]]:
    """Read at most *max_bytes* from one no-follow regular metadata file."""
    if path.is_symlink():
        return None, 0, "skipped symbolic-link {0} file".format(kind)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        return None, 0, "could not read {0} file".format(kind)
    flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, 0, "skipped non-regular {0} file".format(kind)
        if metadata.st_size > max_bytes:
            return None, max_bytes, "skipped {0} file larger than {1} bytes".format(kind, max_bytes)
        data = os.read(descriptor, max_bytes)
        current = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino) or current.st_size > max_bytes:
            return None, max_bytes, "skipped {0} file larger than {1} bytes".format(kind, max_bytes)
    except OSError:
        return None, 0, "could not read {0} file".format(kind)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return data, len(data), None


def read_bounded_utf8(path: Path, max_bytes: int, kind: str) -> Tuple[Optional[str], int, Optional[str]]:
    data, bytes_read, warning = _read_bounded_regular(path, max_bytes, kind)
    if data is None:
        return None, bytes_read, warning
    try:
        return data.decode("utf-8"), bytes_read, None
    except UnicodeDecodeError:
        return None, bytes_read, "skipped non-UTF-8 {0} file".format(kind)


def read_skill(path: Path, root: Path, max_bytes: int, limits: DiscoveryLimits) -> Tuple[Optional[Capability], int, Optional[str]]:
    data, bytes_read, warning = _read_bounded_regular(path, max_bytes, "skill")
    if data is None:
        if warning == "skipped skill file larger than {0} bytes".format(max_bytes):
            warning = "skipped skill frontmatter exceeding {0} bytes".format(max_bytes)
        return None, bytes_read, warning
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, bytes_read, "skipped non-UTF-8 skill metadata"
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, bytes_read, None
    fields: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip("\"'")
    if not fields.get("name") or not fields.get("description"):
        return None, bytes_read, None
    if len(fields["name"]) > limits.max_capability_name_chars or len(fields["description"]) > limits.max_capability_description_chars:
        return None, bytes_read, "skipped skill metadata with oversized name or description"
    return Capability("skill", fields["name"], fields["description"], str(path.parent), source_for(root)), bytes_read, None


def read_agent(path: Path, root: Path, max_bytes: int, limits: DiscoveryLimits) -> Tuple[Optional[Capability], int, Optional[str]]:
    text, bytes_read, warning = read_bounded_utf8(path, max_bytes, "agent")
    if text is None:
        return None, bytes_read, warning
    fields = dict(TOML_FIELD_RE.findall(text))
    name, description = fields.get("name"), fields.get("description", "")
    if not name or not description:
        return None, bytes_read, None
    if len(name) > limits.max_capability_name_chars or len(description) > limits.max_capability_description_chars:
        return None, bytes_read, "skipped agent metadata with oversized name or description"
    model = fields.get("model", "")
    suffix = " model={0}".format(model) if model else ""
    return Capability("agent", name, description + suffix, str(path), source_for(root)), bytes_read, None


def roots_for(cwd: Path, extra: Sequence[str], no_default_roots: bool) -> List[Path]:
    if no_default_roots:
        roots = [Path(item).expanduser() for item in extra]
        return list(dict.fromkeys(roots))
    ancestors = [cwd, *cwd.parents][:MAX_DEFAULT_ANCESTOR_ROOTS]
    roots = [directory / ".agents" / "skills" for directory in ancestors]
    home = Path.home()
    configured_home = codex_home()
    roots.extend([home / ".agents" / "skills", configured_home / "skills", configured_home / "skills" / ".system", configured_home / "plugins" / "cache"])
    roots.extend(Path(item).expanduser() for item in extra)
    return list(dict.fromkeys(roots))[:MAX_EXPLICIT_ROOTS]


def add_warning(warnings: List[str], message: str, max_warnings: int) -> None:
    if len(warnings) < max_warnings:
        warnings.append(message)
    elif len(warnings) == max_warnings:
        warnings.append("additional discovery warnings omitted")


def _collect_skills(roots: Sequence[Path], limits: DiscoveryLimits) -> Tuple[List[Capability], List[str], Dict[str, int]]:
    found: Dict[str, Capability] = {}
    warnings: List[str] = []
    files_seen = total_bytes = directories_seen = entries_seen = 0
    prioritized_roots = _prioritized_roots(roots)
    trusted_roots = tuple(root for root in prioritized_roots if source_for(root) in TRUSTED_SOURCES)
    ordered_roots = trusted_roots or prioritized_roots
    overall_limits = limits
    for root_index, root in enumerate(ordered_roots):
        if trusted_roots:
            limits = _root_limits(overall_limits, len(ordered_roots), root_index)
        else:
            limits = replace(
                overall_limits,
                max_skill_files=overall_limits.max_skill_files - files_seen,
                max_skill_directories=overall_limits.max_skill_directories - directories_seen,
                max_skill_entries=overall_limits.max_skill_entries - entries_seen,
                max_total_skill_bytes=overall_limits.max_total_skill_bytes - total_bytes,
            )
        if root.is_symlink():
            add_warning(warnings, "skipped symbolic-link skill root", limits.max_warnings)
            continue
        if not root.is_dir():
            continue
        root_files = root_bytes = root_directories = root_entries = 0
        stopped = False
        pending = [(root, 0)]
        while pending and not stopped:
            directory, depth = pending.pop()
            if root_directories >= limits.max_skill_directories:
                add_warning(warnings, "stopped skill discovery after {0} directories".format(limits.max_skill_directories), limits.max_warnings)
                stopped = True
                continue
            root_directories += 1
            try:
                with os.scandir(directory) as iterator:
                    entries = []
                    for entry in iterator:
                        if root_entries >= limits.max_skill_entries:
                            add_warning(warnings, "stopped skill discovery after {0} directory entries".format(limits.max_skill_entries), limits.max_warnings)
                            stopped = True
                            break
                        root_entries += 1
                        entries.append(entry)
            except OSError:
                add_warning(warnings, "could not traverse skill directory", limits.max_warnings)
                continue
            if stopped:
                continue
            child_directories: List[Path] = []
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if entry.name == "SKILL.md":
                    if root_files >= limits.max_skill_files:
                        add_warning(warnings, "stopped skill discovery after {0} files".format(limits.max_skill_files), limits.max_warnings)
                        stopped = True
                        break
                    if root_bytes >= limits.max_total_skill_bytes:
                        add_warning(warnings, "stopped skill discovery after {0} bytes".format(limits.max_total_skill_bytes), limits.max_warnings)
                        stopped = True
                        break
                    capability, bytes_read, warning = read_skill(path, root, min(limits.max_skill_file_bytes, limits.max_total_skill_bytes - root_bytes), limits)
                    root_files += 1
                    root_bytes += bytes_read
                    if warning:
                        add_warning(warnings, warning, limits.max_warnings)
                    if capability:
                        found.setdefault(capability.path, capability)
                elif not entry.is_symlink() and entry.is_dir(follow_symlinks=False):
                    child_directories.append(path)
            if depth >= limits.max_skill_depth:
                if child_directories:
                    add_warning(warnings, "stopped skill traversal below depth {0}".format(limits.max_skill_depth), limits.max_warnings)
                continue
            pending.extend((child, depth + 1) for child in reversed(child_directories))
        files_seen += root_files
        total_bytes += root_bytes
        directories_seen += root_directories
        entries_seen += root_entries
    return list(found.values()), warnings, {"skill_files": files_seen, "skill_directories": directories_seen, "skill_entries": entries_seen, "skill_bytes": total_bytes}


def _collect_agents(roots: Sequence[Path], limits: DiscoveryLimits) -> Tuple[List[Capability], List[str], Dict[str, int]]:
    found: Dict[str, Capability] = {}
    warnings: List[str] = []
    files_seen = entries_seen = total_bytes = 0
    prioritized_roots = _prioritized_roots(roots)
    trusted_roots = tuple(root for root in prioritized_roots if source_for(root) in TRUSTED_SOURCES)
    ordered_roots = trusted_roots or prioritized_roots
    overall_limits = limits
    for root_index, root in enumerate(ordered_roots):
        if trusted_roots:
            limits = _root_limits(overall_limits, len(ordered_roots), root_index)
        else:
            limits = replace(
                overall_limits,
                max_agent_files=overall_limits.max_agent_files - files_seen,
                max_agent_entries=overall_limits.max_agent_entries - entries_seen,
                max_total_agent_bytes=overall_limits.max_total_agent_bytes - total_bytes,
            )
        if root.is_symlink():
            add_warning(warnings, "skipped symbolic-link agent root", limits.max_warnings)
            continue
        if not root.is_dir():
            continue
        root_files = root_entries = root_bytes = 0
        stopped = False
        try:
            with os.scandir(root) as iterator:
                paths = []
                for entry in iterator:
                    if root_entries >= limits.max_agent_entries:
                        add_warning(warnings, "stopped agent discovery after {0} directory entries".format(limits.max_agent_entries), limits.max_warnings)
                        stopped = True
                        break
                    root_entries += 1
                    if entry.name.endswith(".toml"):
                        paths.append(Path(entry.path))
        except OSError:
            add_warning(warnings, "could not traverse agent root", limits.max_warnings)
            continue
        for path in sorted(paths) if not stopped else ():
            if root_files >= limits.max_agent_files:
                add_warning(warnings, "stopped agent discovery after {0} files".format(limits.max_agent_files), limits.max_warnings)
                break
            if root_bytes >= limits.max_total_agent_bytes:
                add_warning(warnings, "stopped agent discovery after {0} bytes".format(limits.max_total_agent_bytes), limits.max_warnings)
                break
            capability, bytes_read, warning = read_agent(path, root, min(limits.max_agent_file_bytes, limits.max_total_agent_bytes - root_bytes), limits)
            root_files += 1
            root_bytes += bytes_read
            if warning:
                add_warning(warnings, warning, limits.max_warnings)
            if capability:
                found[capability.path] = capability
        files_seen += root_files
        entries_seen += root_entries
        total_bytes += root_bytes
    return list(found.values()), warnings, {"agent_files": files_seen, "agent_entries": entries_seen, "agent_bytes": total_bytes}


def collect(roots: Sequence[Path], limits: DiscoveryLimits) -> Tuple[List[Capability], List[str], Mapping[str, int]]:
    """Enumerate local metadata without following symlinks and within limits."""
    _validate_limits(limits)
    _validate_roots(roots, limits)
    root_paths = tuple(Path(root).expanduser() for root in roots)
    skills, skill_warnings, skill_counters = _collect_skills(root_paths, limits)
    agents, agent_warnings, agent_counters = _collect_agents(root_paths, limits)
    counters = dict(skill_counters)
    counters.update(agent_counters)
    return skills + agents, skill_warnings + agent_warnings, counters


def rank(query: str, capabilities: Sequence[Capability], context: Sequence[str]) -> List[Capability]:
    """Rank metadata deterministically as text, retaining transparent matches."""
    items = [item for item in capabilities if item.source in TRUSTED_SOURCES]
    query_tokens, phrase = tokens(query), query.lower().strip()
    context_tokens = tokens(" ".join(context)) - query_tokens
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
            item.score, item.matched_terms = -1.0, []
            continue
        specific_matches = specific_tokens & candidate_tokens
        if specific_tokens and not specific_matches:
            item.score, item.matched_terms = -1.0, []
            continue
        if len(specific_tokens) >= 3 and len(specific_matches) < 2:
            item.score, item.matched_terms = -1.0, []
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
    unique: Dict[str, Capability] = {}
    for item in ranked:
        unique.setdefault(item.name.casefold(), item)
    return list(unique.values())


def validate_request(request: DiscoveryRequest, limits: DiscoveryLimits) -> DiscoveryRequest:
    """Reject requests that would relax the established input bounds."""
    _validate_limits(limits)
    if not request.query.strip():
        raise ValueError("--query must not be blank")
    if len(request.query) > limits.max_query_chars:
        raise ValueError("--query must not exceed {0} characters".format(limits.max_query_chars))
    if len(request.context) > limits.max_context_items:
        raise ValueError("--context may be repeated at most {0} times".format(limits.max_context_items))
    if sum(len(item) for item in request.context) > limits.max_context_chars:
        raise ValueError("combined --context must not exceed {0} characters".format(limits.max_context_chars))
    _validate_roots(request.roots, limits)
    if not 0 <= request.limit <= limits.max_results:
        raise ValueError("--limit must be between 0 and {0}".format(limits.max_results))
    return request


def _validate_limits(limits: DiscoveryLimits) -> None:
    """Allow callers to tighten limits, but never to relax established bounds."""
    defaults = _limits_payload(DEFAULT_LIMITS)
    for item in fields(DiscoveryLimits):
        value = getattr(limits, item.name)
        maximum = defaults[item.name]
        if type(value) is not int or value < 0 or value > maximum:
            raise ValueError("{0} must be between 0 and {1}".format(item.name, maximum))


def _root_limits(limits: DiscoveryLimits, root_count: int, root_index: int) -> DiscoveryLimits:
    """Allocate each global discovery limit deterministically across roots."""

    if root_count <= 0:
        return limits
    values: Dict[str, int] = {}
    for item in fields(DiscoveryLimits):
        total = getattr(limits, item.name)
        if item.name in ROOT_SHARED_LIMITS:
            base, remainder = divmod(total, root_count)
            values[item.name] = base + (1 if root_index < remainder else 0)
        else:
            values[item.name] = total
    return DiscoveryLimits(**values)


def _prioritized_roots(roots: Sequence[Path]) -> Tuple[Path, ...]:
    """Visit provenance-eligible roots before untrusted roots without reordering peers."""

    indexed = enumerate(Path(root).expanduser() for root in roots)
    return tuple(
        root for _index, root in sorted(
            indexed,
            key=lambda pair: (source_for(pair[1]) not in TRUSTED_SOURCES, pair[0]),
        )
    )




def _validate_roots(roots: Sequence[Path], limits: DiscoveryLimits) -> None:
    """Reject an unbounded root set before any path is materialized or read."""
    if len(roots) > limits.max_explicit_roots:
        raise ValueError("explicit roots must not exceed {0} per capability type".format(limits.max_explicit_roots))


def _limits_payload(limits: DiscoveryLimits) -> Dict[str, int]:
    return asdict(limits)


def discovery_result(capabilities: Sequence[Capability], warnings: Sequence[str], counters: Mapping[str, int], limits: DiscoveryLimits) -> CommandResult:
    """Build the typed public envelope for a bounded discovery result."""
    return command_result(
        "discover",
        data={
            "capabilities": [asdict(item) for item in capabilities],
            "warnings": list(warnings),
            "counters": dict(counters),
            "limits": _limits_payload(limits),
        },
    )


def discover(request: DiscoveryRequest, limits: DiscoveryLimits = DEFAULT_LIMITS) -> CommandResult:
    """Discover and rank local metadata deterministically within fixed limits."""
    validated = validate_request(request, limits)
    capabilities, warnings, counters = collect(validated.roots, limits)
    ranked = rank(validated.query, capabilities, validated.context)[:validated.limit]
    return discovery_result(ranked, warnings, counters, limits)


def result_limit(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not 0 <= count <= MAX_RESULTS:
        raise argparse.ArgumentTypeError("must be between 0 and {0}".format(MAX_RESULTS))
    return count


def _legacy_payload(query: str, context: Sequence[str], cwd: Path, capabilities: Sequence[Capability], warnings: Sequence[str], top_skills: int, top_agents: int, unscoped_high_risk: bool, canonical_agents_root: Optional[Path] = None) -> Dict[str, object]:
    skills = rank(query, [item for item in capabilities if item.kind == "skill"], context)
    discovered_agents = [item for item in capabilities if item.kind == "agent"]
    lane_agents = sorted(
        (
            item for item in discovered_agents
            if _is_canonical_lane_agent(item, canonical_agents_root)
        ),
        key=lambda item: item.name,
    )
    agents = rank(query, discovered_agents, context)
    if unscoped_high_risk:
        skills, agents = [], []
    lane_agent_payload = []
    for item in lane_agents:
        payload = asdict(item)
        payload["score"] = None
        payload["role"] = "required-lane"
        lane_agent_payload.append(payload)
    return {
        "schema_version": 1,
        "query": query,
        "context": list(context),
        "cwd": str(cwd),
        "counts": {"skills": len(skills), "agents": len(agents), "lane_agents": len(lane_agents)},
        "warnings": list(warnings),
        "skills": [asdict(item) for item in skills[:top_skills]],
        "agents": [asdict(item) for item in agents[:top_agents]],
        "lane_agents": lane_agent_payload,
    }


def _is_canonical_lane_agent(item: Capability, canonical_agents_root: Optional[Path]) -> bool:
    """Require a reserved role to come from its canonical managed path."""

    if canonical_agents_root is None or item.kind != "agent" or item.name not in LANE_AGENT_NAMES:
        return False
    root = Path(os.path.abspath(os.fspath(canonical_agents_root.expanduser())))
    path = Path(os.path.abspath(item.path))
    if path.parent != root or path.name != item.name + ".toml":
        return False
    data, _bytes_read, _warning = _read_bounded_regular(path, MAX_AGENT_FILE_BYTES, "agent")
    return data is not None and data.startswith(b"# managed-by: laneorchestrator ")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the established catalog CLI, retaining its v1 JSON contract."""
    parser = argparse.ArgumentParser(description="Discover and rank local Codex skills and custom agents without dependencies.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--context", action="append", default=[], help="Verified project or stack context used as a lower-weight ranking signal.")
    parser.add_argument("--skills-root", action="append", default=[])
    parser.add_argument("--agents-root", action="append", default=[])
    parser.add_argument("--no-default-roots", action="store_true")
    parser.add_argument("--top-skills", type=result_limit, default=6)
    parser.add_argument("--top-agents", type=result_limit, default=6)
    parser.add_argument("--unscoped-high-risk", action="store_true", help="Return only mandatory lane roles until project evidence is inspected.")
    args = parser.parse_args(argv)
    if len(args.skills_root) > MAX_EXPLICIT_ROOTS or len(args.agents_root) > MAX_EXPLICIT_ROOTS:
        parser.error("explicit roots must not exceed {0} per capability type".format(MAX_EXPLICIT_ROOTS))
    cwd = Path(args.cwd).resolve()
    skill_roots = roots_for(cwd, args.skills_root, args.no_default_roots)
    managed_agents_root = codex_home() / "agents"
    agent_roots = list(dict.fromkeys(Path(item).expanduser() for item in args.agents_root)) or [managed_agents_root]
    if not args.query.strip():
        parser.error("--query must not be blank")
    if len(args.query) > MAX_QUERY_CHARS:
        parser.error("--query must not exceed {0} characters".format(MAX_QUERY_CHARS))
    if len(args.context) > MAX_CONTEXT_ITEMS:
        parser.error("--context may be repeated at most {0} times".format(MAX_CONTEXT_ITEMS))
    if sum(len(item) for item in args.context) > MAX_CONTEXT_CHARS:
        parser.error("combined --context must not exceed {0} characters".format(MAX_CONTEXT_CHARS))
    # Preserve the legacy split: skills recurse only under skill roots and
    # agents inspect only direct entries under agent roots.
    skills, skill_warnings, _ = _collect_skills(skill_roots, DEFAULT_LIMITS)
    agents, agent_warnings, _ = _collect_agents(agent_roots, DEFAULT_LIMITS)
    capabilities = skills + agents
    payload = _legacy_payload(args.query, args.context, cwd, capabilities, skill_warnings + agent_warnings, args.top_skills, args.top_agents, args.unscoped_high_risk, managed_agents_root)
    print(json.dumps(payload, indent=2))
    return 0
