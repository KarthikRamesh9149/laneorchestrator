# LaneOrchestrator World-Class Public Launch Design

**Status:** Approved design, pending implementation plan  
**Date:** 2026-08-09  
**Target release:** v0.2.0  
**Product scope:** Codex-first, standalone, optionally enhanced by installed skills and agents

## Executive summary

LaneOrchestrator will become a public, Codex-first orchestration plugin with a testable Python control plane. The `$laneorchestrator` skill remains the user entry point. Deterministic standard-library code owns configuration, diagnostics, capability discovery, routing recommendations, and the safe lifecycle of the four bundled agent profiles. Codex remains responsible for invoking agents and performing repository work.

The public release will work without VoltAgent or any other third-party capability pack. When relevant external skills or agents are present, bounded discovery may recommend them as optional specialists. The read-only Sol router retains authority over the final route. Luna is restricted to verified bounded work, Terra is the normal writable implementation lane, and high-risk work requires Sol planning, Terra implementation, and a fresh read-only Sol review.

The repository will remain private until every defined launch gate passes. The owner has explicitly authorized making it public after those gates pass. Publication does not authorize external promotional messages; outreach remains a separate approval boundary.

## Problem

Codex users can accumulate many skills, custom agents, and model choices. Manual selection becomes inconsistent as the catalog grows, and untrusted capability metadata creates an additional routing risk. Existing orchestration projects demonstrate demand, but LaneOrchestrator needs a clearer standalone installation path, configurable roles, programmatic diagnostics, release artifacts, public benchmarks, and external-facing documentation before it is a credible open-source product.

The current project has strong routing, discovery, installer, security, and test foundations. Its main gaps are productization and evidence:

- the GitHub repository is private;
- the repository has no public tag or release;
- installation describes a generic local-plugin flow instead of exact marketplace commands;
- model roles are fixed in checked-in profiles;
- fallback behavior is mostly an instruction contract rather than a diagnosable user-facing state;
- no public benchmark corpus measures routing or specialist-selection quality;
- no clean-host marketplace installation test exists;
- no public demonstration, social preview, or adoption evidence exists.

## Goals

1. Provide a zero-configuration first run for supported Codex users.
2. Provide optional role-to-model configuration without storing credentials.
3. Diagnose verifiable readiness precisely and label host-unverifiable facts as unknown.
4. Preserve strict separation between read-only routing/review and writable implementation.
5. Work with only the four bundled LaneOrchestrator profiles.
6. Discover relevant installed skills and agents without requiring or modifying them.
7. Offer exact marketplace installation, update, and removal documentation.
8. Safely install, update, adopt, and uninstall only LaneOrchestrator-managed profiles.
9. Publish reproducible routing and capability-ranking benchmarks.
10. Ship a security-reviewed v0.2.0 release with verified checksums and public installation evidence.
11. Present a polished open-source surface suitable for broad discovery and contribution.
12. Avoid claims that cannot be proven, including guaranteed correctness, model availability, cost savings, or star counts.

## Non-goals

- Cross-client adapters for Cursor, Copilot, Kiro, or other hosts are not part of v0.2.0.
- LaneOrchestrator will not run a daemon or MCP server.
- LaneOrchestrator will not install third-party skills or agents.
- LaneOrchestrator will not send telemetry.
- LaneOrchestrator will not store secrets or credentials.
- LaneOrchestrator will not silently deploy, delete, spend money, send messages, migrate data, or broaden scope.
- Native Windows profile mutation will not be advertised unless equivalent reparse-point protections are implemented and verified. WSL is the supported Windows installation path for v0.2.0.
- The release will not promise or manufacture GitHub stars, forks, testimonials, or benchmark outcomes.

## Filesystem threat boundary

Malicious processes already running with the same effective UID as LaneOrchestrator are outside the v0.2.0 threat boundary because they can already access the user's private state and processes. Other users, unsafe filesystem objects, symlink and path attacks, and all cooperating LaneOrchestrator instances remain inside the threat boundary.

