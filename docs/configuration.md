# Configuration

LaneOrchestrator starts with built-in role defaults and does not require a configuration file. When configuration is present, it is a schema-versioned JSON document under the Codex state directory. `CODEX_HOME`, when set, must name an absolute, resolved, user-owned, non-symlink directory; otherwise Codex's normal home is used.

The logical roles are `router`, `small_task_executor`, `main_implementer`, and `independent_reviewer`. In schema v1 their model identities are fixed to Sol, Luna, Terra, and Sol respectively; only `reasoning_effort` is configurable. This preserves Sol's independent high-risk planning and review boundary. The defaults use High effort for every role.

Luna availability may fall back to Terra for a tightly scoped task. That is a runtime availability fallback, not a configuration override. Missing Sol for required high-risk planning or independent review, or missing Terra for implementation, blocks the route rather than weakening it.

## Safe change workflow

1. Create a `configure preview` with one or more `--set ROLE.FIELD=VALUE` settings.
2. Inspect the proposed destination, content hash, and changed settings.
3. If and only if the preview is correct, supply its exact unexpired bound token and its matching `approve:<approval_digest>` value to `configure apply`.
4. Run `status --json` to confirm the resulting state.

Do not place credentials, tokens, or private paths in configuration. Unknown fields, duplicate keys, control characters, secret-shaped keys, and oversized values are rejected.

## Profiles

The four bundled profiles are managed separately from plugin registration. Lifecycle actions are `install`, `update`, `adopt`, and `uninstall`; every action has the same preview-before-apply boundary. A collision, symbolic link, unsafe parent, receipt drift, or changed preview state is refused rather than overwritten.

Plugin removal only removes the registration and cached plugin files. It does not remove profiles or configuration. To recover from a profile conflict, compare the existing file with the bundled profile, reconcile it deliberately, and request a new preview. Do not reuse an earlier token.

See [commands](commands.md) for the exact interface and [security model](security-model.md) for filesystem limitations.
