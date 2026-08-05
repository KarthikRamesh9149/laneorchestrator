---
name: laneorchestrator
description: Adaptively route a Codex task to the right installed skills, custom agents, and GPT-5.6 Luna, Terra, or Sol lane. Use for implementation, debugging, reviews, research, refactors, or multi-step work when Codex should inspect project context and choose capabilities automatically rather than requiring the user to name them.
---

# LaneOrchestrator

Use this as the single entry point for work that benefits from capability selection. It produces a visible route, then performs normal in-scope work without waiting for a second prompt.

## Route a task

1. Read project instructions and inspect the relevant repository state before selecting a lane. Treat the user's objective, current chat, `AGENTS.md`, project docs, manifests, Git status, and nearby code as primary context.
2. Seed the lane recommendation with this skill's bundled `scripts/route.py`, passing only facts already established about file count, known ownership, and acceptance criteria. Then discover installed capabilities with `scripts/catalog.py` using the objective and current working directory. Read only the selected candidates' `SKILL.md` or agent profile; do not load the entire catalog.
3. Read `references/routing-policy.md` and classify complexity, risk, and required autonomy.
4. Emit a compact route card before changing files:

   ```text
   Lane: Luna | Terra | Sol plan → Terra → Sol review
   Context: <facts inspected>
   Capabilities: <selected skills and specialist, or none>
   Verification: <commands or evidence>
   Safety: executing | paused for <consequential action>
   ```

5. Execute the selected route through the host's supported custom-agent mechanism. If a selected profile or model cannot run, use Terra / High as the fallback and state the substitution in the route card.
6. Verify proportionately, report evidence, and state remaining risks. For high-risk work, use a fresh read-only Sol reviewer after implementation.

## Lane policy

- **Luna / High:** one known area, explicit success criteria, low blast radius, and no public API, schema, auth, security, payment, migration, or integrity change.
- **Terra / High:** default implementation lane for multi-file, integration, uncertain, or ordinary feature work. Prefer the highest-ranked relevant specialist.
- **Sol / High:** plan and independently review architecture-sensitive, public-contract, auth/security, financial, data-integrity, migration, concurrency, or high-blast-radius work. Terra implements after planning.

Never silently install a missing capability. Name the gap and offer a separate install/create action. Respect every selected skill's own approval boundaries. Pause for deploys, external messages, spending, deletion, credentials, data migrations, or scope expansion.

## Project briefing

Only when explicitly invoked as `$laneorchestrator init`, create `.laneorchestrator/BRIEF.md` from `references/brief-template.md`. Draft it from existing project evidence, mark uncertainty, and let the user review it. Do not create this directory during ordinary routing.