Within that boundary, mutation rejects unsafe ancestry, ownership, permissions, links, non-regular files, reserved lock-file destinations, and detected identity changes. A validated private advisory lock file serializes cooperating POSIX LaneOrchestrator mutations from destination inspection through atomic publication or cleanup. Advisory locking is serialization within this boundary; it is not claimed as a control against hostile code running with the same effective UID, and the design does not claim an unavailable portable compare-and-replace primitive.

## Audience

The primary audience is a Codex user who wants one safe entry point for implementation, debugging, review, research, or refactoring. The user may have no external agents, a small hand-picked set, or a large global catalog such as VoltAgent. They should not need to understand LaneOrchestrator's internal model lanes before first use.

Maintainers and security reviewers are a secondary audience. They need deterministic commands, stable JSON, documented invariants, reproducible tests, and explicit limitations.

## Product promise

> **Risk-aware agent routing for Codex. Works standalone, discovers the capabilities you already have, and requires independent review when the work is dangerous.**

## Architecture

```text
user task
    |
    v
$laneorchestrator skill
    |
    +--> control-plane CLI
    |       +--> configuration
    |       +--> doctor/status
    |       +--> bounded capability discovery
    |       +--> conservative route recommendation
    |       `--> auditable JSON
    |
    v
read-only Sol router
    |
    +--> Luna executor for verified bounded low-risk work
    +--> Terra executor for normal implementation
    `--> Sol plan -> Terra -> fresh Sol review for high-risk work
             |
             v
      verification evidence and final report
```

The Python control plane provides deterministic evidence and safety checks. It does not spawn models or claim authority over Codex's instruction hierarchy. The skill combines control-plane output with inspected repository evidence, emits the route card, and uses the host's supported custom-agent mechanism.

### Canonical Python package

The repository will add this focused package:

```text
laneorchestrator/
  __init__.py       package version and public constants
  __main__.py       `python3 -m laneorchestrator`
  cli.py            argument parsing, output selection, exit status
  config.py         defaults, schema validation, atomic private state
  diagnostics.py    typed PASS/WARN/FAIL/UNKNOWN results
  doctor.py         read-only environment and readiness checks
  discovery.py      bounded skill and agent discovery
  routing.py        deterministic lane recommendation
  models.py         role/model validation and fallback contracts
  plans.py          private preview plans and one-time confirmation tokens
  profiles.py       managed profile render/install/update/adopt/uninstall
  security.py       no-follow path and private-file primitives
```

Each module owns one concept. `cli.py` performs no policy calculations and delegates to typed module APIs. Human output and JSON output are rendered from the same result objects.

### Backward compatibility

These existing entry points remain available in v0.2.0 as thin wrappers:

- `skills/laneorchestrator/scripts/route.py`
- `skills/laneorchestrator/scripts/catalog.py`
- `scripts/install_agents.py`
- `scripts/install-agents.sh`
- `scripts/healthcheck.py`
- `scripts/validate.sh`

Policy, discovery, and filesystem behavior must live only in the canonical package. Wrapper tests prove output compatibility for supported existing arguments. Deprecation is documented before any later removal.

## Command-line contract

The canonical developer and skill-facing entry point is:

```text
python3 -m laneorchestrator <command>
```

Commands are:

- `doctor [--json]`: perform read-only readiness checks;
- `status [--json]`: summarize effective defaults/configuration and managed profile state;
- `configure [role options] [--json]`: create a private preview plan;
- `configure --apply <token> [--json]`: apply the unchanged, unexpired preview;
- `route [routing facts]`: emit schema-versioned routing JSON;
- `catalog [query and roots]`: emit schema-versioned capability JSON;
- `profiles install|update|adopt|uninstall [--json]`: preview a profile lifecycle operation;
- `profiles apply <token> [--json]`: apply the unchanged, unexpired profile plan;
- `benchmark [--json]`: run the committed evaluation corpus;
- `version [--json]`: report package, manifest, and schema versions.

CLI usage errors return exit status 2. Successful commands return 0. A completed command with a domain failure, safety refusal, or failing doctor result returns 1. Unexpected internal errors return 3 after a concise diagnostic; tracebacks are shown only with an explicit debug flag and must not reveal configuration secrets.

Machine-readable responses use a shared envelope:

