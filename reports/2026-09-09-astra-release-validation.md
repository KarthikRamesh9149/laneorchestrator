# Astra 0.3.0 validation checkpoint

This records reproducible local evidence and the bounded live experiment. Release
publication additionally requires the protected GitHub checks, annotated tag,
attested artifacts and public installation check described in RELEASING.md.

## Engineering evidence

- Clean tracked-source snapshot at `3fd2e3d`: full validator passed 1,051 tests
  with one set-ID filesystem skip, including extracted-archive validation.
- The 200 normal and 100 extreme offline scenarios remain passing. They validate
  supplied scope facts and policy contracts, not 300 model implementations.
- Usage tests cover pending/failed calls, retry and call ceilings, malformed and
  duplicate counters, per-packet/agent totals, cache accounting and unknown usage.
- Independent read-only review resolved the discovered mixed-task/credential
  review omissions and benchmark grading issues. Detection remains a conservative
  lexical backstop applied to trusted host scope assertions.
- Four legacy core profiles were adopted through exact reviewed lifecycle plans.
  All four now verify as managed, and 172 specialists are installed with no drift.
  See [installation evidence](2026-09-09-install-readiness.md).

## Live checkpoint

The [machine-readable checkpoint](astra-030-workflow-checkpoint.json) contains two
actual calls. The first asked Astra/high to route three repository-derived
fixtures and assess the frozen U006 review-only calibration. U006 passed after
the policy clarification. All three model/effort pairs were policy-valid; two
complete routing decisions matched the frozen fixture rubrics.

For the duplicate-JSON fixture, Astra chose small Terra/high without review, while
the authored rubric expected routine/demanding with review. The model's reasoning
was that the isolated fixture did not establish production consequences. That
mismatch is preserved, not relabeled as success. Execution can use the valid
model pair while the harness independently retains the stricter review floor.

The second call implemented that fixture using Terra/high and passed its external
tests without changing them. No fixed-baseline implementation or independent
review had run when the observed-token guard stopped admission to call three.
This is a successful implementation check, not a completed workflow comparison.

Reported usage at the stop: 328,686 input tokens, of which 246,016 were cached,
and 3,139 output tokens. Total observed processing was 331,825 tokens. One admitted
call crossed the configured 250,000 threshold; the next launch was stopped as
documented. Those counters are not a bill or a conversion to account-limit usage.
Parent conversation and engineering-review agents are excluded from these totals.

The router was reused for recovery without a second routing call. Additional paid
comparison work is paused pending the user's budget choice. No token-efficiency,
latency or quality advantage over the fixed baseline is established yet.

## Remaining evidence boundaries

Runtime model and reasoning identity remain unknown where the CLI does not emit
them. Host discovery-disable flags were requested, but actual logs still showed
host metadata loading; no overhead-saving claim is made. The fixtures are adapted
from repository concepts, not three independent user repositories. External user
feedback still requires participants and actual responses; a trial guide alone
does not establish adoption or user satisfaction.
