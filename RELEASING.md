# Releasing

Release preparation and external publication are separate boundaries. Do not describe a release as available until every pre-public gate in the approved release plan has fresh evidence and the post-visibility checks complete.

1. Prepare a candidate heading, release notes, and a version-alignment test. The Python package, both versioned plugin manifests, archive prefix, planned `vX.Y.Z` tag, changelog, and notes must agree.
2. At the exact release commit, confirm a clean synchronized `main`, run the acceptance surface and full validator, verify documented commands and links, and record every GitHub Actions matrix result without annotations.

   ```sh
   python3 -m unittest tests.test_acceptance_100 -v
   sh scripts/validate.sh
   ```

   The first command must report exactly 100 passing tests.
3. Generate and review the benchmark report from that commit; confirm its thresholds and benchmark documentation agree.
4. Build and verify the deterministic archives with `python scripts/build_release.py --output <empty-output-dir>` and `python scripts/verify_release.py <output-dir>`. Attach the generated `SHA256SUMS`; never copy a digest into documentation by hand.
5. Complete clean install, v0.1.0 adoption, update, drift-refusal, uninstall, and isolated marketplace journeys. Keep tokens, account paths, and private findings out of evidence.
   The release verifier applies bounded, high-confidence credential and local-path checks as defense in depth; it is not an exhaustive secret scanner and adds no third-party scanner dependency.
6. Complete the required deep security review and a fresh independent read-only review. Resolve every blocking finding before continuing; a suspected leak requires containment before any public action.
7. Apply the reviewed GitHub metadata, Discussions choice, sole-`main` ruleset, and release-tag ruleset only after the code gates pass. If the account plan cannot protect a private repository, the explicitly authorized visibility change is the enabling action: make the repository public, apply and verify both rulesets immediately, and do not create a tag or release during that interval.
8. Create and push the annotated `vX.Y.Z` tag only after both rulesets are verified. Wait for the tag-triggered release workflow to pass, download that run's verified archives and generated `SHA256SUMS`, create the GitHub Release from those exact artifacts, verify its attestation, and repeat the installation and public-link journey from an unauthenticated context.

Do not reuse or move a tag once it has been made public. If a release is incorrect, use a new patch version with an explanatory changelog entry. A failure after visibility is not a release-success claim. Plugin removal does not remove managed profiles or configuration; recovery remains previewed and explicit.
