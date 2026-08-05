#!/usr/bin/env python3
"""Produce a conservative GPT-5.6 lane recommendation from explicit task facts."""

from __future__ import annotations

import argparse
import json

HIGH_RISK_TERMS = {
    "api", "authentication", "authorization", "auth", "credential", "security",
    "payment", "financial", "migration", "schema", "database", "data integrity",
    "concurrency", "race condition", "deployment", "production", "public contract",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--known-area", action="store_true")
    parser.add_argument("--acceptance-criteria", action="store_true")
    parser.add_argument("--files", type=int, default=2)
    args = parser.parse_args()
    lowered = args.objective.lower()
    signals = sorted(term for term in HIGH_RISK_TERMS if term in lowered)
    if signals:
        route = {"lane": "sol-plan-terra-sol-review", "model": "gpt-5.6-sol", "reasoning_effort": "high", "reason": "high-risk signal", "signals": signals}
    elif args.known_area and args.acceptance_criteria and args.files == 1:
        route = {"lane": "luna", "model": "gpt-5.6-luna", "reasoning_effort": "high", "reason": "bounded known-area task", "signals": []}
    else:
        route = {"lane": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "high", "reason": "default implementation lane", "signals": []}
    print(json.dumps(route, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
