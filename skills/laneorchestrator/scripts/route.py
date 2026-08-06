#!/usr/bin/env python3
"""Produce a conservative GPT-5.6 lane recommendation from explicit task facts."""

from __future__ import annotations

import argparse
import json
import re

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


def normalize(value: str) -> str:
    """Normalize punctuation so hyphenation cannot evade risk phrases."""
    return " ".join(RISK_TOKEN_ALIASES.get(token, token) for token in re.findall(r"[a-z0-9]+", value.casefold()))


def contains_term(text: str, term: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text))


def positive_file_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if count < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--known-area", action="store_true")
    parser.add_argument("--acceptance-criteria", action="store_true")
    parser.add_argument("--files", type=positive_file_count, default=2)
    parser.add_argument("--risk-assessment", choices=("low", "normal", "high", "unknown"), default="unknown")
    args = parser.parse_args()
    objective = args.objective.strip()
    if not objective:
        parser.error("--objective must not be blank")
    if len(objective) > MAX_OBJECTIVE_CHARS:
        parser.error(f"--objective must not exceed {MAX_OBJECTIVE_CHARS} characters")

    normalized = normalize(objective)
    signals = sorted(term for term in HIGH_RISK_TERMS | HIGH_RISK_PHRASES if contains_term(normalized, term))
    if signals or args.risk_assessment in {"high", "unknown"}:
        if signals:
            reason = "high-risk signal"
        elif args.risk_assessment == "high":
            reason = "explicit high-risk assessment"
        else:
            reason = "risk assessment required"
        lane, model = "sol-plan-terra-sol-review", "gpt-5.6-sol"
    elif args.risk_assessment == "low" and args.known_area and args.acceptance_criteria and args.files == 1:
        lane, model, reason = "luna", "gpt-5.6-luna", "bounded known-area task"
    else:
        lane, model = "terra", "gpt-5.6-terra"
        reason = "low-risk requirements not met" if args.risk_assessment == "low" else "default implementation lane"
    route = {
        "schema_version": 1,
        "lane": lane,
        "model": model,
        "reasoning_effort": "high",
        "reason": reason,
        "signals": signals,
        "assessment": {
            "risk": args.risk_assessment,
            "known_area": args.known_area,
            "acceptance_criteria": args.acceptance_criteria,
            "files": args.files,
        },
    }
    print(json.dumps(route, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
