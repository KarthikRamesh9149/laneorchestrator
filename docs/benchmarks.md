# Benchmarks

The committed benchmark is a regression evaluation for the current routing and capability-ranking policy. It does not establish that lexical ranking replaces repository-aware routing.

## Corpus and measurement

The routing corpus contains 200 reviewed cases. The capability corpus contains 25 bounded synthetic catalogs, including non-applicable, source-precedence, keyword-stuffing, vendor-mismatch, and high-risk-evasion cases. The runner reports route agreement, high-risk recall, capability top-1 and top-3 recall, repeatability, adversarial pass rate, false-positive escalation, and bounded discovery timing.

A fresh local run observed 0.985 overall agreement, 1.0 high-risk recall over 100 reviewed expected-Sol labels, 1.0 top-1 and top-3 capability recall, 1.0 adversarial pass rate, and 0.03 false-positive escalation. The same run measured maximum-catalog discovery at 0.514 seconds and full evaluation at 2.455 seconds. These are observations from one local environment, not a portable performance claim; the release threshold for bounded discovery is under ten seconds on each release CI job.

Reports are generated on demand and are not committed. Maximum-catalog timing measures discovery after temporary fixed-seed fixture creation. The fixture saturates file and byte caps; independent directory and entry caps cannot all be saturated simultaneously without violating the file caps.

See [the corpus notes](../benchmarks/README.md) for labels, adversarial coverage, and further limits. The [roadmap](roadmap.md) records future evaluation work.
