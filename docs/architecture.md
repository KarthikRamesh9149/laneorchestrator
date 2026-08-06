# Architecture

LaneOrchestrator separates decision-making from implementation so a writable model never selects its own authority.

```text
task + repository evidence
          |
          v
read-only Sol router ----> bounded route card
          |                       |
          |                capability catalog
          |                  (untrusted index)
          v
 Luna executor or Terra executor
          |
          v
 verification evidence
          |
          v
 read-only Sol reviewer for high-risk work
```

## Components

- `route.py` converts explicit scope and risk facts into a conservative model lane. Unknown risk and recognized high-risk signals select the Sol-controlled path.
- `catalog.py` discovers local skills and agent profiles within file, byte, depth, and result limits. Ranking is lexical and transparent; matched terms and source are returned with each candidate.
- `laneorchestrator-router` is the read-only control plane. It inspects repository evidence, chooses capabilities, and creates a bounded execution packet.
- Luna handles only verified one-file, low-risk work. Terra is the default writable implementation lane. A fresh read-only Sol agent reviews high-risk work.
- `install_agents.py` installs the four namespaced profiles with collision checks and descriptor-relative no-follow operations.

## Data flow

Capability descriptions never become instructions. The catalog returns JSON index records. The router may then read only selected capability files under the host's normal instruction hierarchy and approval boundaries.

## Fallbacks

If Luna or an optional specialist is unavailable, the route falls back to Terra at high reasoning effort and reports the substitution. If Terra is unavailable, implementation pauses. If Sol is unavailable for required high-risk planning or review, the high-risk route pauses rather than dropping an independent control. Missing capabilities are named but never installed automatically.
