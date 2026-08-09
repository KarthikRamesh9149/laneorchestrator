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

Profile and configuration updates use private exact-state previews, bound tokens, descriptor-relative no-follow checks, private temporary files, atomic replacement, and parent-directory synchronization where supported. A changed, expired, or replayed preview fails without publishing a partial configuration document.

These controls serialize cooperating LaneOrchestrator writers inside the documented POSIX boundary. They do not claim protection from malicious code sharing the same effective user identity, a compromised host, or an external system compromise. Native Windows mutation is disabled in this release; use WSL for configuration and profile mutation.

## Known limitations

- Lexical risk signals are not complete semantic classification; the trusted router must assess repository evidence.
- Deterministic lexical ranking is not an embedding model and does not replace router review.
- Model and custom-agent availability are controlled by the Codex host.
- `CODEX_HOME`, if set, must be absolute. It identifies state and agent roots but does not grant mutation approval.

Report suspected invariant violations through the private process in [SECURITY.md](../SECURITY.md). The fuller [threat model](threat-model.md) records assumptions and non-goals.
