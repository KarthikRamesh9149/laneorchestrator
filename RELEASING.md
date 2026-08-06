# Releasing

Releases are made from a clean, synchronized `main` branch after CI succeeds.

1. Move completed entries from `Unreleased` in `CHANGELOG.md` into a semantic version heading with the release date.
2. Update `version` in `.codex-plugin/plugin.json` to the same version.
3. Run `sh scripts/validate.sh` and confirm every GitHub Actions matrix job passes.
4. Commit with `release: prepare vX.Y.Z` and create an annotated `vX.Y.Z` tag.
5. Push `main` and the tag, then create a GitHub release using the matching changelog section.
6. Verify the source archive contains the manifest, skill, four agent profiles, installer, license, and security documentation.

Do not reuse or move a published tag. If a release is incorrect, publish a new patch version with an explanatory changelog entry.
