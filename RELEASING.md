# Releasing

Releases are made from a clean, synchronized `main` branch after CI succeeds. Do not describe a release as published until every pre-public gate in the approved release plan has fresh evidence.

1. Move completed entries from `Unreleased` in `CHANGELOG.md` into a semantic version heading with the release date.
2. Update package, `plugin.json`, and `.codex-plugin/plugin.json` versions to the same value.
3. Run `sh scripts/validate.sh`, verify documented commands and links, and confirm every GitHub Actions matrix job passes.
4. Generate and review a fresh benchmark report; confirm its thresholds and the benchmark documentation agree.
5. Confirm marketplace installation from an isolated Codex home, release archive contents, and checksums. Keep tokens, account paths, and private findings out of public evidence.
   The release verifier applies bounded, high-confidence credential and local-path checks as defense in depth; it is not an exhaustive secret scanner and adds no third-party scanner dependency.
6. Complete the required security review and independent read-only review. Repository visibility and external messages remain separate authorization boundaries.
7. Commit with `release: prepare vX.Y.Z`, create an annotated `vX.Y.Z` tag, then push and create a GitHub release using the matching changelog section.

Do not reuse or move a published tag. If a release is incorrect, publish a new patch version with an explanatory changelog entry. Plugin removal does not remove managed profiles or configuration; recovery remains previewed and explicit.
