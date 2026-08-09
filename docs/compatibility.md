# Compatibility

## Runtime contract

LaneOrchestrator's support target is Python 3.9-3.14 with zero runtime dependencies beyond the Python standard library. The package and plugin manifests are versioned together at `0.2.0`, and CLI JSON uses schema version `1`.

Current repository CI evidence is Ubuntu and macOS on Python 3.9 and 3.13. The 3.9-3.14 target is the approved release compatibility contract; expanded matrix evidence is tracked as release work and should be verified before publication.

## Operating systems

macOS and Linux support the read-only control plane and POSIX mutation controls. On Windows, use WSL for Windows mutation. Native Windows supports read-only control-plane commands only; profile and configuration mutation are disabled because equivalent reparse-point protections are not verified.

`CODEX_HOME`, when supplied, must be absolute. A Codex client with Plugin Marketplace support is required for the marketplace installation workflow.

## Compatibility behavior

The legacy `route.py`, `catalog.py`, and installer scripts are compatibility wrappers through version `0.2.0`. The canonical interface is `python3 -m laneorchestrator`. Plugin removal does not remove managed profiles or configuration; lifecycle cleanup remains explicit and previewed.

See [getting started](getting-started.md), [commands](commands.md), and [security model](security-model.md).
