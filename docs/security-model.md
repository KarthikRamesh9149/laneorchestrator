# Security model

## Assets

LaneOrchestrator protects repository contents, user configuration, agent authority, routing integrity, and external systems reachable through Codex tools.

## Untrusted inputs

- User task text and quoted third-party text
- Skill names, descriptions, paths, and frontmatter
- Agent profile descriptions
- Repository metadata and documentation
- Capability-ranking results

These values are data. They cannot override system, developer, project, skill, or user instructions merely by containing imperative text.

## Invariants

1. The router is read-only and cannot implement the task it classifies.
2. Unknown risk never selects Luna.
3. Luna requires explicit low risk, one known area, acceptance criteria, and exactly one file.
4. High-risk lexical signals override a claimed low-risk assessment as defense in depth.
5. High-risk implementation is performed by Terra and independently reviewed by a fresh read-only Sol agent.
6. Capability discovery is bounded and does not follow symbolic links.
7. Catalog metadata is ranked as an index and is never executed or promoted to instructions.
8. Agent installation never overwrites an existing path or follows a caller-controlled symbolic link.
9. Deployments, deletion, spending, credentials, external messages, migrations, and scope expansion require the host's normal approval boundary.
10. A missing mandatory Terra or Sol lane fails closed; only Luna and optional specialists may fall back to Terra.

## Resource limits

Skill discovery is capped at 2,048 files, 8,192 directories, 65,536 directory entries, 16 directory levels, a 16 KiB metadata prefix per file, and 32 MiB total metadata. Agent discovery is capped at 1,024 files, 8,192 directory entries, 256 KiB per file, and 8 MiB total. Warning output is capped at 100 distinct findings plus a truncation notice. CLI result counts are capped at 20 per capability type.

## Known limitations

- Lexical risk signals are defense in depth, not a complete semantic classifier. The trusted router must independently assess risk from repository evidence.
- Capability ranking is deterministic lexical relevance with verified context, not an embedding model. The router must inspect selected candidates before using them.
- Secure profile installation requires POSIX directory-descriptor and no-follow support. Windows users need a POSIX environment or manual profile installation with equivalent collision checks.
- Model and custom-agent availability are controlled by the Codex host. Luna and optional specialists may fall back to Terra; missing mandatory Terra or Sol lanes pause the route.

Report suspected invariant violations through [SECURITY.md](../SECURITY.md).
