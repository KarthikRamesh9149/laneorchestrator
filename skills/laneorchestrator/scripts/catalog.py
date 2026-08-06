#!/usr/bin/env python3
"""Discover and rank local Codex skills and custom agents without dependencies."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

STOP_WORDS = {"a", "an", "and", "are", "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or", "please", "the", "this", "to", "use", "with", "write"}
VENDOR_TOKENS = {"airtable", "aws", "azure", "cloudflare", "datadog", "figma", "github", "gitlab", "google", "hubspot", "linear", "notion", "openai", "salesforce", "slack", "stripe", "supabase", "twilio", "vercel", "zoom"}
GENERIC_TASK_TOKENS = {"add", "bug", "change", "check", "code", "create", "feature", "fix", "help", "implement", "issue", "make", "review", "task", "test", "update", "work"}
LANE_AGENT_NAMES = {"laneorchestrator-router", "laneorchestrator-luna-executor", "laneorchestrator-terra-executor", "laneorchestrator-sol-reviewer"}
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+.#/-]*")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOML_FIELD_RE = re.compile(r'^\s*(name|description|model)\s*=\s*"(.*)"\s*$', re.MULTILINE)


@dataclass
class Capability:
    kind: str
    name: str
    description: str
    path: str
    source: str
    score: float = 0


def tokens(value: str) -> set[str]:
    return {word for word in WORD_RE.findall(value.lower()) if word not in STOP_WORDS and len(word) > 1}


def source_for(root: Path) -> str:
    value = str(root)
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


def read_skill(path: Path, root: Path) -> Optional[Capability]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"\'')
    if not fields.get("name") or not fields.get("description"):
        return None
    return Capability("skill", fields["name"], fields["description"], str(path.parent), source_for(root))


def read_agent(path: Path, root: Path) -> Optional[Capability]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = dict(TOML_FIELD_RE.findall(text))
    name, description = fields.get("name"), fields.get("description", "")
    if not name or not description:
        return None
    model = fields.get("model", "")
    suffix = f" model={model}" if model else ""
    return Capability("agent", name, description + suffix, str(path), source_for(root))


def roots_for(cwd: Path, extra: list[str], no_default_roots: bool) -> list[Path]:
    if no_default_roots:
        return [Path(item).expanduser() for item in extra]
    roots = [directory / ".agents" / "skills" for directory in [cwd, *cwd.parents]]
    home = Path.home()
    roots.extend([home / ".agents" / "skills", home / ".codex" / "skills", home / ".codex" / "skills" / ".system", home / ".codex" / "plugins" / "cache"])
    roots.extend(Path(item).expanduser() for item in extra)
    return roots


def collect_skills(roots: list[Path]) -> list[Capability]:
    found: dict[str, Capability] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("SKILL.md"):
                capability = read_skill(path, root)
                if capability:
                    found.setdefault(capability.path, capability)
        except OSError:
            pass
    return list(found.values())


def collect_agents(roots: list[Path]) -> list[Capability]:
    found: dict[str, Capability] = {}
    for root in roots:
        if root.is_dir():
            for path in root.glob("*.toml"):
                capability = read_agent(path, root)
                if capability:
                    found[capability.path] = capability
    return list(found.values())


def rank(items: list[Capability], query: str) -> list[Capability]:
    query_tokens, phrase = tokens(query), query.lower().strip()
    specific_tokens = query_tokens - GENERIC_TASK_TOKENS
    document_tokens = [tokens(item.name.replace("-", " ")) | tokens(item.description) for item in items]
    document_frequency = {token: sum(token in document for document in document_tokens) for token in query_tokens}
    for item in items:
        name_tokens = tokens(item.name.replace("-", " "))
        description_tokens = tokens(item.description)
        candidate_vendors = (name_tokens | description_tokens) & VENDOR_TOKENS
        if candidate_vendors and not (candidate_vendors & query_tokens):
            item.score = -1.0
            continue
        specific_matches = specific_tokens & (name_tokens | description_tokens)
        if specific_tokens and not specific_matches:
            item.score = -1.0
            continue
        if len(specific_tokens) >= 3 and not (specific_tokens & name_tokens) and len(specific_matches) < 2:
            item.score = -1.0
            continue
        item.score = sum((3 if token in name_tokens else 1) * (math.log((len(items) + 1) / (document_frequency[token] + 1)) + 1) for token in query_tokens if token in description_tokens or token in name_tokens)
        if phrase and phrase in (item.name + " " + item.description).lower():
            item.score += 6.0
        if item.source in {"project", "user-or-project", "system"}:
            item.score += 0.25
        item.score = round(item.score, 3)
    return sorted((item for item in items if item.score > 0), key=lambda item: (-item.score, item.name, item.path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--skills-root", action="append", default=[])
    parser.add_argument("--agents-root", action="append", default=[])
    parser.add_argument("--no-default-roots", action="store_true")
    parser.add_argument("--top-skills", type=int, default=6)
    parser.add_argument("--top-agents", type=int, default=6)
    parser.add_argument("--unscoped-high-risk", action="store_true", help="Return only mandatory lane roles until project evidence is inspected.")
    args = parser.parse_args()
    cwd = Path(args.cwd).resolve()
    agent_roots = [Path(item).expanduser() for item in args.agents_root] or [Path.home() / ".codex" / "agents"]
    skills = rank(collect_skills(roots_for(cwd, args.skills_root, args.no_default_roots)), args.query)
    discovered_agents = collect_agents(agent_roots)
    lane_agents = sorted((item for item in discovered_agents if item.name in LANE_AGENT_NAMES), key=lambda item: item.name)
    agents = rank(discovered_agents, args.query)
    if args.unscoped_high_risk:
        skills, agents = [], []
    lane_agent_payload = []
    for item in lane_agents:
        payload = asdict(item)
        payload["score"] = None
        payload["role"] = "required-lane"
        lane_agent_payload.append(payload)
    print(json.dumps({"query": args.query, "cwd": str(cwd), "counts": {"skills": len(skills), "agents": len(agents), "lane_agents": len(lane_agents)}, "skills": [asdict(item) for item in skills[:args.top_skills]], "agents": [asdict(item) for item in agents[:args.top_agents]], "lane_agents": lane_agent_payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
