# Task 3 report: canonical bounded capability discovery

## Status

Complete. Bounded capability discovery and deterministic ranking now live in
`laneorchestrator.discovery`; the legacy catalog entry point is a path bootstrap
and `discovery.main()` only. The legacy v1 JSON shape, source evidence,
lane-agent separation, ranking/tie ordering, matched terms, warnings, and
existing resource bounds are retained.

## Files

- Added `laneorchestrator/discovery.py`.
- Added `tests/test_discovery_api.py`.
- Reduced `skills/laneorchestrator/scripts/catalog.py` to the compatibility
  bootstrap.
- Updated `tests/test_catalog.py` to exercise the public package API and to
  use `sys.executable` for all subprocesses.

## RED evidence

Before creating the canonical module, the required focused command was run:

```text
python3 -m unittest tests.test_discovery_api tests.test_catalog -v
ModuleNotFoundError: No module named 'laneorchestrator.discovery'
Ran 18 tests in 0.605s
FAILED (errors=1)
```

## GREEN evidence

The focused suite was run twice after the implementation:

```text
python3 -m unittest tests.test_discovery_api tests.test_catalog -v
Ran 25 tests in 0.627s
OK

python3 -m unittest tests.test_discovery_api tests.test_catalog -v
Ran 25 tests in 0.621s
OK
```

The legacy catalog command was executed twice with identical inputs and
`diff -u` produced no output, proving deterministic JSON output. Full project
validation also passed:

```text
sh scripts/validate.sh
LaneOrchestrator health check passed
Ran 68 tests in 5.750s
OK
```

## Commit

`refactor: centralize bounded capability discovery`

## Self-review

- `DiscoveryRequest` and `DiscoveryLimits` are frozen; callers may tighten but
  cannot raise any established bound.
- Local metadata reads remain no-follow, bounded, deterministic, and decoded
  as untrusted UTF-8 text only.
- Direct API coverage includes legacy parity, prompt-injection-like text,
  keyword stuffing, vendor mismatch, duplicate names, deterministic ties,
  depth/file/byte/entry caps, invalid UTF-8, dangling symlinks, warning caps,
  counters, and validation bounds.
- `git diff --check` passed and the catalog executable bit was preserved.

## Concerns

No known blockers. The compatibility script intentionally no longer exposes
its old implementation helpers as importable script globals; consumers should
use the canonical `laneorchestrator.discovery` API.

## Fix Round 1: direct `collect()` root bound

### Changed files

- Updated `laneorchestrator/discovery.py` with a shared root-count validator
  used by both `validate_request()` and the direct public `collect()` API.
- Updated `tests/test_discovery_api.py` with a direct-`collect()` regression
  using 65 roots.

### RED evidence

Before the production fix:

```text
python3 -m unittest tests.test_discovery_api tests.test_catalog -v
FAIL: test_collect_rejects_unbounded_roots_before_enumeration
AssertionError: ValueError not raised
Ran 26 tests in 0.618s
FAILED (failures=1)
```

### GREEN evidence

After adding the shared pre-enumeration check:

```text
python3 -m unittest tests.test_discovery_api tests.test_catalog -v
Ran 26 tests in 0.611s
OK
```

### Commit

`869ddc5` — `fix: bound direct discovery roots`

### Self-review

`collect()` checks the root count before converting any root to a `Path` or
iterating it. The same helper remains used by request validation, so direct and
request-mediated discovery now share the exact 64-root limit and error text.

### Concerns

None. The guard rejects only root lists above the established bound and does
not alter legacy CLI root handling.
