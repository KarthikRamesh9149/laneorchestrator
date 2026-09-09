# Documentation

LaneOrchestrator turns a normal Codex request into scoped agent work. Astra chooses the expertise, model and thinking after inspecting the task. The local CLI validates decisions and manages profiles; Codex runs the agents.

## Start and use

| I want to… | Read |
| --- | --- |
| Install the Astra source version and finish a first task | [Getting started](getting-started.md) |
| Understand which version to install or migrate existing profiles | [Release channels and upgrades](upgrading.md) |
| See a small change with proportionate verification | [Small change](examples/small-change.md) |
| Follow Astra → Sol → Astra through a feature | [Notification preferences](examples/normal-feature.md) |
| Understand demanding implementation and independent review | [Event-stream recovery](examples/high-risk-change.md) |
| Split bounded work between Terra specialists | [Project pagination](examples/parallel-specialists.md) |
| Recover from setup or dispatch problems | [Troubleshooting](troubleshooting.md) |

## Configure and integrate

- [Configuration](configuration.md): presets, preferences and profile lifecycle.
- [Usage controls](usage-controls.md): per-agent counters, bounded delegation and stop conditions.
- [Commands](commands.md): module entry point, JSON, setup and advanced operations.
- [Concepts](concepts.md): responsibilities, evidence and selection.
- [Compatibility](compatibility.md): platforms, Python, host requirements and schemas.
- [Dispatch contract](../skills/laneorchestrator/references/dispatch.md): validate settings and launch with explicit model and thinking.

## Verify and contribute

- [Live validation](live-validation.md) separates observed fixture results from unknown backend settings.
- [Benchmarks](benchmarks.md) explains what the offline corpora measure.
- [Workflow comparison](workflow-benchmark.md) runs a bounded adaptive-versus-fixed experiment on executable fixtures.
- [User feedback](user-feedback.md) gives a short protocol for trying the skill on your own repository.
- [Security model](security-model.md) and [threat model](threat-model.md) define trust boundaries.
- [Contributing](../CONTRIBUTING.md), [support](../SUPPORT.md) and [roadmap](roadmap.md) explain how to help.
- [Media production](media-production.md) documents the recreated launch workflows.
- [Legacy examples](examples/legacy/normal-feature.md) are retained for existing fixed-lane integrations.

The source documentation describes `main`. Tagged releases keep their own versioned files. A passing route or selection validator is not proof of execution, and the demo film is an illustration rather than a live recording.
