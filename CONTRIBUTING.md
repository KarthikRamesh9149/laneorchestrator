# Contributing

Contributions should preserve LaneOrchestrator's conservative routing and explicit trust boundaries.

## Development setup

The support target is Python 3.9-3.14. The runtime has no third-party Python dependencies. macOS and Linux support mutation controls; native Windows is read-only only, so use WSL for profile or configuration mutation.

```bash
git clone https://github.com/KarthikRamesh9149/laneorchestrator.git
cd laneorchestrator
sh scripts/validate.sh
```

## Change requirements

1. Add behavior-focused regression coverage before changing routing, discovery, installation, or fallback behavior.
2. Keep capability metadata untrusted. Never evaluate metadata as code or merge it into developer instructions.
3. Default unknown risk to the Sol control path. Luna requires verified low risk, one known area, explicit acceptance criteria, and one file.
4. Preserve installer collision safety and descriptor-relative, no-follow file operations.
5. Update documentation and `CHANGELOG.md` for user-visible behavior.
6. Preserve the preview-and-bound-token workflow for configuration and managed-profile changes; never add a shortcut that weakens the required human review.

Run `sh scripts/validate.sh` before opening a pull request. Explain risk, verification evidence, and rollback strategy in the pull-request description.

## Style

- Prefer the Python standard library and small explicit functions.
- Support Python 3.9-3.14.
- Keep shell scripts POSIX-compatible.
- Use structured JSON for machine-consumed output.
- Avoid broad exception suppression; return actionable warnings for skipped untrusted inputs.

Security reports must follow [SECURITY.md](SECURITY.md), not the public issue tracker.