```json
{
  "schema_version": 1,
  "command": "doctor",
  "ok": true,
  "data": {},
  "diagnostics": [],
  "errors": []
}
```

Command-specific payload schemas are documented and fixture-tested. Breaking schema changes require a new schema version.

## Zero-configuration defaults

Absence of user configuration is valid and does not create a file. Effective defaults are:

| Role | Model | Reasoning effort | Required |
| --- | --- | --- | --- |
| router | `gpt-5.6-sol` | `high` | yes |
| small-task executor | `gpt-5.6-luna` | `high` | no |
| main implementer | `gpt-5.6-terra` | `high` | yes |
| independent reviewer | `gpt-5.6-sol` | `high` | required for high-risk work |

The logical roles, not the default model names, form the stable configuration interface.

## Configuration

### State location

Persistent state lives below the effective Codex home:

```text
${CODEX_HOME:-~/.codex}/laneorchestrator/
  config.json
  receipts.json
  plans/
  backups/
```

`CODEX_HOME`, when set, must be an absolute path. The implementation rejects unsafe caller-controlled symbolic links and creates new state directories with mode `0700` and files with mode `0600` on POSIX systems. Unsupported permission guarantees produce a failing diagnostic before mutation.

### Schema

Configuration schema version 1 stores only logical preferences:

```json
{
  "schema_version": 1,
  "roles": {
    "router": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "small_task_executor": {"model": "gpt-5.6-luna", "reasoning_effort": "high"},
    "main_implementer": {"model": "gpt-5.6-terra", "reasoning_effort": "high"},
    "independent_reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}
  }
}
```

Unknown fields, duplicate logical roles, control characters, oversized values, relative state roots, and secret-like keys are rejected. Model identifiers and reasoning settings are syntactically validated but are not reported as available unless the host exposes authoritative evidence.

### Preview and confirmation

Mutation is always a two-step operation:

1. The preview command validates input and current state, renders exact destination paths and contents or hashes, stores a private plan, and returns a random one-time token.
2. The apply command requires that exact token and rechecks plan age, plan kind, current target hashes, configuration hashes, destinations, and symlink state.

Plans expire after ten minutes and are single-use. Tokens are generated with the Python `secrets` module and are bound by the stored plan. A failed or interrupted apply cannot be replayed. Applying unchanged state is idempotent.

Configuration writes hold the validated private advisory lock, use a private sibling temporary file, `fsync`, atomic replacement, and parent-directory synchronization where supported. Cooperating LaneOrchestrator writers are serialized across inspection, publication, and cleanup. Failure leaves either the previous complete file or the new complete file, never a partially written JSON document.

## Doctor and status

`doctor` is read-only and classifies every result as:

- `PASS`: directly verified;
- `WARN`: usable with a documented degradation;
- `FAIL`: mandatory requirement missing or unsafe;
- `UNKNOWN`: the host does not expose authoritative evidence.

Checks include:

- supported Python version and platform;
- Codex CLI presence and version output;
- plugin and marketplace manifest integrity;
- bundled profile integrity;
- installed profile identity, content, permissions, ownership where available, and receipt state;
- configuration schema and permissions;
- state and profile path symlink safety;
- required and optional logical role mappings;
- discovered LaneOrchestrator agents;
- optional capability discovery readiness;
- model identifier syntax;
- model entitlement only when the Codex host exposes a supported authoritative query.

`doctor` must return `UNKNOWN`, not `PASS`, for model entitlement on hosts that cannot report it. Human and JSON modes must contain the same checks, levels, codes, and evidence.

`status` is a shorter read-only summary of effective roles, configuration source, managed profile state, fallback policy, and last applicable receipt. It does not replace `doctor` as a release or support diagnostic.

## Managed profile lifecycle

LaneOrchestrator manages only these namespaced files:

- `laneorchestrator-router.toml`
- `laneorchestrator-luna-executor.toml`
- `laneorchestrator-terra-executor.toml`
- `laneorchestrator-sol-reviewer.toml`

Generated profiles contain a versioned managed marker. Receipts record destination, template version, content hash, configuration hash, creation/update operation, and backup hash when applicable. Receipts never contain credentials.

