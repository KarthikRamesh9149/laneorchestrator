# LaneOrchestrator benchmark corpora

`routing-corpus-v1.json` is a 200-case, reviewed regression corpus. It retains
the 50 cases from `tests/test_routing_matrix.py` verbatim and adds exact totals
of 40 bounded-low, 60 normal, 70 high-risk, 15 high-risk-evasion, and 15
conservative-unknown cases. The latter are deliberately marked `risk: unknown`:
the current conservative route policy sends an unassessed task to the Sol review
lane, even where the objective itself has no lexical high-risk signal.

Every route record is reviewed and labelled against the current policy. The runner
passes only task facts to `recommend_route`; `expected_lane` is never an input
to that function. High-risk recall is therefore calculated from all reviewed
Sol-lane labels (currently 100 cases), and false-positive escalation is reported
over the remaining reviewed cases without being a release threshold.

`capability-corpus-v1.json` contains 25 bounded synthetic catalogs, with at
most eight metadata records per query. It covers OAuth, Stripe, PostgreSQL,
React accessibility, Azure, Slack, deployment, Kubernetes, Supabase, Figma,
non-applicable work, source precedence, keyword stuffing, and vendor mismatch.
Top-1 and top-3 recall use only the 20 `applicable_specialist: true` cases;
the five false cases have no expected specialist. The eight tagged capability
adversarial cases include keyword stuffing and vendor mismatch; they are
combined with high-risk-evasion route cases, and every tagged case must pass.

Run a fresh report with:

```sh
python3 -m laneorchestrator benchmark --json
```

The report is generated on demand and is intentionally not committed. Its
maximum-catalog timing measures discovery only, after temporary fixed-seed
fixture creation. It creates 2,048 valid 16 KiB skills (32 MiB total) and
1,024 valid 8 KiB agents (8 MiB total), then removes them. File and byte caps
are saturated; independent directory/entry caps cannot all be saturated at the
same time without violating those file caps. Timing is hardware and CI
dependent, while corpus decisions and ranking output are deterministic.

This is a regression benchmark, not a claim that lexical ranking replaces the
repository-aware routing workflow. Threshold changes require a reviewed policy
or corpus rationale and a newly generated report.
