# LaneOrchestrator

[![CI](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](docs/compatibility.md)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-blue.svg)](docs/compatibility.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Secure, evidence-driven model and agent routing for Codex.

```text
task + repository evidence -> route card -> bounded implementation -> verification
```

```sh
codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref main
codex plugin add laneorchestrator@laneorchestrator
```

Invoke `$laneorchestrator` for a route card. Third-party agent packs are optional.

```text
$laneorchestrator route and implement this task safely
Lane: Terra
Why: multi-file work or uncertain scope uses the default implementation lane
Safety: workspace execution only
```

On first use, the skill runs `doctor` to check readiness. If the host does not expose required bundled profiles, it shows a preview and waits for explicit approval rather than applying a change automatically.

See the deterministic [90-second terminal demonstration](docs/assets/demo.cast). It contains representative route-card text, not a record of a live installation.

`--ref main` follows a moving branch and is not content-pinned. The marketplace command registers the source; the second command installs the plugin. The runtime has no third-party Python dependencies.

## Start here

[Getting started](docs/getting-started.md) covers the first route and readiness checks. Read [concepts](docs/concepts.md) for lanes and evidence, then use [commands](docs/commands.md) for the canonical CLI. The legacy helper scripts remain compatibility wrappers; new automation should use `python3 -m laneorchestrator`.

The default path works without third-party agents. When available, optional specialists can be shortlisted from bounded metadata; the router must inspect selected candidates before use. Missing mandatory Terra or Sol roles pause the applicable route instead of weakening it.

## Safety and lifecycle

Profile and configuration changes are previewed before they are applied. Review the exact preview and supply its unexpired bound token yourself; the examples intentionally do not contain a usable token. Plugin removal removes registration and cached plugin files; it does not remove managed profiles or configuration.

Read the [security model](docs/security-model.md), [threat model](docs/threat-model.md), and [Windows and Python compatibility](docs/compatibility.md) before relying on mutation workflows. Native Windows supports read-only control-plane commands only; use WSL for profile or configuration mutation.

## Documentation

- [Configuration and recovery](docs/configuration.md)
- [Complete command reference](docs/commands.md)
- [Small, normal, and high-risk examples](docs/examples/small-change.md)
- [Architecture](docs/architecture.md) and [benchmarks](docs/benchmarks.md)
- [Troubleshooting](docs/troubleshooting.md), [roadmap](docs/roadmap.md), and [support](SUPPORT.md)

## Development and community

Run `sh scripts/validate.sh` before opening a pull request. It runs the repository checks and unit suite; [CONTRIBUTING.md](CONTRIBUTING.md) explains the expected evidence and rollback note. See [CHANGELOG.md](CHANGELOG.md), [RELEASING.md](RELEASING.md), [SECURITY.md](SECURITY.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Licensed under the [MIT License](LICENSE). [NOTICE](NOTICE) records clean-room provenance.