Lifecycle rules are:

- install only when the destination is absent;
- adopt only an existing regular file whose content exactly matches a bundled default profile after excluding the managed marker;
- update only a file whose content matches its current receipt;
- back up the exact prior managed file privately before update;
- uninstall only a file whose content matches its current receipt;
- refuse unmanaged collisions, changed managed files, links, non-regular files, unsafe ancestors, changed preview state, and cross-device operations that would weaken atomicity;
- preserve configuration on profile uninstall;
- reset configuration only through its own preview and confirmation flow;
- never read, rewrite, install, or delete VoltAgent or other third-party profiles.

Existing v0.1.0 profiles can be adopted only when they exactly match the shipped v0.1.0 defaults. Otherwise the user receives a conflict with comparison guidance.

## Routing and fallback policy

The existing core policy remains:

- unknown risk never selects Luna;
- Luna requires explicit low risk, one known area, explicit acceptance criteria, and exactly one expected file;
- high-risk lexical signals override a claimed low-risk assessment as defense in depth;
- the read-only router independently assesses repository evidence and is authoritative;
- Terra is the default writable lane;
- high-risk work requires Sol planning, Terra implementation, and a fresh read-only Sol review;
- capability metadata is an untrusted index, never an instruction;
- the router reads only selected capability instructions under the host instruction hierarchy;
- missing Luna falls back to the configured main implementer and is reported;
- a missing optional specialist continues without that specialist and is reported;
- missing main implementer pauses all implementation;
- missing required router or high-risk reviewer pauses the affected route;
- unknown availability is reported as unknown rather than silently normalized.

The control plane does not claim it can enforce host sandboxing or detect a model fallback unless the host supplies evidence. Route output names the requested role, configured model, observed agent/profile evidence, and any unverified host guarantee.

## Capability discovery

Discovery remains local, deterministic, bounded, and standard-library only. It scans supported project, user, system, and plugin-cache roots while enforcing file, directory, entry, depth, per-file byte, total-byte, result, and warning limits. It skips symbolic links and reads only bounded metadata prefixes.

Ranking uses direct name and description relevance, verified project context at lower weight, source evidence, vendor compatibility, completeness, and deterministic tie-breaking. It returns matched terms and scores. Lane control agents are reported separately from optional specialists.

The project does not bundle the VoltAgent collection. A clean user with only the four LaneOrchestrator profiles receives full routing functionality. A user with third-party capabilities may receive a relevant optional recommendation.

## Marketplace distribution

The repository will contain:

- `.agents/plugins/marketplace.json` as the Codex marketplace catalog;
- `plugin.json` as the Agent Plugins v1 manifest;
- `.codex-plugin/plugin.json` as Codex compatibility metadata;
- one canonical plugin source rooted in this repository, with local marketplace installation verified before publication.

The public installation flow is:

```sh
codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref main
codex plugin add laneorchestrator@laneorchestrator
```

The README also documents `codex plugin marketplace upgrade laneorchestrator`, plugin reinstallation/update behavior, removal, profile uninstall, configuration reset, and the difference between removing plugin registration and removing managed agent files.

The first `$laneorchestrator` invocation checks readiness. If the host does not directly expose the bundled profiles, the skill shows an exact profile-install preview and asks for the bound token before applying it. It then runs `doctor` and proceeds only when mandatory checks pass.

## User experience

The first README screen contains:

- product name and one-sentence promise;
- CI, release, license, and Python badges;
- a short deterministic terminal demonstration;
- exact marketplace installation commands;
- one `$laneorchestrator` invocation;
- a statement that external agent packs are optional;
- a link to a 90-second demonstration.

The skill emits a compact route card before mutation:

```text
Lane: Terra
Why: multi-file feature with normal implementation risk
Evidence: Python service, 3 affected files, existing tests
Capabilities: python-pro
Verification: focused tests, complete validator
Safety: workspace execution only
```

The user is not required to understand model lanes before first use. Documentation progressively explains routing, security, configuration, and limitations.

## Documentation and assets

The public documentation set is:

