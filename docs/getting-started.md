# Getting started

LaneOrchestrator is installed as a Codex plugin. From an arbitrary workspace, `$laneorchestrator` is the installed-user entry point; it resolves the installed plugin root before it invokes the bundled module. The direct CLI is useful for source-checkout development and host integrations that have already resolved that installed plugin root.

## Install

Use the marketplace commands shown in the [README](../README.md). They pin the reviewed source to the protected annotated `v0.2.3` release tag. The release ruleset blocks tag updates and deletion; review and explicitly select a new protected release tag for every upgrade.

After installation, ask `$laneorchestrator` to route the work. Do not expect `python3 -m laneorchestrator` to work merely because a marketplace plugin is installed in an unrelated directory. The skill checks readiness before proceeding. For a complete first-run install, resolve the plugin root and run the interactive setup command:

```sh
python3 -m laneorchestrator setup
```

Setup previews all four control profiles and 172 bundled specialists (176 profiles total), asks once for `y` or `yes`, and verifies doctor plus specialist status afterward. It requires a POSIX/WSL TTY on both stdin and stdout; pipes and redirects are refused, and `setup --json` is a read-only readiness response with no prompt or target mutation. If the specialist stage fails after the control profiles succeed, rerun setup after resolving the reported collision or drift. The explicit profile and specialist preview/apply commands remain available below and in the [command reference](commands.md) for advanced, separately reviewed workflows.

If bundled profiles are not exposed by the host, the manual path shows a profile-install preview. Review the destinations and changes, then supply both the exact unexpired bound token and the matching explicit `approve:<approval_digest>` value from that preview only if you approve the apply step.

## Inspect readiness

Run the following source-checkout commands from the source checkout or a resolved installed plugin root. They are read-only and return the stable JSON envelope when `--json` is supplied:

```sh
python3 -m laneorchestrator --help
python3 -m laneorchestrator version --json
python3 -m laneorchestrator doctor --json
python3 -m laneorchestrator status --json
```

The version output contains matching package and manifest versions plus `schema_version: 1`. `doctor` reports environmental findings; `status` reports configuration and profile state without changing it. In a source checkout without a discoverable Codex CLI, `doctor --json` deliberately exits with a structured not-ready result: `ok: false`, no unstructured error, and a `CODEX_CLI` diagnostic. The installed `$laneorchestrator` workflow stops on that failed readiness check. A direct `route --json` command may still compute a local decision from its supplied facts, but it cannot prove host readiness; it cannot execute or authorize that route.

## First route

This bounded source-checkout example is suitable for inspecting route behavior in an environment where the four bundled profiles are available. A host integration must use the resolved installed plugin root for the same direct command:

```sh
python3 -m laneorchestrator route --json --objective "Fix a README typo" --known-area --acceptance-criteria --files 1 --risk-assessment low
```

The `route` result distinguishes the requested lane from the effective lane. If required role availability is unknown or missing, the result reports that failure instead of claiming a usable route. See [commands](commands.md) for flags and [troubleshooting](troubleshooting.md) for recovery.

## Update or remove

The marketplace source is pinned to the release tag you selected. `codex plugin marketplace upgrade laneorchestrator` refreshes that same configured source; it does **not** silently move a pinned installation to a newer tag. Review a newer release first, then switch deliberately:

```sh
codex plugin remove laneorchestrator@laneorchestrator
codex plugin marketplace remove laneorchestrator
codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref vX.Y.Z
codex plugin add laneorchestrator@laneorchestrator
```

Replace `vX.Y.Z` with the reviewed release tag. To remove the plugin without installing a replacement, use only the first two commands. Either path removes the plugin registration and cache; it does not remove LaneOrchestrator-managed profiles or configuration. If you want to remove those separately, create a `profiles uninstall preview` and follow the reviewed lifecycle in the [command reference](commands.md#mutating-commands). Never delete managed profile files by hand.
