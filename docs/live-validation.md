# Astra execution evidence

On 2026-09-07, four separate Codex CLI processes completed the same isolated Python implementation fixture with the generated Python specialist instructions. Requested combinations were Luna/high, Terra/medium, Sol/medium, and Astra/high. Each process exited successfully, preserved the supplied tests, and passed five independently executed unit tests. The tests cover normalization, aggregation, invalid inputs, Unicode casefolding, and input preservation.

A fifth, read-only Sol/high process independently reviewed the Astra implementation against the original requirements. It approved the fixture, ran the native tests and additional edge-case probes, and left both source and tests unchanged. It identified optional additional test cases, not implementation defects. This is a review of the fixture, not an independent review of the entire LaneOrchestrator change.

The [sanitized result](../reports/astra-live-smoke.json) records requested settings, process results and limitations. The CLI accepted explicit model and thinking arguments, but the captured events did not expose backend-observed model or reasoning level. Those fields remain unknown. This also does not establish that an already-running desktop task has reloaded the model-neutral named profiles.

The opt-in [smoke harness](../scripts/live_dispatch_smoke.py) accepts `--run`, an installed CLI path through `--codex`, and a new temporary output directory through `--output`. It uses the existing CLI authentication, creates isolated fixtures, and makes live model calls; it is deliberately excluded from normal offline validation. It requires available model access and may consume account usage. Raw execution logs stay in the selected temporary output directory.

These are functional smoke checks, not model-quality, cost, latency or routing-quality benchmarks. The separate offline regression suite checks all 176 generated profiles, supported model/effort validation, paraphrase stability, exact-state migration, rollback and user-edit refusal.
