# Feature: notification preferences

## Request

> `$laneorchestrator Add notification preferences to settings. Save per user and restore them after reload.`

## What Astra inspects

The application already has a settings endpoint, authenticated user context and reusable form components. The change spans the form, persistence and defaults; no new authorization model is needed. Astra resolves the preferences and acceptance criteria from the request and repository, asking only for a product decision that cannot be inferred.

## Selection and handoff

**Astra coordinates → Sol/high implements → Astra/high reviews.**

Sol/high is a reasonable choice because the implementation follows known architecture but requires careful integration across layers. This is not a rule that every settings page must use Sol: a smaller isolated form might justify Terra/medium, while an unknown storage migration requires more investigation.

The full-stack specialist receives the relevant files, ownership boundaries, existing settings contract and acceptance criteria. It implements through that contract rather than creating a competing settings system.

## Verification

- Saved preferences survive a reload.
- Existing users receive valid defaults.
- A failed save preserves the edited form and reports the failure.
- Existing user isolation and settings behavior remain intact.

The separate Astra reviewer checks the final diff against these criteria and the test evidence. It can request a correction; implementation is not self-approved. The final handoff reports the actual checks and any unresolved gap.

This is the second recreated workflow in the [launch film](../assets/laneorchestrator-product-demo.mp4). It illustrates the policy; it is not live execution evidence. See [fixture evidence](../live-validation.md) and the [legacy payload](legacy/normal-feature.md).
