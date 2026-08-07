# Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Multi-platform CI across Python 3.9 and current Python.
- Auditable routing facts and normalized high-risk signal detection.
- Verified project-context signals and matched-term evidence in capability ranking.
- Bounded, no-follow discovery for both skill and agent metadata.
- Contributor, security, support, architecture, and threat-model documentation.

### Changed

- Extracted the agent installer into a testable Python module behind the existing shell command.
- Strengthened malformed-input validation and capability deduplication.
- Upgraded CI actions to current Node.js 24 releases pinned by immutable commit SHA.

## 0.1.0 - 2026-08-07

### Added

- Initial LaneOrchestrator plugin with Luna, Terra, and Sol routing lanes.
- Local skill and custom-agent discovery.
- Collision-safe custom-agent installer.
- Routing matrix, end-to-end coverage, and security hardening.