```text
docs/
  getting-started.md
  concepts.md
  configuration.md
  commands.md
  examples/
    small-change.md
    normal-feature.md
    high-risk-change.md
  architecture.md
  security-model.md
  threat-model.md
  benchmarks.md
  troubleshooting.md
  compatibility.md
  roadmap.md
```

The repository also includes a deterministic terminal transcript, an architecture diagram, a lightweight visual demonstration, a reproducible social-preview image, three complete route examples, and a factual comparison with manual capability selection. Assets avoid copyrighted third-party branding and retain editable source where practical.

Every documented local command is exercised by CI or by a documentation fixture. Examples are generated or verified against current JSON schemas. The README states limitations next to relevant claims.

## Open-source repository surface

Before visibility changes, the repository will have:

- a concise GitHub description, homepage, and focused topics;
- README, MIT license, notice, code of conduct, contribution guide, support policy, security policy, changelog, release guide, and roadmap;
- issue forms for bugs and feature requests plus security and support routing;
- a pull-request template with risk and evidence fields;
- GitHub Discussions enabled at publication;
- a protected `main` ruleset appropriate for a single-maintainer project;
- pinned CI actions, minimal workflow permissions, concurrency limits, and timeouts;
- static analysis, dependency review, and secret scanning where meaningful for the dependency-free Python runtime;
- good-first-issue candidates based on genuine separable improvements;
- no fabricated users, testimonials, benchmarks, sponsorships, or adoption numbers.

## Test strategy

All new behavior follows red-green-refactor TDD. Tests assert public behavior, not implementation details.

### Unit coverage

Unit tests cover defaults, schema validation, migrations, atomic writes, diagnostic levels, human/JSON parity, CLI status, route policy, discovery, model syntax, confirmation plan expiry and replay, profile rendering, receipts, adoption, update, uninstall, and backward-compatible wrappers.

### Adversarial coverage

Tests cover blank, malformed, oversized, deeply nested, control-character, and secret-like input; prompt injection in metadata; ranking manipulation; duplicate names; vendor mismatch; high-risk evasion; symlink and dangling-link paths; reparse-point detection where supported; races between cooperating instances; advisory-lock validation and exclusivity; collisions; interrupted writes; managed drift; unsafe permissions; corrupt state; expired/replayed confirmation; unavailable roles; output flooding; and discovery resource exhaustion. Race claims apply to other users, unsafe filesystem objects, and cooperating LaneOrchestrator instances within the documented threat boundary, not malicious same-effective-UID code.

### Integration journeys

Tests create isolated homes and exercise:

1. clean user with no external capabilities;
2. user with optional specialists;
3. unmanaged collision;
4. exact v0.1.0 adoption;
5. configuration preview/apply;
6. managed update with backup;
7. drift refusal;
8. safe uninstall preserving unrelated files and configuration;
9. high-risk route with missing Sol;
10. normal route with missing Terra;
11. Luna fallback to Terra;
12. local Codex marketplace add/install/list/remove against the repository package.

## Benchmark design

The committed evaluation corpus contains at least 200 representative tasks with reviewed expected lanes and relevant specialist labels. The benchmark reports:

- overall route accuracy;
- high-risk recall, with zero known high-risk false negatives required in the curated corpus;
- false-positive rate as a separate conservative-routing cost;
- top-1 and top-3 specialist relevance;
- deterministic repeatability;
- keyword-stuffing and vendor-mismatch resistance;
- large-catalog elapsed time and configured resource limits.

The benchmark documentation states corpus construction, labeling process, limitations, hardware context, and the distinction between lexical helper results and the authoritative repository-aware router. Results are generated, not hand-edited.

Release thresholds are:

- at least 98% overall lane agreement with reviewed corpus labels;
- 100% recall for reviewed high-risk corpus cases;
- at least 90% top-3 recall for cases with an applicable installed specialist;
- 100% identical output across repeated deterministic runs;
- 100% pass rate for committed keyword-stuffing, vendor-mismatch, and high-risk-evasion cases;
- completion of the maximum-size bounded discovery fixture in less than ten seconds on every release CI job.

False-positive escalation is reported even when the overall agreement threshold passes. A threshold change requires a documented corpus or policy rationale in the changelog and benchmark report.

## CI and platform matrix

