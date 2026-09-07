# Demanding change: event-stream recovery

## Request

> `$laneorchestrator Fix stream recovery after reconnects. Prevent duplicate events and checkpoint gaps.`

## What makes this demanding

Inspection shows replay ordering, deduplication and checkpoint persistence interact. A crash between applying an event and advancing the cursor could lose work or apply it twice. Astra first maps those state transitions and determines the transaction boundary; a feature name alone does not justify a larger model.

## Selection and execution

Astra selects **Astra/xhigh** for the implementation because the failure paths require deep reasoning across coupled state. It passes the inspected constraints and file ownership to the implementation task. A separate **Astra/high reviewer** receives the original requirements, final diff and verification evidence.

This uses Astra throughout while keeping implementation and review independent. It does not require the user to request an all-Astra preset. The selection still depends on the active host supporting those settings.

## Verification and stopping conditions

Exercise reconnect replay, duplicate delivery and failure at the checkpoint boundary. Check that event effects and cursor advancement have the intended transactional behavior. A diagram or happy-path unit test alone cannot establish crash safety.

If the existing persistence layer cannot provide the required guarantee, report that gap and revise the design before claiming completion. Do not fabricate exactly-once behavior for external side effects outside the transaction. The reviewer must reject a patch whose evidence does not support the guarantee.

This is an illustrative use case shown in the [launch film](../assets/laneorchestrator-product-demo.mp4), not a claim that this repository implements an event-stream service. See [live validation](../live-validation.md) for what has actually been executed. The old credential-rotation route payload remains in [legacy examples](legacy/high-risk-change.md).
