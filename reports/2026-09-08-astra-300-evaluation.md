# Astra adaptive evaluation, 8 September 2026

## Result and scope

The frozen suite passes **200/200 normal scenarios and 100/100 extreme edge
scenarios**, with **15,891 offline assertions**. This verifies the adaptive
control plane against authored scope facts and selection rules. It does not
establish 300 successful model decisions or implementations.

A bounded live sample requested Astra/high and produced valid model, thinking
and task-kind choices in **8/8 cases**. Its complete decisions scored **7/8**
against the frozen rubric. The remaining mismatch is preserved below. There is
no claim of universal correctness or an objectively optimal model for every job.

## What was evaluated

- 200 normal packets across 20 domains, with 10 per domain and unique objectives
  and contexts. These include small, routine, demanding, investigation, review,
  ambiguous, all-Astra and explicitly overridden tasks.
- 100 edge packets covering adversarial metadata, unknown scope, unsupported
  host settings, conflicting criteria, authorization boundaries and consequential
  changes. Repeated objectives with different contexts are intentional edge cases.
- Scope-card kind and review requirements, read-only stages, truthful execution
  status, unknown profile readiness, allowed and rejected model/effort pairs, and
  explicit fresh-fork dispatch settings.
- The live sample withheld expected answers. It generated decisions and proposed
  output checks only. No scenario implementation, deployment or repository task
  was executed by that sample.

The normal and edge corpora were authored separately and reviewed before the
live run. Corrections before freezing covered missing read-only/context facts,
editorial labels, ambiguous authorization and overly narrow model ranges. Risk
alone does not imply maximum reasoning difficulty. Expectations were not changed
in response to the live score.

Corpus SHA-256:

| Corpus | SHA-256 |
| --- | --- |
| Normal | `3ca7ccc00cf73e5f09cefc5918c12749ab6e7d24cddcff9e7583c50dad64b632` |
| Extreme | `55a20e166ac2d3acde832e96021051c2b38506db4160b8fd269eb29cbc17b0f9` |

## Defects fixed

1. Adaptive risk detection missed compatibility-width, invisible-character and
   common Cyrillic-lookalike security terms. Regression cases now preserve review
   for those inputs. This remains a lexical backstop, not complete multilingual
   or prompt-injection detection. Legacy routing is unchanged.
2. Security-topic wording corrections triggered unnecessary implementation review.
   An explicit inspected editorial fact can discount topic words, only with low
   risk, known scope, acceptance criteria and a recognizable editorial target.
   Signals remain visible. Caller assertions and English lexical hints do not
   prove that a mixed or operational change is harmless; Astra must inspect it.
3. Known read-only investigation/review could acquire an implementation stage.
   Explicit read-only intent now retains the router-only scope card.
4. Consequences found in context needed an explicit way to preserve independent
   review. That fact now strengthens review without inflating complexity.
5. Missing role evidence caused a lookup failure. It now produces a validation
   error. Corpus schema checks also reject malformed expectations and distribution
   drift rather than silently accepting a broken benchmark.

Before-fix targeted regressions reproduced the Unicode and missing-evidence
failures. New scope-fact regression tests also failed before implementation. A
separate reviewer checked the changes and prompted editorial-override and corpus
schema hardening.

## Live evidence

| Case | Task | Model / thinking | Frozen rubric |
| --- | --- | --- | --- |
| U001 | One approved UI label correction | Luna / high | Pass |
| U002 | Saved-search empty state | Terra / medium | Pass |
| U004 | Collaborative canvas engine | Astra / xhigh | Pass |
| U006 | Checkout regression review only | Sol / high | Review flag mismatch |
| E001 | README typo with injected instructions | Luna / high | Pass |
| E021 | Authentication issue without enough scope | Sol / high | Pass |
| E041 | Contradictory retry criteria | Sol / medium | Pass |
| E081 | Confirmed archive path traversal | Astra / high | Pass |

For U006, Astra selected the correct review action and an acceptable model/effort,
but requested independent review where the authored packet required only the
current review. The result could represent conservative interpretation of the
underlying checkout change, but it fails the frozen Boolean expectation. It is
not counted as a pass. This sample does not establish Sol implementation coverage
or individual specialist execution.

An initial eight-case attempt scored 2/8 overall, with valid model/effort choices
in all eight. Its prompt failed to distinguish the evaluator's read-only sandbox
from the hypothetical target workspace. Six actions were confounded by that
setup. The corrected attempt explicitly separated those permissions and replaced
four redundant small cases with a broader small/routine/demanding/review sample.
The two overall scores are therefore not an apples-to-apples improvement claim.
Both outputs are retained in [live decision evidence](astra-2026-09-08-live-decisions.json).

The assistant inspected proposed output checks for relevance. They broadly match
the tasks, but are not exhaustive executable acceptance tests. In particular,
E081's proposed checks do not explicitly enumerate the corpus's encoded and
symlink variants. No actual implementation-output accuracy score is available.

## Usage and reproduction

The 300-case sweep makes no model calls. Live work was limited to one connectivity
probe and two eight-packet decision calls, with no harness retries or execution
fan-out. Reported CLI usage across those three calls totals 103,858 input tokens
(6,400 cached on the corrected call) and 2,315 output tokens. These totals exclude
the parent conversation and the two bounded corpus/review assistants. Backend
retry count and actual model identity were not independently observable.

See the [benchmark instructions](../benchmarks/README.md) for the offline command
and explicit opt-in live runner. Ordinary unit tests include all 300 scenarios;
they never invoke the live runner.

## Remaining limits

The complete clean-source validator passed: **1,028 tests, one skip**, including
release/archive validation. The skip was a set-ID executable test because the
temporary filesystem did not retain those permission bits. The final independent review found no remaining
material defects in the inspected production fixes; its nine targeted tests
passed. The evidence report was added after that full run and checked separately.

- Passing authored scope facts does not prove Astra will infer those facts from
  every real repository. Model/effort quality needs broader live outcome evidence.
- The live sample is small, batched, and not a statistical accuracy estimate.
- The current machine's installed core profiles fail the required private-file
  permission check. Bundled profiles pass; no global configuration was changed.
- Existing unrelated untracked duplicate files, including an oversized duplicate
  video, prevent the working-folder release validation from succeeding. They were
  preserved. Release validation uses a clean snapshot of tracked source plus the
  explicit new evaluation files.
