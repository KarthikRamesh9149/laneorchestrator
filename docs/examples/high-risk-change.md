# High-risk change example

Objective: rotate OAuth client credentials. This generated `data.route` decision shows explicit high-risk handling without including credentials or a live environment.

```json
{
  "assessment": {
    "acceptance_criteria": true,
    "files": 2,
    "known_area": true,
    "risk": "high"
  },
  "lane": "sol-plan-terra-sol-review",
  "model": "gpt-5.6-sol",
  "reason": "high-risk signal",
  "reasoning_effort": "high",
  "schema_version": 1,
  "signals": [
    "credentials",
    "oauth"
  ]
}
```

The route requires read-only Sol planning, Terra implementation, and a fresh read-only Sol review. Missing Sol or Terra is a pause condition. Follow the host's approval boundary for any external, destructive, costly, or scope-expanding action. See the [threat model](../threat-model.md).
