"""Conservative, auditable routing for LaneOrchestrator tasks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
from typing import Dict, List, Optional, Sequence


MAX_OBJECTIVE_CHARS = 16 * 1024
HIGH_RISK_TERMS = {
    "authentication", "authorization", "auth", "credential", "credentials", "security", "oauth", "sso",
    "rbac", "permission", "permissions", "password", "secret", "secrets", "encryption", "encrypt", "pii", "gdpr",
    "payment", "payments", "refund", "refunds", "billing", "financial", "ledger", "invoice", "invoices",
    "migration", "schema", "database", "backfill", "retention", "purge", "delete", "deletion", "concurrency",
    "idempotency", "deployment", "deploy", "production", "certificate", "certificates", "iam", "rollback",
    "login", "session", "jwt", "oidc", "mfa", "acl", "cors", "tls", "kms", "backup", "restore", "infrastructure",
    "firewall", "tenant", "compliance", "hipaa", "medical", "tax", "settlement", "webhook", "audit", "xss", "csrf",
    "vulnerability", "vulnerabilities", "decrypt", "deployments", "rce", "ssrf", "chargebacks",
}
HIGH_RISK_PHRASES = {
    "access control", "access token", "account recovery", "api key", "bank transfer", "browser origin",
    "data integrity", "data retention", "endpoint response contract", "private key", "public api", "public contract",
    "public rest", "race condition", "response contract", "role based access", "session cookie", "signed webhook",
    "signature verification", "trusted issuer", "version outbound webhook", "webhook payload", "webhook request",
    "audit log", "disaster recovery", "multi factor", "sign in", "tenant isolation", "cross site scripting",
    "credit card", "data breach", "data erasure", "data export", "personal data", "privilege escalation",
    "remote code execution", "sql injection", "web hook", "wire transfer",
    "saml assertion", "signing key", "path traversal", "arbitrary file read", "arbitrary file reads",
}
RISK_TOKEN_ALIASES = {"2fa": "mfa", "authz": "authorization", "authorisation": "authorization", "oauth2": "oauth", "openid": "oidc"}
VALID_RISKS = ("low", "normal", "high", "unknown")
LOW_RISK_ACTIONS = frozenset({"adjust", "amend", "change", "correct", "fix", "rename", "replace", "update"})
LOW_RISK_TARGET_TOKENS = frozenset({
    "alt", "bullet", "caption", "comment", "date", "description", "error", "example", "flag", "grammar", "heading",
    "hint", "label", "link", "placeholder", "punctuation", "sentence", "spelling", "string", "text", "title", "token", "typo",
    "url", "variable", "wording",
})
LOW_RISK_OBJECTIVE_TOKENS = LOW_RISK_ACTIONS | LOW_RISK_TARGET_TOKENS | {
    "a", "accessibility", "an", "anchor", "api", "architecture", "approved", "breadcrumb", "broken", "button", "capitalization", "changelog",
    "checklist", "cli", "client", "code", "color", "command", "component", "contributor", "css", "development", "diagram", "docstring",
    "documented", "documentation", "enum", "error", "established", "existing", "faq", "field", "file", "fixture", "form",
    "glossary", "guide", "help", "in", "issue", "keyboard", "known", "local", "log", "map", "mark", "message", "misleading", "mistake",
    "misspelled", "mock", "model", "name", "note", "notes", "of", "one", "operations", "outdated", "ownership", "page", "panel",
    "payload", "policy", "preferences", "product", "readme", "release", "repository", "response", "sample", "screenshot", "section",
    "setup", "shortcut", "snapshot", "source", "spacing", "stale", "static", "story", "table", "team", "template", "terminology", "test",
    "the", "to", "troubleshooting", "tutorial", "unit",
}
LOW_RISK_CONTEXT_TOKENS = frozenset({
    "accessibility", "api", "architecture", "breadcrumb", "button", "changelog", "cli", "client", "code", "component", "contributor",
    "css", "development", "diagram", "documentation", "docstring", "error", "example", "faq", "form", "guide", "help", "keyboard",
    "local", "log", "mistake", "mock", "operations", "page", "panel", "readme", "release", "repository", "sample", "screenshot", "source", "story", "team", "typo",
    "template", "test", "troubleshooting", "tutorial", "unit",
})


@dataclass(frozen=True)
class RouteFacts:
    """Facts that are required to make a conservative lane recommendation."""

    objective: str
    known_area: bool
    acceptance_criteria: bool
    files: int
    risk: str


def normalize(value: str) -> str:
    """Normalize punctuation so hyphenation cannot evade risk phrases."""
    return " ".join(RISK_TOKEN_ALIASES.get(token, token) for token in re.findall(r"[a-z0-9]+", value.casefold()))


def contains_term(text: str, term: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text))


def validate_route_facts(facts: RouteFacts) -> RouteFacts:
    """Validate a route request before deriving a recommendation."""
    if type(facts) is not RouteFacts:
        raise ValueError("route facts must be a RouteFacts instance")
    if type(facts.objective) is not str:
        raise ValueError("--objective must be a string")
    if type(facts.known_area) is not bool:
        raise ValueError("--known-area must be a boolean")
    if type(facts.acceptance_criteria) is not bool:
        raise ValueError("--acceptance-criteria must be a boolean")
    if type(facts.files) is not int:
        raise ValueError("--files must be an integer")
    if type(facts.risk) is not str:
        raise ValueError("--risk-assessment must be a string")
    if not facts.objective.strip():
        raise ValueError("--objective must not be blank")
    if len(facts.objective.strip()) > MAX_OBJECTIVE_CHARS:
        raise ValueError("--objective must not exceed {0} characters".format(MAX_OBJECTIVE_CHARS))
    if facts.files < 1:
        raise ValueError("--files must be at least 1")
    if facts.risk not in VALID_RISKS:
        raise ValueError("--risk-assessment must be one of: {0}".format(", ".join(VALID_RISKS)))
    return facts


def high_risk_signals(objective: str) -> List[str]:
    """Return normalized, sorted high-risk terms and phrases from an objective."""
    normalized = normalize(objective)
    return sorted(term for term in HIGH_RISK_TERMS | HIGH_RISK_PHRASES if contains_term(normalized, term))


def is_bounded_low_risk_objective(objective: str) -> bool:
    """Allow Luna only for an ASCII-only, bounded editorial objective."""
    if not objective.isascii():
        return False
    tokens = normalize(objective).split()
    token_set = set(tokens)
    return (
        len(tokens) >= 3
        and tokens[0] in LOW_RISK_ACTIONS
        and bool(token_set & LOW_RISK_TARGET_TOKENS)
        and bool(token_set & LOW_RISK_CONTEXT_TOKENS)
        and ("token" not in token_set or {"css", "color"}.issubset(token_set))
        and token_set.issubset(LOW_RISK_OBJECTIVE_TOKENS)
    )


def route_payload(
    facts: RouteFacts,
    lane: str,
    model: str,
    signals: Sequence[str],
    non_ascii_objective: bool = False,
) -> Dict[str, object]:
    """Build the stable v1 JSON payload used by direct and legacy callers."""
    if signals:
        reason = "high-risk signal"
    elif non_ascii_objective:
        reason = "non-ASCII objective requires review"
    elif facts.risk == "high":
        reason = "explicit high-risk assessment"
    elif facts.risk == "unknown":
        reason = "risk assessment required"
    elif lane == "sol-plan-terra-sol-review":
        reason = "low-risk objective not recognized"
    elif lane == "luna":
        reason = "bounded known-area task"
    elif facts.risk == "low":
        reason = "low-risk requirements not met"
    else:
        reason = "default implementation lane"
    return {
        "schema_version": 1,
        "lane": lane,
        "model": model,
        "reasoning_effort": "high",
        "reason": reason,
        "signals": list(signals),
        "assessment": {
            "risk": facts.risk,
            "known_area": facts.known_area,
            "acceptance_criteria": facts.acceptance_criteria,
            "files": facts.files,
        },
    }


def recommend_route(facts: RouteFacts) -> Dict[str, object]:
    """Return the stable v1 route recommendation for validated task facts."""
    facts = validate_route_facts(facts)
    signals = high_risk_signals(facts.objective)
    non_ascii_objective = not facts.objective.isascii()
    bounded_low_risk_objective = is_bounded_low_risk_objective(facts.objective)
    if signals or non_ascii_objective or facts.risk in {"high", "unknown"}:
        lane, model = "sol-plan-terra-sol-review", "gpt-5.6-sol"
    elif facts.risk == "low":
        if bounded_low_risk_objective and facts.known_area and facts.acceptance_criteria and facts.files == 1:
            lane, model = "luna", "gpt-5.6-luna"
        elif not bounded_low_risk_objective:
            lane, model = "sol-plan-terra-sol-review", "gpt-5.6-sol"
        else:
            lane, model = "terra", "gpt-5.6-terra"
    else:
        lane, model = "terra", "gpt-5.6-terra"
    return route_payload(facts, lane, model, signals, non_ascii_objective)


def positive_file_count(value: str) -> int:
    """Parse a strictly positive file count for the legacy argument parser."""
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if count < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return count


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the legacy route command with its established output contract."""
    parser = argparse.ArgumentParser(description="Produce a conservative GPT-5.6 lane recommendation from explicit task facts.")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--known-area", action="store_true")
    parser.add_argument("--acceptance-criteria", action="store_true")
    parser.add_argument("--files", type=positive_file_count, default=2)
    parser.add_argument("--risk-assessment", choices=VALID_RISKS, default="unknown")
    args = parser.parse_args(argv)
    facts = RouteFacts(
        objective=args.objective.strip(),
        known_area=args.known_area,
        acceptance_criteria=args.acceptance_criteria,
        files=args.files,
        risk=args.risk_assessment,
    )
    try:
        route = recommend_route(facts)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(route, indent=2))
    return 0
