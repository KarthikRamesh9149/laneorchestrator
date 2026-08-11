# Security model

## Assets and inputs

LaneOrchestrator protects repository contents, user configuration, managed profile integrity, routing authority, and external systems reachable through Codex tools. Task text, skill frontmatter, agent descriptions, repository metadata, paths, and capability rankings are untrusted data.

## Invariants

1. The router is read-only and does not implement the task it classifies.
2. Unknown risk never selects Luna; Luna needs explicit low risk, one known area, acceptance criteria, and one file.
3. High-risk lexical signals are defense in depth; high-risk work requires Sol planning, Terra implementation, and a fresh read-only Sol review.
4. Discovery is bounded, source-aware, and does not follow symbolic links. Metadata is an index, never executable instruction text.
5. Agent lifecycle operations do not overwrite an existing path or follow caller-controlled symbolic links.
6. Required Terra and Sol roles fail closed. Luna and optional specialists may fall back to Terra only where the route permits it.
7. External, destructive, costly, credential-bearing, or scope-expanding actions remain subject to the host approval boundary.

## Mutation boundary

Profile and configuration updates use private exact-state previews, bound tokens, matching explicit approvals, descriptor-relative no-follow checks, private temporary files, atomic replacement, and parent-directory synchronization where supported. A changed, expired, or replayed preview fails without publishing a partial configuration document.

These controls serialize cooperating LaneOrchestrator writers inside the documented POSIX boundary. They do not claim protection from malicious code sharing the same effective user identity, a compromised host, or an external system compromise. Native Windows mutation is disabled in this release; use WSL for configuration and profile mutation.

## Regression boundaries

Security regressions exercise dangling and live destination links, unsafe filesystem objects, bounded metadata reads, high-risk lexical evasions, malformed or replayed plans, and cooperating-writer races. Descriptor-relative POSIX controls protect against other users and unsafe filesystem objects; they do not provide hostile same-effective-user compare-and-swap semantics. Capability metadata remains untrusted index data: it is bounded and ranked as text, never executed as instructions. Diagnostic path and message output is bounded and redacted where it could otherwise expose mutation tokens.

## Static-analysis evidence

The Security workflow uses a bounded standard-library AST scanner for private repositories where GitHub Code Scanning is unavailable. It analyzes the committed `laneorchestrator` and `scripts` trees and saves deterministic SARIF as a workflow artifact. This narrow gate detects a small set of high-confidence Python risks; it is not equivalent to CodeQL. Public repositories run the pinned CodeQL actions and upload Code Scanning results and the analysis database.

## Known limitations

- Lexical risk signals are not complete semantic classification; the trusted router must assess repository evidence.
- Prompt-injection-like metadata cannot override the control plane, but no lexical filter can prove that a model will never follow untrusted text in another host context.
- Deterministic lexical ranking is not an embedding model and does not replace router review.
- Model and custom-agent availability are controlled by the Codex host.
- `CODEX_HOME`, if set, must be absolute. It identifies state and agent roots but does not grant mutation approval.

Report suspected invariant violations through the private process in [SECURITY.md](../SECURITY.md). The fuller [threat model](threat-model.md) records assumptions and non-goals.
