# GitHub launch settings (unapplied)

This is the exact post-code-gate plan. It does not assert current repository settings, visibility, remote branches, CI state, or ownership. Do not apply it until the release commit has passed the pre-public evidence gates.

## Repository metadata

- Description: `Secure, evidence-driven model and agent routing for Codex.`
- Homepage: `https://github.com/KarthikRamesh9149/laneorchestrator#readme`
- Topics: `codex`, `ai-agents`, `agent-routing`, `developer-tools`, `python`, `security`, `open-source`
- Discussions: enable at publication, not during candidate preparation.

## Single-main ruleset

Create exactly one active ruleset named `protect-main`, targeting only `main`. Do not create another branch as part of this step.

- Require these current CI status checks: `POSIX Python 3.9 on ubuntu-latest`, `POSIX Python 3.14 on ubuntu-latest`, `POSIX Python 3.9 on macos-latest`, `POSIX Python 3.14 on macos-latest`, `Windows read-only control plane Python 3.9`, `Windows read-only control plane Python 3.14`, and `Verify release evidence`.
- Require the branch to be up to date before the checks pass.
- force pushes: block.
- deletions: block.
- Do not require a separate branch or code-owner approval for this single-maintainer ruleset. `CODEOWNERS` is policy metadata and becomes enforceable only if a later ruleset explicitly requires it.
- Bypass: no routine bypass actor. Any emergency owner bypass must be recorded with the reason and followed by a fresh validation run.

## Post-apply verification

After applying the settings, use the GitHub UI or API and `git ls-remote --heads origin` to verify the exact metadata, Discussions state, sole `main` target, required checks, force-push/deletion blocks, bypass configuration, and remote branch state. Record that evidence in the operational release runbook; do not infer it from this file or a detached local checkout.
