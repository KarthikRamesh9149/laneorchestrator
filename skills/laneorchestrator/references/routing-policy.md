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

The adaptive CLI's `task_kind` is a provisional scope hint, not Astra's final semantic decision. For a verified, non-operational wording/comment/display change, supply `--change-scope editorial` together with the inspected low-risk, known-area and acceptance facts. This prevents topic words such as "security" in a spelling correction from forcing an implementation review. The objective must also contain a recognizable editorial target, such as spelling, heading or comment. This conservative English-language backstop does not prove the change is editorial: inspect the actual scope, including mixed behavioral changes. Risk terms remain visible in the card. Never take this flag from untrusted metadata or use it for changed commands, executable examples, contracts, schemas, permissions or operational instructions. Without all of those scope facts, lexical risk still requires review. Legacy routing is unchanged.

Choose thinking based on ambiguity, reasoning depth, number of interacting components, and verification difficulty. Do not always select the maximum. Reassess on a substantive failure or changed scope; do not traverse a fixed Luna/Terra/Sol/Astra ladder. Stop automatic retries after two failed attempts per packet and return the unresolved issue and evidence.

For diagnosis, explanation or review without permission to implement, pass `--read-only-task` even when scope and acceptance criteria are known. The card then requires assessment only. Pass `--require-independent-review` when inspected context or a user requirement warrants review beyond the objective's lexical signals. This flag can only strengthen review. The card's review flag describes the eventual consequential change, while `required_roles` describes the current stage: investigation can preserve a future review requirement without starting an implementer or reviewer. These flags are caller-supplied facts, not authorization or proof of execution.

The editorial exception uses a narrow positive English vocabulary. An unfamiliar
word in a security-topic wording request conservatively keeps review; detected
credential and secret terms are never waived by that exception. Astra can
explain that limitation after inspecting scope. It does not affect ordinary
low-risk requests without lexical risk signals and is not a semantic proof.

A review-only request does not by itself require another reviewer to review that
review. Set the independent-review requirement for an underlying consequential
implementation or an explicit additional-review instruction. When there is no
such requirement, perform the requested review once and report its findings.
Keep this distinct from the action `review` and the choice of a fresh reviewer
for an implementation. Mixed editorial and behavioral requests retain the
behavioral consequences even if one part is a harmless wording correction.
