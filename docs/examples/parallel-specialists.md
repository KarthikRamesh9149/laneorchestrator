# CLI workflow: project pagination

## Request

> `$laneorchestrator Add project pagination and update the typed client. Reuse our existing cursor format and page schema.`

## Inspection and division of work

Astra finds a shared cursor helper and a known page-response contract. It defines that contract before splitting the work, assigns disjoint file ownership and provides each specialist with the relevant existing code.

| Responsibility | Example choice | Reason |
| --- | --- | --- |
| Coordinate and integrate | Astra/high | Set the contract and reconcile the two outputs |
| Backend endpoint | Terra/medium | Reuse an established cursor helper in a known implementation pattern |
| Typed client | Terra/high | Small, bounded SDK change with an explicit response shape |
| Review | Separate Astra/high task | Check the public contract and acceptance evidence independently |

The specialists can work concurrently only while their ownership does not overlap. Shared-file changes need sequencing. Parallel agents are not automatically useful for every task.

## Expected result

The endpoint and client agree on cursor validation, page items and `next_cursor`. Verification covers an empty page, invalid cursor and last-page termination. Astra integrates the results and supplies the diff and evidence to the review task before handoff.

The CLI segment in the [launch film](../assets/laneorchestrator-product-demo.mp4) is a recreation of this workflow. These model choices are justified illustrations, not a measured ranking of model ability. Existing host support and inspected scope determine actual dispatch.
