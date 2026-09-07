# Contributing

Contributions should preserve LaneOrchestrator's conservative routing and explicit trust boundaries.

## Development setup

The support target is Python 3.9-3.14. The runtime has no third-party Python dependencies. macOS and Linux support mutation controls; native Windows is read-only only, so use WSL for profile or configuration mutation.

```bash
git clone https://github.com/KarthikRamesh9149/laneorchestrator.git
cd laneorchestrator
sh scripts/validate.sh
```

## Choose a contribution

Start with a reproducible bug, a clearer example, a platform compatibility fix, or a focused test for a real regression. Discuss architectural changes in [Discussions](https://github.com/KarthikRamesh9149/laneorchestrator/discussions) before a large patch. Do not open speculative refactors solely to increase activity.

| Area | Where to look |
| --- | --- |
| Selection constraints | `laneorchestrator/adaptive.py`, adaptive tests |
| Skill execution instructions | `skills/laneorchestrator/SKILL.md` and references |
| Profile lifecycle | `laneorchestrator/profiles.py`, `laneorchestrator/voltagent.py` |
| First-use documentation | `README.md`, `docs/getting-started.md` |
| Release integrity | `scripts/build_release.py`, `scripts/verify_release.py` |

Work from a fork or a local branch, keep the change focused, and open a pull request against `main`. Do not edit the pinned upstream specialist source casually: its integrity and attribution are verified. Generated profile changes belong in the renderer and corresponding migration coverage.

## Change requirements

1. Add behavior-focused regression coverage before changing routing, discovery, installation, or fallback behavior.
2. Keep capability metadata untrusted. Never evaluate metadata as code or merge it into developer instructions.
3. Resolve unknown scope through investigation before choosing an implementation model. Preserve Astra's task-specific selection policy, host-supported settings and independent review for consequential changes.
4. Preserve installer collision safety and descriptor-relative, no-follow file operations.
5. Update documentation and `CHANGELOG.md` for user-visible behavior.
6. Preserve the preview-and-bound-token workflow for configuration and managed-profile changes; never add a shortcut that weakens the required human review.

For documentation, start with `python3 scripts/check_docs.py`; the full validator also checks links, command contracts, manifests and distribution contents. Some integration checks intentionally require an isolated fixture or a POSIX environment. Live model smoke tests are optional and consume account usage; they are not required for ordinary contributions.

Run `sh scripts/validate.sh` before opening a pull request. Explain risk, verification evidence, and rollback strategy in the pull-request description.

## Style

- Prefer the Python standard library and small explicit functions.
- Support Python 3.9-3.14.
- Keep shell scripts POSIX-compatible.
- Use structured JSON for machine-consumed output.
- Avoid broad exception suppression; return actionable warnings for skipped untrusted inputs.

Security reports must follow [SECURITY.md](SECURITY.md), not the public issue tracker.

## Review and community expectations

Describe the problem, resulting behavior and verification so a reviewer can assess the patch without reading its conversation history. Documentation-only changes do not need artificial behavioral tests; update existing documentation checks when their contract changes. Do not claim a benchmark, live run or platform check that you did not perform.

Keep discussion respectful and focused on the work. Harassment, personal attacks and disclosure of private information are not acceptable. Use the support channels below for help. Maintainers may close off-topic or abusive threads; no response-time commitment is implied.

See [SUPPORT.md](SUPPORT.md) for questions and bug reports, and [RELEASING.md](RELEASING.md) for maintainer release work.
