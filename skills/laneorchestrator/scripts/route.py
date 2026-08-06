#!/usr/bin/env python3
"""Produce a conservative GPT-5.6 lane recommendation from explicit task facts."""

from __future__ import annotations

import argparse
import json
import re

HIGH_RISK_TERMS = {
    "authentication", "authorization", "auth", "credential", "security", "oauth", "sso",
    "rbac", "permission", "password", "secret", "secrets", "encryption", "encrypt", "pii", "gdpr", "payment", "refund", "refunds",
    "billing", "financial", "ledger", "invoice", "invoices", "migration", "schema", "database",
    "backfill", "retention", "purge", "delete", "concurrency", "race condition",
    "idempotency", "deployment", "production",
}
HIGH_RISK_PHRASES = {
    "bank transfer", "data integrity", "data retention", "endpoint response contract", "role-based access",
    "public api", "public rest", "public contract", "response contract", "signed webhook",
    "signature verification", "version outbound webhook", "webhook payload", "webhook request",
}


def contains_term(text: str, term: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--known-area", action="store_true")
    parser.add_argument("--acceptance-criteria", action="store_true")
    parser.add_argument("--files", type=int, default=2)
    parser.add_argument("--risk-assessment", choices=("low", "normal", "high", "unknown"), default="unknown")
    args = parser.parse_args()
    lowered = args.objective.lower()
    signals = sorted(term for term in HIGH_RISK_TERMS | HIGH_RISK_PHRASES if contains_term(lowered, term))
    if signals or args.risk_assessment in {"high", "unknown"}:
        if signals:
            reason = "high-risk signal"
        elif args.risk_assessment == "high":
            reason = "explicit high-risk assessment"
        else:
            reason = "risk assessment required"
        route = {"lane": "sol-plan-terra-sol-review", "model": "gpt-5.6-sol", "reasoning_effort": "high", "reason": reason, "signals": signals}
    elif args.risk_assessment == "low" and args.known_area and args.acceptance_criteria and args.files == 1:
        route = {"lane": "luna", "model": "gpt-5.6-luna", "reasoning_effort": "high", "reason": "bounded known-area task", "signals": []}
    else:
        route = {"lane": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "high", "reason": "default implementation lane", "signals": []}
    print(json.dumps(route, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
