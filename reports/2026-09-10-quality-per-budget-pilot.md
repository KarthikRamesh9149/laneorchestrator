# Quality per budget: bounded pilot

The pilot resumed the original saved run, preserving its routing decision,
fixtures, prompts, baseline and tests. It stopped after five of eight possible
calls at the selected one-million observed-token admission threshold. Three new
calls were made; no router or completed implementation was repeated.

## Results

| Task | Adaptive selection | Fixed selection | Adaptive external tests | Fixed external tests |
| --- | --- | --- | --- | --- |
| Duplicate JSON keys | Terra/high | Terra/medium | Pass | Pass |
| Capability ranking | Terra/medium | Terra/medium | Fail | Fail |
| Route-summary refactor | Luna/high | Terra/medium | Not run | Not run |

Independent review of the consequential JSON changes did not run before the
budget stop. Each arm therefore has one external-test pass, one failure and one
unattempted task, but **zero fully accepted task completions** under this pilot's
review requirements. The experiment is incomplete and establishes no quality-per-
budget advantage. The original routing rubric mismatch also remains recorded.

## Observed processing

| Component | Input tokens | Cached input, included in input | Output tokens | Total observed | Model-call seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Astra coordination | 41,818 | 0 | 608 | 42,426 | Unknown in recovered checkpoint |
| Adaptive JSON implementation | 286,868 | 246,016 | 2,531 | 289,399 | 63.208 |
| Fixed JSON implementation | 285,697 | 246,016 | 2,366 | 288,063 | 65.496 |
| Adaptive ranking implementation | 290,732 | 248,064 | 3,438 | 294,170 | 97.770 |
| Fixed ranking implementation | 338,795 | 316,416 | 4,709 | 343,504 | 106.267 |
| Shared independent review | Not run | Not run | Not run | Not run | Not run |

Total: 1,243,910 input tokens, including 1,056,512 cached input tokens, plus 13,652
output tokens, for **1,257,562 observed tokens**. The last admitted call crossed
the one-million threshold; the guard stopped call six. Cached input is not added
again. No retry, refactor, review or fixed-Astra call followed the stop.

Adaptive implementations used 583,569 observed tokens and fixed implementations
used 631,567. These are implementation-only totals, not the cost of completed
workflows. The feature arms requested the same model and thinking, so their
difference cannot establish an advantage from model selection. The fixed order,
cache effects, single attempt per arm and run resumed on a later day also prevent
causal attribution. Model-call durations exclude verification and are not full
workflow latency. Coordination time remains unknown after recovery.

These are reported processing counters, not monetary costs or account-limit
percentages. Runtime model and thinking identity remain unknown when events do
not expose them. Engineering work on the harness and this report is outside the
pilot ledger.

## What the failures teach us

Both feature implementations passed the ranking behaviour tests but failed the
input-validation test. Four invalid-input cases raised `TypeError` where the
verifier expected `ValueError`; empty queries and zero limits were accepted where
the verifier expected rejection. The prompt says "Validate all inputs" but does
not state those exact rules, and the starter docstring does not resolve them.

The frozen failures are retained. This ambiguity limits the fixture's use as
evidence of model quality. Future fixture versions must expose their input and
error contracts before execution and use fresh evaluation tasks. The current
fixture, verifier and paid results were not rewritten to turn failures into wins.

## Host context investigation

Codex CLI 0.153.4 documents `--ignore-user-config` as skipping `config.toml`, not
all host context. Its feature inventory accepts `skip_host_skill_discovery=true`
and disabled multi-agent features. Nevertheless, stderr from both the original
adaptive JSON call and the resumed fixed JSON call records a host skill scan
reaching its traversal limit. That proves scanning still occurred in these runs;
it does not measure how many prompt tokens each discovery source contributed.

The available local evidence does not identify the internal cause or establish a
supported setting that eliminates it. No speculative flag, broader permission or
fresh paid probe was introduced. Compact dispatch packets remain useful guidance,
but are not proof of reduced host-injected context or measured savings.

## Changes and next evidence

Dispatch guidance now reuses a current Astra coordinator's assessment and valid
inspection results, supplies focused context and explicit acceptance contracts,
and avoids delegation without useful separate ownership. Required independent
review and existing model/thinking rules remain in place. These changes were made
after the frozen pilot; this run cannot measure their effectiveness.

The reporting tool exposes failures, missing work, review status and overhead
separately. A fixed-Astra baseline is available for future runs but was not run.
See the [machine-readable summary](quality-per-budget-pilot-v1.json) and
[benchmark instructions](../docs/workflow-benchmark.md).

A new, explicitly budgeted experiment with unambiguous fresh tasks and balanced
execution order is needed to compare complete adaptive, fixed-Terra and fixed-Astra
workflows. No general superiority or efficiency claim is supported by this pilot.
