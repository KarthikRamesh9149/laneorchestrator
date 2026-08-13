# Command reference

The canonical module command is `python3 -m laneorchestrator` from a source checkout or a resolved installed plugin root. A marketplace-installed user in an arbitrary workspace should use `$laneorchestrator`, which resolves that root before using the module. Every command accepts `--json` for the schema-versioned result envelope. The public command names are `setup`, `doctor`, `status`, `version`, `configure`, `route`, `orchestrate`, `catalog`, `profiles`, `voltagent`, and `benchmark`.

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

## Read-only commands

| Command | Purpose |
| --- | --- |
| `doctor [--json]` | Inspect runtime, configuration, filesystem, and profile readiness. |
| `status [--json]` | Inspect effective configuration and profile state. |
| `version [--json]` | Report package, manifest, and result-schema versions. |
| `route --objective TEXT [--known-area] [--acceptance-criteria] [--files N] [--risk-assessment low|normal|high|unknown] [--json]` | Return a route decision and role availability result. |
| `orchestrate --objective TEXT [route options] [--context TEXT] [--agents-root PATH] [--json]` | Return one combined route card with lane workflow, role evidence, trusted specialist metadata, fallback, and verification requirements. |
| `catalog --query TEXT [--cwd PATH] [--context TEXT] [--skills-root PATH] [--agents-root PATH] [--no-default-roots] [--top-skills N] [--top-agents N] [--unscoped-high-risk] [--json]` | Return bounded capability-index results. |
| `benchmark [--repeat 2..10] [--json]` | Evaluate the committed routing and capability corpora. |
| `voltagent inventory\|status [--json]` | Inspect the bundled pinned VoltAgent specialist pack or its installation state. |

`orchestrate` and `catalog` treat roots and metadata as untrusted input. They do not execute metadata, follow symbolic links, or install a result. `orchestrate` automatically suppresses an optional specialist for high-risk work when no trusted project context was supplied.

## Mutating commands

`configure preview --set ROLE.FIELD=VALUE [--json]` creates a preview. `configure apply --token <bound-token> --approval approve:<approval-digest> [--json]` consumes the exact token only after human review and an independently supplied approval for that preview.

`profiles ACTION preview [--json]` and `profiles ACTION apply --token <bound-token> --approval approve:<approval-digest> [--json]` use `ACTION` from `install`, `update`, `adopt`, or `uninstall`. The placeholders are intentionally neither a usable token nor a human-approval event and cannot be used to apply a change.

`voltagent install preview [--json]` prepares the exact 172-profile installation. `voltagent install apply --token <bound-token> --approval approve:<approval-digest> [--json]` installs it only after review. The bundled upstream source is integrity-pinned and MIT-attributed; profiles are namespaced and run as Terra/High specialists. Installation refuses partial packs, drift, collisions, and unsafe plan state.

Native Windows supports read-only commands only in this release. Use WSL for configuration or profile mutation. See [compatibility](compatibility.md) and [troubleshooting](troubleshooting.md).
