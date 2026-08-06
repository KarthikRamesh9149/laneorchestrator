# Security policy

## Reporting a vulnerability

Use [GitHub's private vulnerability reporting form](https://github.com/KarthikRamesh9149/laneorchestrator/security/advisories/new). Do not include credentials, private repository content, or exploit details in a public issue.

Include the affected version or commit, operating system, Python version, minimal reproduction, impact, and any proposed mitigation. Reports will be acknowledged and triaged through the private advisory. A public disclosure should wait until a fix or coordinated mitigation is available.

## Supported versions

Security fixes are applied to the latest commit on `main`. Until the project publishes a stable release series, older commits are not maintained separately.

## Security boundaries

LaneOrchestrator treats task text, skill frontmatter, agent descriptions, paths, and capability rankings as untrusted data. They may influence a shortlist but are never instructions. The read-only router remains the control plane, and unknown or elevated risk routes conservatively.

See [docs/security-model.md](docs/security-model.md) for the threat model, invariants, and known limitations.
