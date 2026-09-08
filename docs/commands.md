# Command reference

The canonical module command is `python3 -m laneorchestrator` from a source checkout or a resolved installed plugin root. A marketplace-installed user in an arbitrary workspace should use `$laneorchestrator`, which resolves that root before using the module. Every command accepts `--json` for the schema-versioned result envelope. The public command names are `policy`, `select`, `setup`, `doctor`, `status`, `version`, `configure`, `route`, `orchestrate`, `catalog`, `profiles`, `voltagent`, and `benchmark`.

## Recommended first-run setup

`setup` is the guided path for a fresh or resumable installation of all 176 bundled profiles: four control profiles plus 172 namespaced specialists.

```sh
python3 -m laneorchestrator setup
```

It requires an interactive POSIX/WSL terminal with both stdin and stdout attached to a TTY. It renders one combined preview, then accepts only `y` or `yes`; empty, negative, interrupted, piped, and redirected input cancel or refuse safely. The preview does not reveal raw plan tokens or approval digests. Control profiles are applied first, specialists second, and final doctor/status verification is required. If specialists fail after control profiles succeed, setup returns `SETUP_PARTIAL` and a later run resumes after the reported conflict is resolved.

For automation, inspection, or CI, the JSON form is deliberately noninteractive and read-only:

```sh
python3 -m laneorchestrator setup --json
```

It returns `SETUP_INTERACTIVE_REQUIRED`, the current readiness snapshot, and the command to run interactively. Native Windows returns WSL guidance. The explicit preview/apply commands below remain the advanced path for operators who need separate lifecycle control.

## Everyday use versus integration

Use `$laneorchestrator` in Codex for a task that should actually be implemented. The commands here inspect state, validate selections or manage local files. None is a replacement for the host’s agent execution.

## Read-only commands

| Command | Purpose |
| --- | --- |
| `policy [--json]` | Return adaptive presets and model-selection constraints. |
| `select --decision PATH --host-models PATH --task-kind KIND [--json]` | Validate a host-supported selection; does not launch an agent. |
| `doctor [--json]` | Inspect runtime, configuration, filesystem, and profile readiness. |
| `status [--json]` | Inspect effective configuration and profile state. |
| `version [--json]` | Report package, manifest, and result-schema versions. |
| `route --objective TEXT [--known-area] [--acceptance-criteria] [--files N] [--risk-assessment low|normal|high|unknown] [--json]` | Return a route decision and role availability result. |
| `orchestrate --objective TEXT [route options] [--context TEXT] [--agents-root PATH] [--json]` | Return a schema-2 scope card pending Astra selection; use `--legacy` for the fixed-lane contract. |
| `catalog --query TEXT [--cwd PATH] [--context TEXT] [--skills-root PATH] [--agents-root PATH] [--no-default-roots] [--top-skills N] [--top-agents N] [--unscoped-high-risk] [--json]` | Return bounded capability-index results. |
| `benchmark [--repeat 2..10] [--json]` | Evaluate the committed routing and capability corpora. |
| `voltagent inventory\|status [--json]` | Inspect the bundled pinned VoltAgent specialist pack or its installation state. |

`orchestrate` and `catalog` treat roots and metadata as untrusted input. They do not execute metadata, follow symbolic links, or install a result. `orchestrate` automatically suppresses an optional specialist for high-risk work when no trusted project context was supplied.

## Mutating commands

`configure preview --set ROLE.FIELD=VALUE [--json]` creates a preview. `configure apply --token <bound-token> --approval approve:<approval-digest> [--json]` consumes the exact token only after human review and an independently supplied approval for that preview.

`profiles ACTION preview [--json]` and `profiles ACTION apply --token <bound-token> --approval approve:<approval-digest> [--json]` use `ACTION` from `install`, `update`, `adopt`, or `uninstall`. The placeholders are intentionally neither a usable token nor a human-approval event and cannot be used to apply a change.

`voltagent install preview [--json]` prepares the exact 172-profile installation. `voltagent install apply --token <bound-token> --approval approve:<approval-digest> [--json]` installs it only after review. The bundled upstream source is integrity-pinned and MIT-attributed; profiles are namespaced with model and thinking selected per task. Installation refuses partial packs, drift, collisions, and unsafe plan state.

Native Windows supports read-only commands only in this release. Use WSL for configuration or profile mutation. See [compatibility](compatibility.md) and [troubleshooting](troubleshooting.md).

## Adaptive selection

`policy --json` returns the configured selection preset and task preferences. `orchestrate --json` returns a schema-2 scope card with an explicit pending-decision status. `orchestrate --legacy` preserves the old schema-1 fixed-lane card.

Adaptive scope facts include `--change-scope editorial` for inspected non-operational wording changes, `--read-only-task` for diagnosis or review without implementation, and `--require-independent-review` for consequences identified in context or an explicit user review requirement. Editorial scope suppresses lexical escalation only with low-risk, known-area and acceptance facts and a recognizable editorial target in the objective; risk signals remain visible. These are assertions from the invoking host, not permission grants or runtime evidence. See the [selection policy](../skills/laneorchestrator/references/routing-policy.md) for the exact boundaries.

`select --decision <decision.json> --host-models <host-models.json> --task-kind routine --json` validates Astra's decision and returns explicit `model`, `reasoning_effort`, and fresh-context spawn settings. The decision file contains `model`, `reasoning_effort`, and `reason`. The host file maps model IDs to supported thinking levels. Both files are bounded, regular, non-symlink JSON. The CLI cannot authenticate arbitrary caller-supplied host evidence; the invoking host must obtain it from its active capabilities.

Task kinds are `investigation`, `small`, `routine`, `demanding`, and `review`. Optional `--preset` selects `astra-adaptive`, `all-astra`, or `manual`. `--user-override` reflects an actual explicit user choice; it is not a workaround for unsupported settings. A validation success means ready for dispatch, never executed.

`configure preview --set preset=all-astra` previews a persistent preset change. Schema-1 configurations remain readable; reviewed updates write schema 2. Model preferences no longer trigger installed-profile drift.

`voltagent update preview` and `voltagent uninstall preview` expose complete reviewed specialist changes. Their corresponding `apply --token <bound-token> --approval approve:<approval-digest>` phases are bound to that exact action. Update supports the exact legacy pack and recovery of known partial states; user edits are refused.

## Legacy compatibility example

This returns the older deterministic route payload, not an adaptive execution:

```sh
python3 -m laneorchestrator route --json --objective "Fix a README typo" --known-area --acceptance-criteria --files 1 --risk-assessment low
```

For the adaptive scope card, an integration can run:

```sh
python3 -m laneorchestrator orchestrate --objective "<task>" --json
```

See the [dispatch contract](../skills/laneorchestrator/references/dispatch.md) for decision-file shape and explicit launch settings. Success from `select` means `validated_for_dispatch`, not completed work.

For a fresh specialist-only installation, these are complete command forms. Apply only after reviewing the exact preview:

```sh
python3 -m laneorchestrator voltagent install preview --json
python3 -m laneorchestrator voltagent install apply --token <bound-token> --approval approve:<approval-digest> --json
```
