# Getting started

LaneOrchestrator is installed as a Codex plugin. Its skill is the normal entry point; the CLI is useful for inspection and automation.

## Install

Use the marketplace commands shown in the [README](../README.md). `--ref main` is convenient but follows a moving branch, so it is not a content-pinned integrity guarantee.

After installation, ask `$laneorchestrator` to route the work. The skill checks readiness before proceeding. If bundled profiles are not exposed by the host, it shows a profile-install preview. Review the destinations and changes, then supply the exact unexpired bound token only if you approve the apply step.

## Inspect readiness

The following commands are read-only and return the stable JSON envelope when `--json` is supplied:

```sh
python3 -m laneorchestrator --help
python3 -m laneorchestrator version --json
python3 -m laneorchestrator doctor --json
python3 -m laneorchestrator status --json
```

The version output contains matching package and manifest versions plus `schema_version: 1`. `doctor` reports environmental findings; `status` reports configuration and profile state without changing it.

## First route

This bounded example is suitable for inspecting route behavior in an environment where the four bundled profiles are available:

```sh
python3 -m laneorchestrator route --json --objective "Fix a README typo" --known-area --acceptance-criteria --files 1 --risk-assessment low
```

The `route` result distinguishes the requested lane from the effective lane. If required role availability is unknown or missing, the result reports that failure instead of claiming a usable route. See [commands](commands.md) for flags and [troubleshooting](troubleshooting.md) for recovery.
