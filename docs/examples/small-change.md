# Small change example

Objective: fix a README typo in one known file with explicit acceptance criteria. The following route decision is generated from the current routing policy's `data.route` shape.

```json
{
  "assessment": {
    "acceptance_criteria": true,
    "files": 1,
    "known_area": true,
    "risk": "low"
  },
  "lane": "luna",
  "model": "gpt-5.6-luna",
  "reason": "bounded known-area task",
  "reasoning_effort": "high",
  "schema_version": 1,
  "signals": []
}
```

This is a requested lane, not permission to skip verification. If the Luna role is unavailable, the effective route may use Terra; if a required role is unknown, the command reports failure. See [normal feature](normal-feature.md) and [commands](../commands.md).
