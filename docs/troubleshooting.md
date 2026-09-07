# Troubleshooting

Start with the symptom below. Run module commands from the source checkout, not an arbitrary project directory. Prefix command fragments with `python3 -m laneorchestrator`.

## I installed it but do not see Astra behavior

Check the source you installed. The `v0.2.4` release predates Astra. Use the [source quickstart](getting-started.md) and [migration guide](upgrading.md). After migration, open a new Codex task; a running host can retain the old model-pinned profiles.

## Python says no module named laneorchestrator

Change into the `laneorchestrator` checkout created during setup, then run `doctor --json`. In a different project, invoke the installed `$laneorchestrator` skill in Codex instead. Installing a marketplace plugin does not install a system-wide Python package.

## The host selects Astra but launches another model

Inspect the host-loaded agent definition for `model` and `model_reasoning_effort` pins. Follow both core and specialist migration steps in [upgrading](upgrading.md), then open a new task or reload the client. Do not treat the proposed route as evidence of the actual launch. If the host does not expose runtime settings, report them as unknown.

## The CLI reports a pending decision

This is expected for adaptive `orchestrate`: it supplies scope and constraints. It does not call Astra. The installed skill asks Astra to assess them, validates the selection and dispatches through Codex. A standalone JSON command cannot complete that host workflow.

## Setup or dispatch reports missing Codex or model access

Inspect the `CODEX_CLI` diagnostic and confirm Codex is installed and available to the terminal running setup. Check the active host’s supported model/thinking options separately. A file on disk does not grant model access. Correct the reported missing capability and rerun `doctor --json`; do not force a success result.

## Setup requires a terminal

Run `python3 -m laneorchestrator setup` from the resolved plugin root in a POSIX terminal or WSL. Setup requires both stdin and stdout to be TTYs; piped or redirected input is refused, and only `y` or `yes` confirms the exact combined preview. Use `python3 -m laneorchestrator setup --json` for a read-only readiness result and the command to run interactively. Native Windows should use WSL for setup; read-only commands remain supported natively.

## Setup reports `SETUP_PARTIAL`

The four control profiles were installed and verified, but the specialist stage could not complete. The control installation is retained. Read the reported collision, drift, unsafe path, or pack-integrity error, resolve it deliberately without overwriting unrelated profiles, and rerun `setup`; it will resume the remaining specialist step. Do not reuse an expired preview or approval value.

## A required profile is missing or unknown

Run `doctor --json` or `status --json` to inspect the state. If the host does not expose bundled profiles, request a profile-install preview, review it, and supply its new bound token with the matching `approve:<approval_digest>` value only when the preview is correct. Do not reuse a token or approval after a changed, expired, or failed plan.

## A profile preview reports a conflict or drift

The lifecycle operation left the existing object untouched. Compare it with the matching bundled profile, resolve the collision deliberately, and request a new preview. Symbolic links, unsafe parent directories, non-regular files, and receipt drift are refusal conditions, not cases to bypass.

## A route pauses

In adaptive mode, inspect the active host catalog and loaded profile settings. Astra selects another supported model/effort pair only within the requested policy; no silent substitution is allowed. An old profile with fixed model settings needs [migration and a host reload](upgrading.md). Unknown scope requires investigation, and consequential work still needs independent review. Legacy route commands retain their original fallback rules.

## Native Windows cannot apply a profile or configuration change

That is expected in this release. Native Windows supports read-only control-plane commands only. Use WSL for mutation workflows, then review the preview and token boundary as usual. Details are in [compatibility](compatibility.md).

## `CODEX_HOME` is rejected

Use an absolute, resolved, user-owned, non-symlink directory. A relative value or a symbolic link is refused before configuration or profile state is written. Set a compliant directory, rerun the read-only `status --json` check, and request a new preview for any mutation; do not try to redirect the state through a link.

## Capability results are empty or incomplete

Use clear objective terms and only verified stack context. Inspect warnings for skipped roots, symbolic links, and resource limits. Discovery is intentionally bounded and no result is installed automatically.

For reproducible non-security problems, use the [bug form](../.github/ISSUE_TEMPLATE/bug.yml). Redact secrets, tokens, private paths, and private repository content. Report vulnerabilities through [SECURITY.md](../SECURITY.md), not a public issue.
