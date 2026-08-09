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
    "firewall", "tenant", "compliance", "hipaa", "medical", "tax", "settlement", "webhook", "audit",
}
HIGH_RISK_PHRASES = {
    "access control", "access token", "account recovery", "api key", "bank transfer", "browser origin",
    "data integrity", "data retention", "endpoint response contract", "private key", "public api", "public contract",
    "public rest", "race condition", "response contract", "role based access", "session cookie", "signed webhook",
    "signature verification", "trusted issuer", "version outbound webhook", "webhook payload", "webhook request",
    "audit log", "disaster recovery", "multi factor", "sign in", "tenant isolation",
}
RISK_TOKEN_ALIASES = {"oauth2": "oauth", "openid": "oidc"}
VALID_RISKS = ("low", "normal", "high", "unknown")


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


def route_payload(facts: RouteFacts, lane: str, model: str, signals: Sequence[str]) -> Dict[str, object]:
    """Build the stable v1 JSON payload used by direct and legacy callers."""
    if signals:
        reason = "high-risk signal"
    elif facts.risk == "high":
        reason = "explicit high-risk assessment"
    elif facts.risk == "unknown":
        reason = "risk assessment required"
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
    if signals or facts.risk in {"high", "unknown"}:
        lane, model = "sol-plan-terra-sol-review", "gpt-5.6-sol"
    elif facts.risk == "low" and facts.known_area and facts.acceptance_criteria and facts.files == 1:
        lane, model = "luna", "gpt-5.6-luna"
    else:
        lane, model = "terra", "gpt-5.6-terra"
    return route_payload(facts, lane, model, signals)


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
