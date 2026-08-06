# LaneOrchestrator

[![CI](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

LaneOrchestrator is a Codex plugin that turns one task into a visible, conservative execution route:

```text
project evidence -> skills and specialists -> GPT-5.6 lane -> implementation -> verification
```

It gives a read-only Sol router control of task classification, uses Terra for normal implementation, reserves Luna for verified low-risk work, and requires a fresh read-only Sol review for high-risk changes.

## Why use it?

Codex installations can accumulate many skills, agents, and model choices. LaneOrchestrator provides one entry point that:

- inspects the repository before selecting capabilities;
- treats capability metadata as an untrusted index, never as instructions;
- explains the lane, evidence, selected capabilities, verification, and safety state;
- falls back conservatively when risk or model availability is uncertain;
- continues automatically for routine in-scope work while preserving approval boundaries for consequential actions.

## Requirements

- A Codex client that supports local plugins, skills, and custom agents
- Python 3.9 or newer
- macOS or Linux with a POSIX shell
- Access to the configured GPT-5.6 profiles; optional specialists and Luna may fall back to Terra / High

The runtime uses only the Python standard library.

## Install

Clone the repository and register its root through the local-plugin flow supported by your Codex client. The plugin entry point is [.codex-plugin/plugin.json](.codex-plugin/plugin.json).

```bash
git clone https://github.com/KarthikRamesh9149/laneorchestrator.git
cd laneorchestrator
sh scripts/install-agents.sh
sh scripts/install-agents.sh --check
python3 scripts/healthcheck.py
```

The agent installer writes only missing namespaced profiles under `~/.codex/agents`. It refuses collisions and symbolic-link destinations. Preview another target without changing it:

```bash
sh scripts/install-agents.sh --check --target /path/to/agents
```

LaneOrchestrator does not modify shell startup files, global Git settings, hooks, MCP configuration, Codex configuration, or existing agents.

## Use

```text
$laneorchestrator implement OAuth token rotation for this service
```

The router emits a compact decision record before work begins:

```text
Lane: Sol plan -> Terra -> Sol review
Context: repository instructions, authentication service, 4 affected files
Capabilities: security review skill, authentication specialist
Verification: unit tests, integration tests, independent final review
Safety: executing within the repository
```

| Lane | Profile | Appropriate work |
| --- | --- | --- |
| Luna / High | `gpt-5.6-luna` | One known file, explicit acceptance criteria, verified low risk |
| Terra / High | `gpt-5.6-terra` | Default implementation, integration, multi-file, or uncertain work |
| Sol -> Terra -> Sol / High | `gpt-5.6-sol` and `gpt-5.6-terra` | Security, auth, public contracts, financial logic, data integrity, migrations, concurrency, or high blast radius |

For project-owned long-term context, explicitly run `$laneorchestrator init`. This is the only normal operation that writes `.laneorchestrator/BRIEF.md`.

## Inspect the helpers

The routing helper accepts established facts and returns auditable JSON:

```bash
python3 skills/laneorchestrator/scripts/route.py \
  --objective "fix a README typo" \
  --known-area \
  --acceptance-criteria \
  --files 1 \
  --risk-assessment low
```

The catalog can include verified stack context as a lower-weight ranking signal:

```bash
python3 skills/laneorchestrator/scripts/catalog.py \
  --query "fix keyboard navigation" \
  --context "React TypeScript" \
  --cwd .
```

Both helpers emit `schema_version: 1`. Catalog output reports matched terms, source, score, warnings, optional specialists, and mandatory lane profiles separately. `--unscoped-high-risk` suppresses optional capability selection until repository evidence is available.

## Safety model

Unknown risk never selects Luna. High-risk terms override a claimed low-risk assessment as defense in depth, but lexical detection is not treated as a complete security classifier. The read-only router must make the authoritative assessment from repository evidence.

Discovery is bounded by file count, depth, per-file bytes, total bytes, and result count. Skill and agent symbolic links are skipped. Agent installation uses descriptor-relative no-follow operations and never overwrites an existing path.

Read the complete [security model](docs/security-model.md) and [architecture](docs/architecture.md).

## Development

Run the same validation entry point used by CI:

```bash
sh scripts/validate.sh
```

CI runs the suite on Ubuntu and macOS with Python 3.9 and Python 3.13. The suite covers malformed input, capability-ranking quality, untrusted metadata limits, installer collisions and symlinks, end-to-end routing, and a 50-scenario routing matrix.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), [RELEASING.md](RELEASING.md), and [SUPPORT.md](SUPPORT.md).

## Troubleshooting

**A profile reports `conflict`.** The installer found an existing file or link and left it untouched. Compare it with the matching file under `agents/`, then move or reconcile it manually.

**A requested model or agent is unavailable.** The router reports the substitution. Luna and optional specialists may fall back to Terra / High. If Terra is unavailable, or Sol is unavailable for required high-risk planning or review, the route pauses instead of silently weakening the safety boundary. Re-run the profile installer if a bundled profile is missing.

**Capability results are empty.** Use direct objective terms, pass verified stack evidence with `--context`, and inspect `warnings` for skipped roots, symbolic links, or resource limits.

**Windows installation fails.** Secure automatic installation requires POSIX directory-descriptor and no-follow support. Use a POSIX environment or manually copy profiles only after confirming every destination is absent and not a symbolic link.

## Provenance and license

This is a clean-room implementation inspired at a high level by [my-codex](https://github.com/sehoon787/my-codex), [SkillMesh](https://github.com/varunreddy/SkillMesh), [Sol Advisor](https://github.com/DannyMac180/sol-advisor), and [awesome-codex-subagents](https://github.com/VoltAgent/awesome-codex-subagents). No upstream implementation code or prompts are included.

Licensed under the [MIT License](LICENSE). See [NOTICE](NOTICE) for attribution details.
