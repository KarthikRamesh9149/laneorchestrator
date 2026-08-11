# Getting started

LaneOrchestrator is installed as a Codex plugin. From an arbitrary workspace, `$laneorchestrator` is the installed-user entry point; it resolves the installed plugin root before it invokes the bundled module. The direct CLI is useful for source-checkout development and host integrations that have already resolved that installed plugin root.

## Install

Use the marketplace commands shown in the [README](../README.md). They pin the reviewed source to the protected annotated `v0.2.0` release tag. The release ruleset blocks tag updates and deletion; review and explicitly select a new protected release tag for every upgrade.

After installation, ask `$laneorchestrator` to route the work. Do not expect `python3 -m laneorchestrator` to work merely because a marketplace plugin is installed in an unrelated directory. The skill checks readiness before proceeding. If bundled profiles are not exposed by the host, it shows a profile-install preview. Review the destinations and changes, then supply both the exact unexpired bound token and the matching explicit `approve:<approval_digest>` value from that preview only if you approve the apply step.

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
