# Command reference

The canonical module command is `python3 -m laneorchestrator` from a source checkout or a resolved installed plugin root. A marketplace-installed user in an arbitrary workspace should use `$laneorchestrator`, which resolves that root before using the module. Every command accepts `--json` for the schema-versioned result envelope. The public command names are `doctor`, `status`, `version`, `configure`, `route`, `catalog`, `profiles`, and `benchmark`.

## Read-only commands

| Command | Purpose |
| --- | --- |
| `doctor [--json]` | Inspect runtime, configuration, filesystem, and profile readiness. |
| `status [--json]` | Inspect effective configuration and profile state. |
| `version [--json]` | Report package, manifest, and result-schema versions. |
| `route --objective TEXT [--known-area] [--acceptance-criteria] [--files N] [--risk-assessment low|normal|high|unknown] [--json]` | Return a route decision and role availability result. |
| `catalog --query TEXT [--cwd PATH] [--context TEXT] [--skills-root PATH] [--agents-root PATH] [--no-default-roots] [--top-skills N] [--top-agents N] [--unscoped-high-risk] [--json]` | Return bounded capability-index results. |
| `benchmark [--repeat 2..10] [--json]` | Evaluate the committed routing and capability corpora. |

`catalog` treats roots and metadata as untrusted input. It does not execute metadata, follow symbolic links, or install a result.

## Mutating commands

`configure preview --set ROLE.FIELD=VALUE [--json]` creates a preview. `configure apply --token <bound-token> [--json]` consumes the exact token only after human review.

`profiles ACTION preview [--json]` and `profiles ACTION apply --token <bound-token> [--json]` use `ACTION` from `install`, `update`, `adopt`, or `uninstall`. The placeholder is intentionally not a token and cannot be used to apply a change.

Native Windows supports read-only commands only in this release. Use WSL for configuration or profile mutation. See [compatibility](compatibility.md) and [troubleshooting](troubleshooting.md).
