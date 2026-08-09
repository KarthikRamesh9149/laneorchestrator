# Releasing

Release preparation and external publication are separate boundaries. Do not describe a release as available until every pre-public gate in the approved release plan has fresh evidence and the post-visibility checks complete.

1. Prepare a candidate heading, release notes, and a version-alignment test. The Python package, both versioned plugin manifests, archive prefix, planned `vX.Y.Z` tag, changelog, and notes must agree.
2. At the exact release commit, confirm a clean synchronized `main`, then run `sh scripts/validate.sh`, verify documented commands and links, and record every GitHub Actions matrix result without annotations.
3. Generate and review the benchmark report from that commit; confirm its thresholds and benchmark documentation agree.
4. Build and verify the deterministic archives with `python scripts/build_release.py --output <empty-output-dir>` and `python scripts/verify_release.py <output-dir>`. Attach the generated `SHA256SUMS`; never copy a digest into documentation by hand.
5. Complete clean install, v0.1.0 adoption, update, drift-refusal, uninstall, and isolated marketplace journeys. Keep tokens, account paths, and private findings out of evidence.
   The release verifier applies bounded, high-confidence credential and local-path checks as defense in depth; it is not an exhaustive secret scanner and adds no third-party scanner dependency.
6. Complete the required deep security review and a fresh independent read-only review. Resolve every blocking finding before continuing; a suspected leak requires containment before any public action.
7. Apply the reviewed GitHub metadata, Discussions choice, and sole-`main` ruleset only after the code gates pass. Recheck the gates after the setting change.
8. Only then authorize visibility, repeat isolated public installation, create and push the annotated `vX.Y.Z` tag, attach the verified archives and generated `SHA256SUMS`, and verify public links from an unauthenticated context.

Do not reuse or move a tag once it has been made public. If a release is incorrect, use a new patch version with an explanatory changelog entry. A failure after visibility is not a release-success claim. Plugin removal does not remove managed profiles or configuration; recovery remains previewed and explicit.
