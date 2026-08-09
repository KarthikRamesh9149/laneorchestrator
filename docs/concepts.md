# Concepts

## Route cards and evidence

A route card records the requested work lane, the evidence used for the decision, selected optional capabilities, verification expectations, and safety boundary. The router remains read-only; a writable executor does not choose its own authority.

Task text, repository metadata, skill frontmatter, agent descriptions, and ranking output are untrusted data. Metadata can influence a shortlist but never becomes an instruction or approval.

## Lanes

| Lane | Use | Failure behavior |
| --- | --- | --- |
| Luna | Verified low-risk work in one known area with explicit acceptance criteria and one file | Falls back to Terra when Luna is unavailable. |
| Terra | Normal implementation, integration, multi-file, or uncertain work | Pauses when the required Terra role is unavailable. |
| Sol plan -> Terra -> Sol review | Elevated-risk work such as security, credentials, migrations, persistent data, public contracts, or high blast radius | Pauses when required Sol planning or review is unavailable. |

The lexical signals are defense in depth, not a semantic classifier. The router must assess repository evidence independently.

## Optional specialists

Discovery reads bounded metadata from configured skill and agent roots, skips symbolic links, and returns source and matched-term evidence. A specialist may be absent or rejected without blocking a route. Third-party agent packs are optional and are never installed automatically.

## Preview and apply

Configuration and profile operations use a preview followed by an explicit, short-lived bound token. Preview is not a mutation at the destination. An apply must match the reviewed state; changed, expired, or replayed plans fail safely. Details and recovery steps are in [configuration](configuration.md).
