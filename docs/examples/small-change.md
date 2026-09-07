# Small change: correct a README typo

## Request

> `$laneorchestrator Correct “instalation” in the README installation heading. Keep the rest unchanged.`

## What Astra inspects

The heading exists, the change is in one file, the replacement is explicit, and no behavior or public interface changes. There is no need to invent a larger implementation workflow.

## Selection and execution

An appropriate adaptive choice is a core executor using **Luna/high**; **Terra/high** is also allowed. Astra chooses from host-supported settings. A specialist is optional for this task.

The executor edits the heading and inspects the diff. It does not add a test that simply repeats the replacement string. If the heading is generated or the request actually changes installation semantics, Astra reassesses the expanded scope.

## Completion evidence

The handoff identifies the corrected heading and confirms that the diff contains only the intended edit. It does not claim a test suite ran unless it did.

This is an illustrative workflow, not a recording or model benchmark. Existing integrations can consult the [legacy route payload](legacy/small-change.md).
