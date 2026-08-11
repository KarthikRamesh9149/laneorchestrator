# Compatibility

## Runtime contract

LaneOrchestrator's support target is Python 3.9-3.14 with zero runtime dependencies beyond the Python standard library. The package and plugin manifests are versioned together at `0.2.1`, and CLI JSON uses schema version `1`.

The configured release CI matrix is Ubuntu and macOS on Python 3.9 and 3.14, plus an explicit Windows 3.9/3.14 read-only control-plane partition. This configuration has not yet supplied live run evidence for the expanded matrix; local validation in this checkout used Python 3.9 only. Python 3.14 and Windows runner results remain required release evidence before publication.

## Operating systems

macOS and Linux support the read-only control plane and POSIX mutation controls. On Windows, use WSL for Windows mutation. Native Windows supports read-only control-plane commands only; profile and configuration mutation are disabled because equivalent reparse-point protections are not verified.

`CODEX_HOME`, when supplied, must be an absolute, resolved, user-owned, non-symlink directory. A Codex client with Plugin Marketplace support is required for the marketplace installation workflow.

## Compatibility behavior

The legacy `route.py`, `catalog.py`, and installer scripts are compatibility wrappers through version `0.2.1`. The canonical module interface is `python3 -m laneorchestrator` from a source checkout or resolved installed plugin root; marketplace users in an arbitrary workspace use `$laneorchestrator`. Plugin removal does not remove managed profiles or configuration; lifecycle cleanup remains explicit and previewed.

See [getting started](getting-started.md), [commands](commands.md), and [security model](security-model.md).
