# Threat model

## Protected assets

LaneOrchestrator protects routing integrity, repository contents, user configuration, managed profiles, and the authority boundaries around Codex tools. It does not collect telemetry.

## Inputs and trust boundary

Task text, copied third-party text, repository files, capability metadata, paths, and ranking output are untrusted. Discovery constrains traversal and reads metadata as an index only. The router may inspect selected candidates under the host instruction hierarchy, but untrusted content cannot grant authority, supply approval, or change the precedence of instructions.

## Controls

- The router is read-only; writable executors do not classify their own authority.
- Unknown risk does not select Luna. High-risk lexical signals provide an additional conservative check.
- Required Terra and Sol roles fail closed when absent; only Luna and optional specialists can fall back to Terra.
- Discovery limits files, directories, bytes, depth, and results, and skips symbolic links.
- Profile and configuration mutation use exact-state previews, short-lived bound tokens, no-follow validation, and atomic publication within the documented POSIX boundary.

## Limits and non-goals

Lexical detection is not complete semantic risk analysis, and lexical ranking is not a substitute for repository-aware routing. The mutation controls are not a defense against malicious code with the same effective user identity, a compromised host, or an externally compromised Codex environment. Advisory locking serializes cooperating LaneOrchestrator writers within its boundary; it does not claim a portable hostile-process compare-and-replace primitive.

Native Windows mutation is disabled for this release because equivalent reparse-point protections are not verified. See [security model](security-model.md) and [compatibility](compatibility.md).
