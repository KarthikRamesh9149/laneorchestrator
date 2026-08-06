# Contributing

Contributions should preserve LaneOrchestrator's conservative routing and explicit trust boundaries.

## Development setup

Requirements are Python 3.9 or newer and a POSIX shell on macOS or Linux. The runtime has no third-party Python dependencies.

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

Run `sh scripts/validate.sh` before opening a pull request. Explain risk, verification evidence, and rollback strategy in the pull-request description.

## Style

- Prefer the Python standard library and small explicit functions.
- Support Python 3.9 and current Python releases.
- Keep shell scripts POSIX-compatible.
- Use structured JSON for machine-consumed output.
- Avoid broad exception suppression; return actionable warnings for skipped untrusted inputs.

Security reports must follow [SECURITY.md](SECURITY.md), not the public issue tracker.
