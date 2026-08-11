# Command reference

The canonical module command is `python3 -m laneorchestrator` from a source checkout or a resolved installed plugin root. A marketplace-installed user in an arbitrary workspace should use `$laneorchestrator`, which resolves that root before using the module. Every command accepts `--json` for the schema-versioned result envelope. The public command names are `doctor`, `status`, `version`, `configure`, `route`, `catalog`, `profiles`, `voltagent`, and `benchmark`.

## Read-only commands

| Command | Purpose |
| --- | --- |
| `doctor [--json]` | Inspect runtime, configuration, filesystem, and profile readiness. |
| `status [--json]` | Inspect effective configuration and profile state. |
| `version [--json]` | Report package, manifest, and result-schema versions. |
| `route --objective TEXT [--known-area] [--acceptance-criteria] [--files N] [--risk-assessment low|normal|high|unknown] [--json]` | Return a route decision and role availability result. |
| `catalog --query TEXT [--cwd PATH] [--context TEXT] [--skills-root PATH] [--agents-root PATH] [--no-default-roots] [--top-skills N] [--top-agents N] [--unscoped-high-risk] [--json]` | Return bounded capability-index results. |
| `benchmark [--repeat 2..10] [--json]` | Evaluate the committed routing and capability corpora. |
| `voltagent inventory\|status [--json]` | Inspect the bundled pinned VoltAgent specialist pack or its installation state. |

`catalog` treats roots and metadata as untrusted input. It does not execute metadata, follow symbolic links, or install a result.

## Mutating commands

`configure preview --set ROLE.FIELD=VALUE [--json]` creates a preview. `configure apply --token <bound-token> --approval approve:<approval-digest> [--json]` consumes the exact token only after human review and an independently supplied approval for that preview.

`profiles ACTION preview [--json]` and `profiles ACTION apply --token <bound-token> --approval approve:<approval-digest> [--json]` use `ACTION` from `install`, `update`, `adopt`, or `uninstall`. The placeholders are intentionally neither a usable token nor a human-approval event and cannot be used to apply a change.

`voltagent install preview [--json]` prepares the exact 172-profile installation. `voltagent install apply --token <bound-token> --approval approve:<approval-digest> [--json]` installs it only after review. The bundled upstream source is integrity-pinned and MIT-attributed; profiles are namespaced and run as Terra/High specialists. Installation refuses partial packs, drift, collisions, and unsafe plan state.

Native Windows supports read-only commands only in this release. Use WSL for configuration or profile mutation. See [compatibility](compatibility.md) and [troubleshooting](troubleshooting.md).
