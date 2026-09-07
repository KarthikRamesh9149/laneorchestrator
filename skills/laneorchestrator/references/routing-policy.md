# Adaptive model and thinking policy

Astra is the coordinator. The role describes responsibility, the specialist supplies expertise, and each task receives an independent model/effort choice. Model names are not permission boundaries.

| Task | Adaptive preference | Thinking |
| --- | --- | --- |
| Coordination | Astra | High starting point |
| Small, clearly scoped change | Luna or Terra, chosen by Astra | High |
| Routine implementation | Sol or Terra, chosen by Astra | Any host-supported level, chosen by Astra |
| Demanding implementation | Prefer Astra | Chosen by Astra |
| Investigation | Chosen by Astra | Chosen by Astra |
| Independent review | Prefer Sol or Astra | Chosen by Astra |

Routine examples: Terra/medium for a straightforward component implementation; Sol/high for a change requiring careful integration reasoning; Sol/medium for a well-understood feature; Terra/xhigh when the inspected task warrants it. These are illustrations, not measured performance guarantees or a hard lookup table. Never infer thinking from the model name alone.

`astra-adaptive` follows the table. `all-astra` selects Astra for every task while still varying thinking. `manual` uses the user's supplied settings. Explicit user settings override presets but must still be supported by the host. No specialist is permanently tied to a model. Read current host capabilities; API model documentation is not a substitute for the Codex host's effort list.

Separate uncertainty, difficulty, and consequences. Investigate unknown scope before implementation. A wording change, filename, or non-ASCII sentence alone does not increase risk. Preserve evidence of security, authorization, data integrity, migrations, public contracts, and high blast radius; require a fresh independent review for consequential changes. A specialist cannot waive a review requirement or expand the user's authorization.

Choose thinking based on ambiguity, reasoning depth, number of interacting components, and verification difficulty. Do not always select the maximum. Reassess on a substantive failure or changed scope; do not traverse a fixed Luna/Terra/Sol/Astra ladder. Stop automatic retries after two failed attempts per packet and return the unresolved issue and evidence.
