# Usage controls

Before dispatch, choose a call budget appropriate to the task. A small change may
need no delegated agents. The usage checker defaults to eight calls total and at
most two retries per packet. User limits take precedence within that retry ceiling.

The host records one entry per launch in a temporary ledger. Reserve a `pending`
entry before launching, then update that entry to `completed` or `failed`. Count
coordinator and reviewer calls as well as implementations. Use distinct packet IDs
for distinct work, not to evade retry limits. Keep the ledger outside the product
repository unless the user asks to retain it.

```json
{"schema_version":1,"calls":[{"id":"launch-1","packet":"bug-fix","agent":"python-worker","status":"completed","usage":{"input_tokens":1000,"output_tokens":200,"cached_input_tokens":500}}]}
```

Invoke the module's `usage` command with `--ledger <path>`,
`--packet <next-packet>`, optional `--max-calls`, `--max-retries`, `--max-tokens`,
and `--json`. A blocked launch returns exit 1 with `USAGE_LIMIT` and stop reasons.
The response includes per-packet, per-agent and total observed counters. Null usage means
unknown, never zero; a configured token ceiling blocks subsequent launches when
any call has unknown usage. Cached input is already part of input tokens and is
not added again. Supply incremental per-call counters, not cumulative session totals.

The checker reads a host-supplied snapshot. The host must serialize checking and
reserving a launch so concurrent workers cannot spend the same budget. This
command does not launch agents, enforce a server-side token cap, or cancel work.
One running call can exceed the observed-token threshold before it reports usage.
Use provider output limits and timeouts when supported. It does not estimate
money or infer account-wide usage from local counters.

On exhaustion, return completed work, known usage, unknown counters and the next
unfinished packet. Continue only after the user changes the budget. Do not
silently restart a ledger or switch models to bypass a stop.
