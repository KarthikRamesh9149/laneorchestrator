# Getting started

This guide installs the Astra workflow from `main` and takes you through one task.
`main` is a moving source channel; use a verified release tag for a pinned snapshot.
Existing users should start with [upgrading](upgrading.md).

## 1. Check prerequisites

- Git and Python 3.9–3.14; the runtime uses only the Python standard library.
- Codex with plugin marketplace and custom-agent support, signed in with access to the selected models.
- macOS, Linux or WSL for setup. Native Windows supports read-only commands.
- A normal user-owned source directory. Avoid a symlinked checkout or state directory.

The active Codex host must expose Astra and the model/thinking pairs it selects. A plugin cannot grant model access. See [compatibility](compatibility.md).

## 2. Install from a known directory

From your source-projects directory:

```sh
git clone --branch main https://github.com/KarthikRamesh9149/laneorchestrator.git
cd laneorchestrator
codex plugin marketplace add .
codex plugin add laneorchestrator@laneorchestrator
python3 -m laneorchestrator setup
```

Here `.` is the cloned repository, which includes the marketplace manifest. Keep this checkout: it gives you a known working directory for setup, diagnostics and upgrades. If a marketplace named `laneorchestrator` is already registered, use the [upgrade guide](upgrading.md) instead of adding a competing source.

Setup shows the proposed destinations and a review file with the full content of 176 profiles. Confirm with `y` or `yes` after reviewing it. Enter cancels. Run it interactively: pipes and redirected input are refused. A partial result retains the valid control installation; follow [SETUP_PARTIAL recovery](troubleshooting.md#setup-reports-setup_partial) before retrying.

## 3. Confirm readiness and reload

Still inside the cloned `laneorchestrator` directory:

```sh
python3 -m laneorchestrator doctor --json
python3 -m laneorchestrator status --json
python3 -m laneorchestrator voltagent inventory --json
```

Look for no unresolved required-capability failures, recognized managed profiles, and 172 bundled specialists in inventory. Inventory describes the bundle; it does not prove that the host loaded those profiles. Open a **new Codex task** after installation. If it still exposes the old model-pinned profiles, reload the client and inspect again before dispatch.

## 4. Complete a useful first task

Open a small repository you can edit and send a request with a clear outcome. For example, in an app that already has a settings page:

> `$laneorchestrator Add notification preferences to settings. Save per user and restore them after reload.`

The skill should inspect the relevant code before deciding. An illustrative progress card is:

```text
Task: Persist notification preferences through the existing settings API
Agent: Full-stack specialist
Model / thinking: Sol / high
Reason: Familiar architecture; UI state, persistence and defaults interact
Verify: Reload, failed-save handling and a fresh Astra review
```

This is an example, not a promised choice for every repository. Different inspected scope can justify different settings. Do not include “use Astra” just to activate automatic selection.

A useful final handoff names changed files, checks actually run, review results when required, and unresolved limitations. A printed model name or successful selection validation alone is not completion. See the [full example](examples/normal-feature.md).

## Direct CLI versus installed skill

In a project you want to change, use `$laneorchestrator`. The skill resolves its installed plugin root before invoking the module. Direct module commands must run inside this source checkout or a resolved installed plugin root; installing the plugin does not put a Python package in every workspace.

For direct inspection from the source checkout:

```sh
python3 -m laneorchestrator --help
python3 -m laneorchestrator version --json
python3 -m laneorchestrator setup --json
```

`setup --json` is read-only and returns `SETUP_INTERACTIVE_REQUIRED`, not a completed installation. Use interactive setup to review and apply profiles.

The version output contains matching package and manifest versions plus `schema_version: 1`. `doctor` reports environmental findings; `status` reports configuration and profile state without changing it. In a source checkout without a discoverable Codex CLI, `doctor --json` deliberately exits with a structured not-ready result: `ok: false`, no unstructured error, and a `CODEX_CLI` diagnostic. The installed `$laneorchestrator` workflow stops the affected work when a required capability cannot be established, while treating unknown model entitlement separately. A direct `route --json` command may still compute a local decision from its supplied facts, but it cannot prove host readiness; it cannot execute or authorize that route.

## Next steps

Read [upgrades and removal](upgrading.md), [configuration](configuration.md) or [troubleshooting](troubleshooting.md). The older `route` interface [may still compute a local decision](examples/legacy/small-change.md), but it cannot prove host readiness and cannot execute or authorize work.

For removal, the sequence starts with `codex plugin remove laneorchestrator@laneorchestrator` and `codex plugin marketplace remove laneorchestrator`. This does not remove LaneOrchestrator-managed profiles or configuration; review `profiles uninstall preview` and specialist cleanup first as described in the upgrade guide. A marketplace refresh does **not** silently move a pinned installation to a different release tag.
