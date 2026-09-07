# GitHub repository settings

This maintainer reference records the settings inspected on 2026-09-07. Inspect the live GitHub API again before changing them; a document is not proof of current enforcement.

## Public repository

- Default branch: `main`; completed maintenance should leave only `main` on the upstream repository.
- Issues and Discussions are enabled. Bug and feature forms route support questions and private security reports separately.
- Description: `Astra-led orchestration for Codex: automatic model and thinking selection with 172 specialist agents.`
- Homepage: `https://github.com/KarthikRamesh9149/laneorchestrator#readme`
- Topics: `codex`, `ai-agents`, `agent-routing`, `developer-tools`, `python`, `security`, `open-source`.
- CI and security workflows run on changes; the release workflow supplies separate release evidence.

## Main protection

The active `protect-main` ruleset targets `refs/heads/main`. It blocks deletion and non-fast-forward updates, requires an up-to-date branch for its required checks, and has no bypass actors.

Required check contexts are bound to the GitHub Actions integration, never `Any source`:

- `POSIX Python 3.9 on ubuntu-latest` — expected source: `GitHub Actions` app.
- `POSIX Python 3.14 on ubuntu-latest` — expected source: `GitHub Actions` app.
- `POSIX Python 3.9 on macos-latest` — expected source: `GitHub Actions` app.
- `POSIX Python 3.14 on macos-latest` — expected source: `GitHub Actions` app.
- `Windows read-only control plane Python 3.9` — expected source: `GitHub Actions` app.
- `Windows read-only control plane Python 3.14` — expected source: `GitHub Actions` app.
- `Verify candidate distribution` — expected source: `GitHub Actions` app.
- `private-static-analysis` — expected source: `GitHub Actions` app.
- `public-codeql` — expected source: `GitHub Actions` app.

The security workflow conditionally selects the private or public analysis path; a skipped inapplicable job is not a failed analysis. Check the applicable job and its result. The inspected ruleset does not require a separate code-owner approval. `CODEOWNERS` is ownership metadata, not evidence that someone independently reviewed a change.

## Release tags

The active `protect-release-tags` ruleset targets `refs/tags/v*.*.*`, blocks deletion and non-fast-forward updates, and has no bypass actors. Annotated tags, version parity, successful release gates and artifact attestations are release-process requirements described in [RELEASING.md](../RELEASING.md); do not claim that these are all enforced by the two tag rules themselves.

Never move an existing published release tag to add Astra changes. Prepare a new version and verify its release assets separately.

## Post-apply verification

Verify every required check's `GitHub Actions` expected-source binding, the actual default branch, remote branches, CI at the intended commit, ruleset enforcement and public metadata through GitHub. Preserve unmerged work before deleting a branch. Do not disable protections or use an administrative bypass merely to finish maintenance faster.
