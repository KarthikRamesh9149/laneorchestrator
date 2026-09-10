# Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Separate experiment completion, external-test results and review acceptance in
  workflow reporting; expose coordination and shared-review overhead separately.
- Add offline pilot summaries and a selectable fixed-Astra baseline for future
  runs while preserving a resumed experiment's original settings.
- Reduce repeated coordination and inspection in dispatch guidance, and require
  explicit acceptance contracts where ambiguity affects verification.
- Record the five-call budget-stopped pilot with retained failures and the
  observed host discovery limitation; no efficiency advantage is claimed.

## [0.3.0] - 2026-09-09

- Add an opt-in, bounded adaptive-versus-fixed executable workflow comparison,
  with external verification, independent review and explicit usage evidence.
- Support exact adoption of initial legacy profiles and migration from receipted
  v0.2.4 installations; retain drift refusal and backup/uninstall checks.
- Add host-ledger usage checks with per-agent counters, call and retry limits,
  unknown-usage handling, and explicit limits on token-budget enforcement.
- Preserve independent review for mixed editorial/security clauses and clarify
  that a review-only request does not automatically require recursive review.

- Rebuild the Astra source quickstart, task-oriented documentation index, adaptive examples, migration recipes and contributor/support guidance. Keep the old fixed-lane examples explicitly isolated as compatibility references.

### Added

- A frozen 200-task and 100-extreme-case adaptive contract corpus, offline evaluator and bounded opt-in live decision sample. Contract scores do not claim end-to-end model accuracy.

- Astra-led task assessment and host-validated model/thinking selection, with adaptive, all-Astra and manual presets.
- Per-task model and thinking support for all four core profiles and 172 bundled specialists.
- Exact legacy specialist upgrades, recognized partial-state recovery and reviewed uninstall.
- Opt-in live implementation smoke checks and separate fixture review, with sanitized evidence and explicit runtime-observation limits.
- One 65-second Astra film combining Codex desktop and CLI demo recreations, a README GIF preview, and reproducible media production tools.

### Changed

- Adaptive cards accept an explicit host-inspected editorial scope, preserving risk evidence while avoiding unnecessary review for verified non-operational wording changes.
- Read-only task intent prevents implementation stages even when the repository is understood; explicit context-based review requirements are preserved without changing the task's complexity classification.

- Routine implementation uses Sol or Terra with thinking chosen by Astra; small scoped work uses Luna/high or Terra/high. Demanding work can use Astra.
- Default orchestration returns schema-2 assessment evidence awaiting an Astra decision. Legacy `route` and `orchestrate --legacy` preserve the prior fixed-lane contract.
- Schema-1 configurations remain readable; reviewed writes use schema 2. Model preferences no longer require profile regeneration after migration.
- Setup and lifecycle previews expose complete proposed content and exact destinations.
- The bounded Luna executor can write within its workspace.

### Security

- Adaptive risk detection normalizes compatibility-width text, invisible format characters and common Cyrillic lookalikes. Incomplete role evidence now returns a validation error instead of a lookup failure. Legacy routing behavior is preserved.

- Consequential implementations require a separate independent review, including Astra implementations.
- Preserve bounded metadata discovery, upstream content pins, explicit lifecycle approval, exact-state checks and user-edit refusal.
- Unsupported host model/thinking combinations are rejected without silent substitution. Disk profile readiness remains separate from host-loaded availability and execution evidence.

## [0.2.4] - 2026-08-13

### Fixed

- Correct the public compatibility statement to distinguish the verified `v0.2.3` CI matrix from evidence required for later revisions.
- Document the pinned marketplace update and removal path, including the separate previewed lifecycle for managed profiles and configuration.

### Security

- Apply the audit's bounded release, metadata, routing, and installer hardening before publication; see the `v0.2.4` release notes for the user-facing boundaries.

## [0.2.3] - 2026-08-13

### Added

- Add the interactive `python3 -m laneorchestrator setup` first-run flow for one reviewed installation of four control profiles and 172 bundled specialists (176 profiles total).
- Add TTY-bound confirmation, combined preview fingerprints, read-only `setup --json` readiness output, resumable core-first recovery, and native-Windows WSL guidance.
- Keep the explicit `profiles` and `voltagent` preview/apply commands available as the advanced automation path.

### Safety

- Require both terminal input and output; piped, redirected, empty, interrupted, or unrecognized confirmations never apply a setup plan.
- Verify the final control-profile doctor checks and specialist-pack status after setup; refuse drift, collisions, partial packs, and unsafe filesystem state.

## [0.2.2] - 2026-08-11

### Added

- Bundle the pinned, MIT-licensed VoltAgent Codex specialist pack (172 profiles) with exact content verification and attribution.
- Add reviewed `voltagent` inventory, status, preview, and approval-bound installation commands.

### Security

- Refuse unsafe plan state, symbolic links, partial installs, profile drift, and collisions before specialist-pack publication.
- Keep the bundled specialists namespaced and Terra/High so they cannot change LaneOrchestrator's Luna/Terra/Sol routing authority.

## [0.2.1] - 2026-08-11

### Security

- Remove local root, directory, and file paths from discovery warnings before they reach JSON output.
- Preserve credential-detection regression coverage without storing a secret-named synthetic value that creates misleading CodeQL evidence.

### Changed

- Advance the protected public installation reference and managed-profile template identity to `v0.2.1`.

## [0.2.0] - 2026-08-11

### Added

- Multi-platform CI across Python 3.9 and current Python.
- Auditable routing facts and normalized high-risk signal detection.
- Verified project-context signals and matched-term evidence in capability ranking.
- Bounded, no-follow discovery for both skill and agent metadata.
- Contributor, security, support, architecture, and threat-model documentation.
- Progressive setup, configuration, compatibility, command, recovery, and benchmark documentation.
- Deterministic route examples, terminal demonstration source, Mermaid architecture source, and self-contained social preview asset.
- Public bug and feature forms with private security-report routing.
- Isolated lifecycle journeys and direct regression replays for routing, discovery, plans, and managed profiles.
- An exactly 100-case deterministic acceptance suite spanning routing, discovery, approvals, fallbacks, installers, archives, malformed inputs, and standalone skill entry points.

### Changed

- Extracted the agent installer into a testable Python module behind the existing shell command.
- Strengthened malformed-input validation and capability deduplication.
- Upgraded CI actions to current Node.js 24 releases pinned by immutable commit SHA.
- Documented the canonical module CLI while retaining legacy helper wrappers through 0.2.0.
- Bounded metadata readers now reject non-regular files before reading them.
- Hardened approval binding, Luna containment, release verification, benchmark integrity, duplicate-key handling, AST/JSON bounds, and trusted capability provenance after the canonical security review.

## 0.1.0 - 2026-08-07

### Added

- Initial LaneOrchestrator plugin with Luna, Terra, and Sol routing lanes.
- Local skill and custom-agent discovery.
- Collision-safe custom-agent installer.
- Routing matrix, end-to-end coverage, and security hardening.
