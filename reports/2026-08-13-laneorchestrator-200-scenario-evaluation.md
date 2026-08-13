# LaneOrchestrator deterministic 200-scenario evaluation

**Date:** 2026-08-13
**Evidence type:** deterministic, local, real public/control-plane APIs; no model
calls, network calls, wall-clock assertions, or production mocks.

## Final result

| Reviewed slice | Passed | Failed |
|---|---:|---:|
| Routing | 50/50 | 0 |
| Rendered 172-pack specialist top-three selection | 50/50 | 0 |
| Adversarial and fail-closed behaviour | 50/50 | 0 |
| Model, context, configuration, and route-card integration | 50/50 | 0 |
| **Total** | **200/200** | **0** |

Command and result:

```text
python3 -m unittest tests.test_mock_scenarios_200 -v
Ran 5 tests in 0.308s
OK
```

The five test methods are four fixed 50-case manifests plus a manifest-integrity
test. Every scenario has a stable unique `R01`–`R50`, `S01`–`S50`, `A01`–`A50`,
or `M01`–`M50` identifier and an assertion-bearing description in
`tests/test_mock_scenarios_200.py`; the single test-run count must not be read
as five scenarios.

## Scope and API boundary

The corpus exercises the real implementations of `recommend_route()`,
`rank()` over the rendered 172-profile pack, `collect()`, `resolve_route()`,
`validate_config_payload()`, `render_pack()`, and `build_route_card()`.
Temporary files are used only for filesystem-anomaly inputs. The rendered pack
is created by `render_pack()`, then collected/ranked through the production
discovery path; no hand-built specialist catalog stands in for it.

## Regression findings and remediations

The first run exposed the report's critical safety and contract gaps:

- High-risk wording for SAML assertions, signing keys, path traversal, and
  arbitrary file reads needed conservative risk recognition. The permanent
  routing cases require Sol → Terra → independent Sol/high review.
- Natural prompts against all 172 rendered profiles missed reviewed specialist
  matches when aliases, inflections, or task phrases differed from profile
  prose. The 50 natural-language top-three corpus is now permanent.
- A combined machine-readable decision was missing. The route card now records
  lane/workflow, structured selected-specialist metadata, selection reason,
  fallback, verification requirements, and role evidence.
- Control roles could be configured away from their published lane models.
  Schema validation now fixes router/reviewer to Sol, small executor to Luna,
  and main implementation to Terra; the configured model identities cannot
  weaken high-risk review.
- Optional-specialist selection for high-risk work now suppresses itself when
  no trusted project context is supplied, rather than depending on a caller to
  remember a catalog flag.

## Behaviour verified

- The 50 route cases retain Luna solely for bounded, ASCII, known-area,
  acceptance-defined, one-file editorial work. Normal implementation uses
  Terra; explicit, unknown, non-ASCII, and signalled high-risk work cannot
  downgrade to Luna.
- The 50 specialist cases use exactly 172 rendered profiles. Each selected
  profile exposes `model: gpt-5.6-terra`, `reasoning_effort: high`, and trusted
  source separately from description text. Specialist choice is an overlay and
  cannot alter the lane.
- The adversarial slice covers 35 deceptive low-risk security objectives,
  untrusted/project metadata, vendor mismatch, keyword stuffing, symlinked
  metadata, required-role missing/unknown states, approved Luna→Terra fallback,
  and rejected control-model downgrades.
- The model/context slice confirms fixed control models, structured route-card
  fields, deterministic repetition, high-risk unscoped-specialist suppression,
  role fallbacks, and Luna admission conditions.

## Residual boundary

This proves the deterministic control plane, not entitlement to a host model
or an end-to-end paid model execution. `doctor` can establish local profile
file evidence but cannot authoritatively prove model entitlement; rerun
interactive setup/update and `doctor --json` on the target host before live
operation. The repository-wide validator, benchmark, plugin validators, and
cross-platform CI remain separate release gates and should report their own
fresh evidence.
