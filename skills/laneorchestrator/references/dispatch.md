# Explicit model and thinking dispatch

The managed profiles omit `model` and `model_reasoning_effort`. Codex applies those profile fields after explicit spawn settings when present, so old pinned profiles must be migrated and reloaded before dynamic use.

## Before launching

Obtain the model/effort combinations exposed by the active host. Do not copy a capability catalog description or infer entitlement from an installed file. Record a small host snapshot in a temporary JSON file, using this shape:

```json
{"gpt-6-astra":["high","xhigh"],"gpt-5.6-sol":["medium","high"],"gpt-5.6-terra":["medium","high"],"gpt-5.6-luna":["high"]}
```

This is a shape example, not an authoritative or exhaustive capability list. Astra writes a separate decision file:

```json
{"model":"gpt-5.6-sol","reasoning_effort":"medium","reason":"The implementation is understood and needs limited cross-file reasoning."}
```

Validate it from the plugin root:

```sh
python3 -m laneorchestrator select --decision <decision.json> --host-models <host-models.json> --task-kind routine --json
```

Supported task kinds: `investigation`, `small`, `routine`, `demanding`, `review`. Optional `--preset all-astra` or `--preset manual` changes the default policy. Use `--user-override` only for an explicit user instruction, never to bypass a failed validation. The validator checks a host-supplied snapshot; it cannot authenticate the provenance of arbitrary JSON supplied by another caller.

## Launch

Use the exact selected managed agent type from the active host. Pass the returned `model` and `reasoning_effort` as explicit spawn arguments. On hosts exposing `thinking` instead, map `reasoning_effort` to that documented field. Use a fresh bounded packet (`fork_turns="none"` where supported), since full-history forks can prohibit model overrides. Include ownership, relevant inspected context, acceptance criteria, and verification requirements.

Verify that the host-loaded profile does not pin either setting. Disk migration is not proof that a running task reloaded its profiles. If the host still advertises fixed settings, explain that a new task or reload is required. Do not silently dispatch an old Terra/high profile and report Astra/xhigh.

Task model changes occur at dispatch boundaries. If the host cannot change a running agent's settings, start a replacement with a compact evidence handoff. Preserve unrelated working tree changes and ensure overlapping writers are not active together.

## Evidence

Track three distinct states: requested settings, host-accepted launch settings, and runtime-observed settings. Use host events or agent metadata for observations, never an agent's self-description. If the host does not expose the actual model or thinking level, say `unknown`; do not fabricate verification.

`select` returns `validated_for_dispatch`, not `executed`. A launch error requires reassessment or the user's explicit permitted fallback. Do not claim completion until the requested artifact/change and relevant verification exist. Independent review must use a separate agent and the original acceptance criteria plus final diff.
