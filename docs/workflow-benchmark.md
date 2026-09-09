# Workflow benchmark

`scripts/benchmark_workflows.py` is an opt-in comparison of LaneOrchestrator's
adaptive choice with a fixed `gpt-5.6-terra` / `medium` baseline. It runs three
small executable Python fixtures: a duplicate-JSON-key bug, a capability-ranking
feature, and a route-summary refactor. The fixtures are adapted from concepts and
source paths at repository commit
`eb2bb7a4b1fd7e02349c5de1d9e846c63d2afeaa`; they are not three full external
repositories and do not measure the breadth of real user-repository work.

The default command only validates the local corpus and prints the call plan:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_workflows.py
```

A live run must be explicit and must write evidence outside the source checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_workflows.py \
  --run \
  --codex /Applications/ChatGPT.app/Contents/Resources/codex \
  --output /private/tmp/laneorchestrator-workflow-benchmark \
  --timeout 240 \
  --max-observed-tokens 250000
```

The output directory must be absent or empty. `report.json` is updated after the
router and every implementation so a stopped run remains inspectable. Per-call
JSONL, stderr, schemas, changed sources, diffs, final responses, and verifier logs
are retained beside it.

If the only completed call is the router and its model selection is valid under
the active routing policy, reuse that paid call with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_workflows.py \
  --run \
  --codex /Applications/ChatGPT.app/Contents/Resources/codex \
  --resume-routing /private/tmp/laneorchestrator-workflow-benchmark \
  --timeout 240 \
  --max-observed-tokens 250000
```

Resume verifies the prior report's available fixture hashes and provenance,
router JSON, event usage, and ledger before continuing. The paid router call
remains call one of the hard eight-call total. A policy-valid decision that
differs from the frozen authored rubric is retained as a routing failure rather
than discarded; the authored independent-review requirement remains a floor.

If a later call completed and the report stopped at the observed-token ceiling,
continue only the missing execution suffix with `--resume-run`. For example, an
explicitly authorised two-million-token ceiling uses:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_workflows.py \
  --run \
  --codex /Applications/ChatGPT.app/Contents/Resources/codex \
  --resume-run /private/tmp/laneorchestrator-workflow-benchmark \
  --timeout 240 \
  --max-observed-tokens 2000000
```

This mode accepts only a `budget_stopped` report whose calls form the exact
router-plus-execution prefix. It validates event usage and the prior ledger,
re-runs the external verifier against each saved source artifact, preserves all
completed calls and results, then starts at the first missing arm. Cached input
is already a subset of `input_tokens`, so the observed total counts input plus
output once rather than adding cached input a second time.

The run is sequential and has no retry path. Its maximum is eight model calls:
one Astra/high routing call containing all three tasks plus frozen U006 read-only
calibration, six implementation calls, and one fresh Sol/high review of all
consequential A/B outputs. The router never receives the authored expected route
or verifier tests. The combined reviewer sees anonymised arm A/B source and the
requirements, without model labels or tests.

Before every call, the harness applies the host-supplied usage ledger with an
eight-call ceiling, zero retries, and the observed-token ceiling. Missing usage
stops admission to the next call. Reaching the token ceiling also stops the next
call, so one already-admitted call can overshoot it. This is observed accounting,
not a server reservation or hard per-call token cap. If a budget stop leaves an
arm or review incomplete, the report status is `budget_stopped` and the comparison
rows are marked incomplete.

Each arm runs in a fresh temporary Git repository. Authoritative tests are not
copied into the model's task workspace. They are copied later into a separate
write-protected verifier directory and hashed before and after execution. The host
sandbox may still permit read access to their source-controlled originals, so the
harness does not call them inaccessible holdouts. A task passes only when the
model call exits successfully, an editable source changes, no unexpected workspace
files remain, tests pass, and test hashes stay unchanged.

Benchmark subprocesses ignore user configuration and request disabled multi-agent
fan-out and skipped host skill discovery. Runtime evidence can still show host
metadata loading, so these flags do not prove discovery was absent or reduce a
call's input usage. The routing prompt supplies the compact policy and active host
catalog needed by this isolated comparison. Results therefore test
explicit model dispatch on these fixtures; they do not test installed named
profiles, specialist discovery, desktop profile reloads, or production readiness.
Requested model and reasoning settings remain separate from runtime-observed
fields, which stay `null` unless Codex events expose them.