Release CI includes:

- Ubuntu with Python 3.9 and the latest stable CPython release supported by `actions/setup-python` on the release date;
- macOS with Python 3.9 and that same latest stable CPython release;
- Windows control-plane tests with supported Python versions;
- POSIX installer and no-follow security tests on Ubuntu and macOS;
- documentation command and link checks;
- benchmark regression checks;
- manifest and release artifact validation.

WSL is the documented Windows installation path for v0.2.0. Native Windows read-only commands may be supported, but native profile mutation remains disabled unless secure reparse-point behavior is implemented and verified.

The latest stable Python matrix value is an explicit version literal recorded in the workflow and compatibility documentation. Floating values such as `3.x` are not used.

## Security verification

Before publication, the release candidate receives:

- a fresh Codex deep-security scan using preflight, saturated discovery, canonical manifest acceptance, centralized validation, attack-path analysis, canonical completion, and a generated report;
- replay of every previously confirmed installer and routing exploit;
- prompt-injection and resource-exhaustion replays;
- secret scanning and dependency review;
- verification of pinned actions and workflow permissions;
- independent read-only Sol review of implementation, tests, release workflow, and security claims;
- explicit listing of coverage and limitations.

No unresolved Critical or High finding may ship. A Medium finding requires written risk acceptance in the release security report. The public report omits sensitive absolute paths and local account data.

## Release and publication gates

The v0.2.0 release may be published only when all of these are true:

1. The working tree and primary `main` checkout are clean and synchronized.
2. Full local validation passes from the release commit.
3. Every CI matrix job passes without annotations.
4. Clean install, v0.1.0 adoption, update, drift, and uninstall journeys pass.
5. Local Codex marketplace installation succeeds from an isolated Codex home.
6. Security verification completes with no unaccepted blocking finding.
7. Benchmark thresholds and documentation agree with generated results.
8. Every documented command and relative link is verified.
9. Plugin version, Python package version, changelog, release notes, tag, and artifact names agree.
10. The release archive contains only intended distributable files and has published SHA-256 checksums.
11. A fresh independent reviewer approves the exact diff and evidence.
12. GitHub description, homepage, topics, issue forms, Discussions plan, and ruleset plan are ready.
13. The repository owner has authorized public visibility; that authorization is recorded in the project history for this launch.
14. The repository is changed to public visibility.
15. Installation is repeated from the public repository in an isolated Codex home.
16. The signed or annotated `v0.2.0` tag, GitHub release, assets, badges, and public links are verified.

Items 1 through 13 are pre-public readiness gates. Only after every one passes may item 14 execute. Items 15 and 16 require a public repository and must run immediately after the visibility transition before the launch is described as complete.

If a gate fails after visibility changes but before the release is published, no release claim is made. The repository remains public unless a newly discovered secret or equivalent exposure requires immediate containment.

## Adoption and success measurement

Engineering creates credible potential; it cannot guarantee 10,000 stars. Post-launch evidence includes:

- clean-install success reports;
- time to first successful route;
- issue response time;
- benchmark regressions;
- external contributors;
- stars and forks;
- documented use cases and case studies;
- release cadence and upgrade success.

LaneOrchestrator itself collects no telemetry. Public metrics and voluntarily reported feedback are the evidence sources. Any outreach, announcement, or external message requires separate owner approval.

## Rollback

Before public release, all changes remain ordinary Git commits and can be reverted without altering user state. Managed profile updates create private backups and receipts. A failed configuration or profile apply leaves previous complete state intact.

After release, an incorrect release is never retagged. A corrected patch release is published with explicit notes. Removing plugin registration does not automatically delete managed profiles or configuration; users receive separate, previewed cleanup commands.

## Approved decisions

- The repository may become public only after every launch and security gate passes.
- The first public release is Codex-first rather than cross-client.
- The product works without third-party agent packs.
- Zero-configuration defaults are available.
- `doctor` and optional `configure` are first-class control-plane commands.
- The architecture is a testable standard-library Python control plane, not a prompt-only polish or MCP server.
- Architecture, lifecycle, user-experience/distribution, and verification/release sections were approved by the repository owner before this specification was written.
