# LaneOrchestrator

[![CI](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/KarthikRamesh9149/laneorchestrator/actions/workflows/ci.yml)
[![Python 3.9–3.14](https://img.shields.io/badge/Python-3.9--3.14-blue.svg)](docs/compatibility.md)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-blue.svg)](docs/compatibility.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Route Codex work with evidence, not guesswork.

LaneOrchestrator is the safety-aware task router for Codex. It turns a task and its repository context into an auditable execution path: simple, well-bounded work stays fast; normal implementation goes to the right lane; elevated-risk work stops for independent planning and review.

```text
Without LaneOrchestrator                  With LaneOrchestrator
────────────────────────                  ────────────────────
"Fix the billing screen"                  "Fix the billing screen"
        ↓                                          ↓
One opaque agent choice                   Scope + risk + repository evidence
        ↓                                          ↓
Hope the task was interpreted well        A route card, safety boundary, and
                                           the right execution lane
```

```text
task + repository evidence
          ↓
      route card
          ↓
Luna / Terra / Sol → Terra → Sol
          ↓
    verification and handoff
```

It is a control plane, not an autopilot: task text, metadata, paths, and rankings are treated as untrusted input; the router stays read-only; and profile or configuration changes require an explicit preview and approval.

## Install and try it

Install the reviewed `v0.2.2` release, then ask Codex to use the skill from any workspace:

```sh
codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref v0.2.2
codex plugin add laneorchestrator@laneorchestrator
```

```text
$laneorchestrator route and implement this task safely

Lane: Terra
Why: multi-file work or uncertain scope uses the default implementation lane
Safety: workspace execution only
```

**No separate Volt download is required.** The plugin includes the pinned, MIT-licensed VoltAgent Codex specialist pack: 172 namespaced profiles, ready for LaneOrchestrator to select after activation. Plugin installation never silently writes to your global Codex profile directory, so activate the bundled pack through one reviewed preview and approval:

```sh
python3 -m laneorchestrator voltagent install preview --json
python3 -m laneorchestrator voltagent install apply --token <bound-token> --approval approve:<approval-digest> --json
```

This installs `laneorchestrator-voltagent-*` profiles without replacing any of your own agents. The four LaneOrchestrator control profiles still provide safe routing even when you choose not to activate the specialist pack.

On first use, the skill runs `doctor` to check readiness. If the host does not expose the required bundled profiles, it shows a preview and waits for your explicit approval before applying anything. See the deterministic [90-second cast source](docs/assets/demo.cast) and its [matching transcript](docs/transcripts/quickstart.txt) for the first-run flow. They are illustrative, not a live-install recording or embedded player.

## What it does

- **Route with context.** It evaluates scope, risk, acceptance criteria, and role availability instead of trusting a task label.
- **Keep authority separate.** The control plane is read-only; a writable executor never grants itself more authority or quietly broadens your task.
- **Use specialists without surrendering control.** It discovers skills and agents through bounded metadata. The bundled VoltAgent pack adds 172 optional specialists, but none can override the lane decision.
- **Make mutations deliberate.** Profile and configuration changes are previews first, then require a short-lived bound token and a matching approval.
- **Fail in the safe direction.** Unknown risk does not select the smallest writable lane. Missing required roles pause the relevant work instead of quietly downgrading it.
- **Work from chat or automation.** Use `$laneorchestrator` in Codex, or emit stable JSON from the canonical module command in a source checkout or resolved plugin root.

## The three lanes

| Lane | Use when | Example | If it cannot run |
| --- | --- | --- | --- |
| **Luna** | One known, low-risk file with explicit acceptance criteria | Change a CSS label or fix a README typo | Falls back to Terra when Luna is unavailable. |
| **Terra** | Normal features, integrations, multi-file work, or uncertainty | Add report filtering across a small feature area | Pauses when the required Terra profile is unavailable. |
| **Sol → Terra → Sol** | Security, credentials, migrations, persistent data, public contracts, or high blast radius | Rotate OAuth credentials or change an authentication flow | Pauses when planning or independent review is unavailable. |

These lanes are deliberate guardrails, not a claim that keywords alone understand a task. Review the generated route card and repository evidence before acting on it.

## How the workflow feels

```text
You describe the task
        ↓
LaneOrchestrator checks readiness and repository evidence
        ↓
It returns a route card with lane, reason, safety boundary, and role evidence
        ↓
Codex works within that lane and verifies the result
        ↓
High-risk or unavailable-role work pauses instead of quietly weakening safeguards
```

The default path is intentionally simple: install the plugin, invoke `$laneorchestrator`, inspect its route card, and let Codex follow the stated boundary. For direct integration or source development, use `python3 -m laneorchestrator` only from a source checkout or a resolved installed plugin root—not an arbitrary workspace.

## Trust, safety, and release evidence

- The protected annotated [`v0.2.2` release](https://github.com/KarthikRamesh9149/laneorchestrator/releases/tag/v0.2.2) includes deterministic archives and `SHA256SUMS`.
- The tag-triggered [release workflow](.github/workflows/release.yml) validates the repository, verifies generated assets, and emits GitHub artifact attestations.
- Read the [security model](docs/security-model.md) and [threat model](docs/threat-model.md) for boundaries and known limitations.
- Use the [security policy](SECURITY.md) to report a vulnerability privately; do not put sensitive reproduction details in an issue.

Security evidence is layered and bounded. It supports careful use and review; it is not a promise that every environment or future change is risk-free.

## FAQ

### Do I need Volt or a separate agent-pack download?

No. LaneOrchestrator ships the 172-profile VoltAgent specialist pack inside the plugin, with its pinned source and MIT attribution. Activate it once through the explicit preview and approval flow above; it never overwrites an existing user profile. The core routing profiles remain sufficient if you do not activate it.

### Can it change my files or configuration without asking?

No. Routing and discovery are read-only. Profile and configuration lifecycle operations start with a preview; an apply must use the reviewed plan's unexpired bound token and matching explicit approval.

### What if a model or profile is unavailable?

Luna can fall back to Terra for eligible small work. Required Terra or Sol roles cause the relevant route to pause rather than silently choosing a weaker path.

### Does it work on Windows?

Read-only control-plane commands are supported on native Windows. Use WSL for profile or configuration mutation; see [compatibility](docs/compatibility.md) for the exact boundary.

### How do I update or remove it?

Review a newer protected release tag before changing your marketplace source. Plugin removal does not remove managed profiles or configuration; use the explicit lifecycle guidance in [getting started](docs/getting-started.md) and [configuration and recovery](docs/configuration.md).

## Learn more

- Start with [getting started](docs/getting-started.md), then see the [command reference](docs/commands.md) and [concepts](docs/concepts.md).
- Explore [small](docs/examples/small-change.md), [normal](docs/examples/normal-feature.md), and [high-risk](docs/examples/high-risk-change.md) route examples.
- Review [configuration and recovery](docs/configuration.md), [troubleshooting](docs/troubleshooting.md), [architecture](docs/architecture.md), and [benchmarks](docs/benchmarks.md).
- See the [roadmap](docs/roadmap.md), [support options](SUPPORT.md), and [changelog](CHANGELOG.md).

## Contribute

Contributions should preserve the control-plane boundary and leave fresh verification evidence. Run `sh scripts/validate.sh` before opening a pull request; it includes the exactly 100-case acceptance surface and the wider unit suite. [CONTRIBUTING.md](CONTRIBUTING.md) explains the contribution, evidence, and rollback expectations.

Licensed under the [MIT License](LICENSE). [NOTICE](NOTICE) records clean-room provenance.
