# Normal feature example

> Legacy `route` compatibility example. The default `orchestrate` workflow now asks Astra to choose the model and thinking level; see [routing concepts](../concepts.md).

Objective: add export filtering to a report endpoint across three known files with explicit acceptance criteria. This generated `data.route` decision uses the legacy routing policy.

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

In this legacy policy, Terra is the default writable implementation lane. The adaptive policy lets Astra choose Sol or Terra and any supported thinking level. Keep the route bounded, run focused checks, and use the repository validator before handoff. If the work reveals a public-contract, data, auth, or security boundary, return it for a new assessment. See [high-risk change](high-risk-change.md).
