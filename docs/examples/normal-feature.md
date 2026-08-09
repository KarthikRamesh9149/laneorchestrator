# Normal feature example

Objective: add export filtering to a report endpoint across three known files with explicit acceptance criteria. This generated `data.route` decision uses the current routing policy.

```json
{
  "assessment": {
    "acceptance_criteria": true,
    "files": 3,
    "known_area": true,
    "risk": "normal"
  },
  "lane": "terra",
  "model": "gpt-5.6-terra",
  "reason": "default implementation lane",
  "reasoning_effort": "high",
  "schema_version": 1,
  "signals": []
}
```

Terra is the normal writable implementation lane. Keep the route bounded, run focused checks, and use the repository validator before handoff. If the work reveals a public-contract, data, auth, or security boundary, return it for a new assessment. See [high-risk change](high-risk-change.md).
