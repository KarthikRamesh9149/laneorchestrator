# LaneOrchestrator v0.3.0 install and release readiness

Date: 2026-09-09

Scope: installation, migration, drift refusal, uninstall, marketplace isolation, version alignment, and the release gates needed before public availability. No live model calls were made for this audit. GitHub and the real Codex profiles were inspected read-only during diagnosis; the later real-profile changes used the product's reviewed preview/apply lifecycle.

## Result

The v0.3.0 candidate now has a tested path for clean installation, exact historical adoption, receipted v0.2.4 update, drift refusal, reviewed uninstall, and isolated marketplace add/install/remove. Package and plugin manifests report `0.3.0`. Release documentation still calls it a candidate because the protected tag, tag workflow, release assets, attestation, and public pinned installation do not exist yet.

The latest public tag observed from the Git remote was `v0.2.4`, an annotated tag resolving to commit `42db11050691f2669f95a31dcb5e0a0452bbc084`. Tags `v0.2.0` through `v0.2.4` remain immutable historical releases. The v0.3.0 installation command is documented for use only after the new release evidence is public.

## Real profile diagnosis and recovery

The initial `doctor --json` result failed all four installed control profiles as `bad_mode`. Each file was owned by the current user, had mode `0644`, and had no active LaneOrchestrator receipt. The bytes were recognized repository history rather than unknown user content:

| Profile | Initial SHA-256 | Provenance |
| --- | --- | --- |
| `laneorchestrator-router.toml` | `06b31988a6dcd6092cb43731f3d25a560dfb365d9895c675d45a38d3c5b43c39` | Exact initial repository profile from commit `0620191` |
| `laneorchestrator-luna-executor.toml` | `1de0a4bf0ed0b3f32b8597991b8cc4ea5b3581d0736b4e7bb2dae47a8e9a5567` | Exact v0.1.0 fixture |
| `laneorchestrator-terra-executor.toml` | `5feb09a607e4b92b0cb251173e6ca9e6970f1fd3f256e2dcf58f90e6f972c88f` | Exact v0.1.0 fixture |
| `laneorchestrator-sol-reviewer.toml` | `078a82c418f1688b87b341463dcc59cf89c720e9434d4f3b897b991aa6f1b408` | Exact v0.1.0 fixture |

The router allowlist now recognizes both the initial repository hash and the later v0.1.0 hash. The recovery used `profiles adopt preview` followed by its matching reviewed apply. It did not chmod or overwrite the files outside the lifecycle. A separate reviewed specialist installation added all 172 namespaced profiles.

Fresh read-only verification after recovery reported:

- all four installed control profiles `managed`, with mode `0600` and a four-entry v0.3.0 adoption receipt;
- router SHA-256 `b99b6ad9cc1c5e9a0b1381ffdce1a858c102bbac1ad8f5d296738ce17c7841f3`;
- Luna SHA-256 `8e9eb6b42370eb4ae137d9df2e452789da7d3772823c8b6b5c4308ebbcacc5bb`;
- Terra SHA-256 `41538a08e561d20ac8dedaa1483ed9d7ee1141409c50aee8dd7f31466f297214`;
- reviewer SHA-256 `4076e035e35f8cb1affa125f603a1b6111b26cb12fa0e7b565c886b6f04646ca`;
- specialists: 172 installed, 0 missing, 0 drifted;
- no failing doctor diagnostic.

Codex executable parent-chain trust and model entitlement remain `UNKNOWN`; the host does not expose authoritative evidence for those checks. This does not invalidate the verified disk state, and disk state does not prove that an already-running host reloaded the new profiles. A new task or supported client reload remains required.

## Isolated journey evidence

`tests/test_install_journeys.py` adds two command-line journeys using a fresh temporary `CODEX_HOME` for each test:

1. The exact initial-commit/v0.1.0 profile mix begins as `bad_mode`, succeeds through reviewed adoption, becomes four private v0.3.0 managed profiles, and uninstalls without removing an unrelated profile.
2. A valid receipted v0.2.4 profile set begins as recognized drift against v0.3.0, updates through a bound preview, retains four exact backups, becomes managed v0.3.0 state, and uninstalls while retaining the backups.

Both tests passed. Existing focused tests also passed for clean setup of 4 control profiles plus 172 specialists, resumable partial setup, exact v0.1.0 adoption, user-edit drift refusal, unrelated-file preservation, one-time plan use, installer read-only checks, and a real Codex marketplace add/install/list/remove journey isolated under a temporary home.

From a candidate snapshot containing tracked source plus the intended new files and excluding unrelated duplicate ` 2` files:

- the required acceptance suite passed exactly 100 of 100 cases;
- documentation and version-alignment checks passed;
- deterministic archive build and verification passed;
- the two archive-corruption regressions affected by long new fixture paths passed after their helpers were aligned with the builder's USTAR format.

The full extracted-archive validator was not green at this audit checkpoint because the new workflow benchmark provenance test called `git cat-file` inside a source archive that intentionally has no `.git` directory. That failure belongs to the separate workflow-benchmark change and must be resolved before release. No live workflow benchmark result is claimed here.

## v0.3.0 alignment surfaces

The candidate version is aligned across:

- `laneorchestrator/__init__.py`;
- `plugin.json` and `.codex-plugin/plugin.json`;
- `laneorchestrator.profiles.TEMPLATE_VERSION` and the four checked-in managed profile markers;
- receipt validation in `profiles.py` and `doctor.py`, which continues to accept v0.2.0 through v0.2.4 receipts for reviewed migration;
- release archive names and version-dependent test constants;
- `README.md`, compatibility, getting-started, upgrading, troubleshooting, architecture, roadmap, and `docs/releases/v0.3.0.md`.

The marketplace manifest has no version field, so its repository-local plugin mapping remains unchanged. Historical release notes and tags remain unchanged.

## Release gates

Public release requires all of the following at one exact commit:

1. A clean, synchronized `main` with package, both plugin manifests, profile template version, archive prefix, changelog, release notes, and planned `v0.3.0` tag aligned.
2. Exactly 100 passing acceptance tests and a passing full `scripts/validate.sh` run from the candidate source without unrelated duplicate files.
3. A fresh benchmark report meeting its documented thresholds, with offline contract evidence kept separate from live model decisions and actual task execution.
4. Deterministic tar and zip assets built into an empty directory, successful release verification, and a generated two-entry `SHA256SUMS`.
5. Clean setup, exact legacy adoption, v0.2.4 update, drift refusal, uninstall, isolated marketplace, and post-public pinned installation journeys.
6. A completed deep security review and a fresh independent read-only review with every blocking finding resolved.
7. Verified GitHub metadata, Discussions choice, sole-`main` branch ruleset, and release-tag ruleset before tag creation.
8. One new annotated `v0.3.0` tag at the reviewed commit. The tag must never be moved after publication.
9. A passing tag-triggered release workflow. The release must use that run's exact verified archives and generated `SHA256SUMS`, with its attestation checked.
10. A public unauthenticated link and pinned-install journey after release visibility.

At this checkpoint, gates 1, 2, 3, 6, 7, 8, 9, and 10 still need final or external evidence. The local install lifecycle is ready, but v0.3.0 is not yet a public-release success claim.
