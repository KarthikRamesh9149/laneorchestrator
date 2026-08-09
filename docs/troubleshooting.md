# Troubleshooting

## A required profile is missing or unknown

Run `doctor --json` or `status --json` to inspect the state. If the host does not expose bundled profiles, request a profile-install preview, review it, and supply a new bound token only when the preview is correct. Do not reuse a token after a changed, expired, or failed plan.

## A profile preview reports a conflict or drift

The lifecycle operation left the existing object untouched. Compare it with the matching bundled profile, resolve the collision deliberately, and request a new preview. Symbolic links, unsafe parent directories, non-regular files, and receipt drift are refusal conditions, not cases to bypass.

## A route pauses

Luna may fall back to Terra. A missing or unknown Terra role pauses implementation. A high-risk route also pauses if required Sol planning or review is missing. Restore the required profile evidence and start a new route assessment; do not downgrade a high-risk route merely to continue.

## Native Windows cannot apply a profile or configuration change

That is expected in this release. Native Windows supports read-only control-plane commands only. Use WSL for mutation workflows, then review the preview and token boundary as usual. Details are in [compatibility](compatibility.md).

## `CODEX_HOME` is rejected

Use an absolute, resolved, user-owned, non-symlink directory. A relative value or a symbolic link is refused before configuration or profile state is written. Set a compliant directory, rerun the read-only `status --json` check, and request a new preview for any mutation; do not try to redirect the state through a link.

## Capability results are empty or incomplete

Use clear objective terms and only verified stack context. Inspect warnings for skipped roots, symbolic links, and resource limits. Discovery is intentionally bounded and no result is installed automatically.

For reproducible non-security problems, use the [bug form](../.github/ISSUE_TEMPLATE/bug.yml). Redact secrets, tokens, private paths, and private repository content. Report vulnerabilities through [SECURITY.md](../SECURITY.md), not a public issue.
