# Configuration

LaneOrchestrator starts with built-in role defaults and does not require a configuration file. When configuration is present, it is a schema-versioned JSON document under the Codex state directory. `CODEX_HOME`, when set, must name an absolute, resolved, user-owned, non-symlink directory; otherwise Codex's normal home is used.

The logical roles are `router`, `small_task_executor`, `main_implementer`, and `independent_reviewer`. Schema 2 stores role preferences plus a `preset`: `astra-adaptive`, `all-astra`, or `manual`. Existing schema-1 files remain readable without automatic mutation; the next reviewed configuration update writes schema 2 and preserves explicit role values.

Astra coordinates by default. Small tasks prefer Luna/high or Terra/high. For routine implementation Astra chooses Sol or Terra and any supported thinking level from the task's complexity. The model and thinking fields are preferences, not profile pins: actual per-task selections are validated against the active host. Set `preset=manual` for explicit selections or `preset=all-astra` to use Astra throughout while varying thinking.

Unsupported settings require reassessment. A supported-model snapshot, installed profile, host-loaded profile, and observed execution are different evidence. No adaptive fallback is silently applied.

## Safe change workflow

1. Create a `configure preview` with one or more `--set ROLE.FIELD=VALUE` settings.
2. Inspect the proposed destination, actual before/proposed values, content hash, and changed settings.
3. If and only if the preview is correct, supply its exact unexpired bound token and its matching `approve:<approval_digest>` value to `configure apply`.
4. Run `status --json` to confirm the resulting state.

Do not place credentials, tokens, or private paths in configuration. Unknown fields, duplicate keys, control characters, secret-shaped keys, and oversized values are rejected.

## Profiles

Managed profile content does not embed model or thinking preferences. Changing those preferences therefore requires no regeneration. Receipt configuration hashes record historical installation provenance; profile content hashes and ownership continue to detect actual drift. Core profile updates support recognized 0.2.x receipts and preserve exact prior content in private backups.

The specialist pack supports `voltagent update` and `voltagent uninstall`, each with `preview` and `apply` phases. Update recognizes only the exact previously shipped Terra/high pack or the current dynamic pack. A mixture of those known states, including missing targets after interruption, can be recovered with a new reviewed update. Unknown or user-edited content is refused. Uninstall removes only recognized namespaced content. A partial operation never authorizes deleting foreign files.


The four bundled profiles are managed separately from plugin registration. Lifecycle actions are `install`, `update`, `adopt`, and `uninstall`; every action has the same preview-before-apply boundary. A collision, symbolic link, unsafe parent, receipt drift, or changed preview state is refused rather than overwritten.

Plugin removal only removes the registration and cached plugin files. It does not remove profiles or configuration. To recover from a profile conflict, compare the existing file with the bundled profile, reconcile it deliberately, and request a new preview. Do not reuse an earlier token.

See [commands](commands.md) for the exact interface and [security model](security-model.md) for filesystem limitations.
