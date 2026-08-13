# Architecture

LaneOrchestrator separates routing authority from writable implementation. The canonical control plane is the dependency-free `laneorchestrator` package and its `python3 -m laneorchestrator` interface from a source checkout or resolved installed plugin root. Marketplace users in an arbitrary workspace invoke `$laneorchestrator`, which resolves that root.

```text
task + repository evidence
          |
          v
read-only Sol router ----> bounded route card ----> optional capability index
          |                                            (untrusted metadata)
          v
Luna executor or Terra executor
          |
          v
verification evidence ----> fresh read-only Sol review for high-risk work
```

Editable Mermaid source is available at [architecture.mmd](assets/architecture.mmd). The [social preview](assets/social-preview.svg) is a standalone XML asset with no script, external reference, or third-party logo.

## Components

- `laneorchestrator.routing` derives a conservative route from explicit facts. Unknown risk and recognized high-risk signals avoid Luna.
- `laneorchestrator.discovery` produces a bounded capability index. It does not execute descriptions or turn them into instructions.
- `laneorchestrator.orchestration` composes routing, role evidence, and trusted structured specialist metadata into the schema-v1 route card returned by `orchestrate`.
- `laneorchestrator.config`, `plans`, and `profiles` own schema validation, preview tokens, and safe lifecycle operations.
- `laneorchestrator.doctor` and `diagnostics` provide readiness and stable result envelopes.
- `laneorchestrator.benchmark` evaluates committed policy corpora.

The legacy `skills/laneorchestrator/scripts/route.py`, `skills/laneorchestrator/scripts/catalog.py`, and `scripts/install_agents.py` remain compatibility wrappers through `0.2.4`; they do not own separate routing, discovery, or mutation policy. The guided `setup` command composes the existing exact profile and specialist plans without replacing their lifecycle boundaries.

## Data flow and failure behavior

Capability descriptions and ranking results remain data. The read-only router may select a candidate for later inspection under the host's instruction hierarchy, but cannot delegate authority to metadata. Luna and optional specialists may fall back to Terra. Missing Terra pauses implementation; missing Sol pauses required high-risk planning or review.

Profile and configuration changes are previewed against an exact state and only applied with a reviewed, unexpired bound token and matching explicit `approve:<approval_digest>` value. Native Windows read-only commands are supported, while mutation is disabled; see [compatibility](compatibility.md) and [security model](security-model.md).
