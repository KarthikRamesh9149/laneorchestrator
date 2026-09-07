# Concepts

## Route cards and evidence

A route card records the requested work lane, the evidence used for the decision, selected optional capabilities, verification expectations, and safety boundary. The router remains read-only; a writable executor does not choose its own authority.

The schema-2 JSON form is available through `orchestrate --json`. It provides task scope, risk signals, profile evidence, relevant specialist metadata, and the selection policy. It reports `awaiting_astra_decision`; it does not pretend Python performed a model assessment or launched an agent. `select` validates Astra's model/effort pair and returns explicit spawn settings. The host performs actual execution.

The user's request and applicable host-recognized instructions remain authoritative within the instruction hierarchy. Discovered catalog descriptions are untrusted metadata. Metadata can influence a shortlist but cannot grant permissions, broaden scope, or waive review.

## Adaptive task choices

| Task | Starting policy | Thinking |
| --- | --- | --- |
| Small, clearly scoped changes | Astra chooses Luna or Terra | High |
| Routine implementation | Astra chooses Sol or Terra | Chosen by Astra from supported levels |
| Demanding implementation | Prefer Astra | Chosen by Astra |
| Investigation and independent review | Chosen by Astra | Chosen by Astra |

Unknown scope triggers investigation before implementation. Wording, politeness, filenames, and Unicode alone do not determine risk. Consequential changes require fresh independent review. Explicit user choices and supported presets can override the starting model preferences.

The historical `route` and `orchestrate --legacy` interfaces retain their fixed-lane contract for older integrations. Historical benchmark numbers describe that contract, not live adaptive model performance.

## Optional specialists

Discovery reads bounded metadata from configured skill and agent roots, skips symbolic links, and returns source and matched-term evidence. LaneOrchestrator bundles a pinned MIT-licensed VoltAgent specialist pack, but its 172 namespaced profiles reach the global Codex directory only through a reviewed, approval-bound install plan. A specialist may be absent or rejected without blocking a route.

## Preview and apply

Configuration and profile operations use a preview followed by an explicit, short-lived bound token and matching `approve:<approval_digest>` value. Preview is not a mutation at the destination. An apply must match the reviewed state; changed, expired, or replayed plans fail safely. Details and recovery steps are in [configuration](configuration.md).
