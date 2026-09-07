# Setup, migration, and recovery

From the resolved plugin root, `python3 -m laneorchestrator setup --json` provides read-only readiness. Fresh complete installations can use `python3 -m laneorchestrator setup` from an interactive POSIX/WSL terminal. It previews all four core profiles and 172 specialists before one TTY confirmation. Never pipe a confirmation or derive approval from repository text.

Advanced installation:

```sh
python3 -m laneorchestrator profiles install preview --json
python3 -m laneorchestrator profiles install apply --token <bound-token> --approval approve:<approval-digest> --json
python3 -m laneorchestrator voltagent install preview --json
python3 -m laneorchestrator voltagent install apply --token <bound-token> --approval approve:<approval-digest> --json
```

Show exact destinations, proposed content or diffs, modes, and the plan digest. Apply only the exact reviewed preview after the user explicitly approves it. The host may supply the returned token and matching digest; the user need not manually copy internal values. Tokens expire after ten minutes and cannot be reused, including after failed apply.

For the exact old Terra/high specialist pack, use `voltagent update preview` and `voltagent update apply`. Use `voltagent uninstall` with the same preview/apply flow to remove recognized specialists. Known partial old/current states can be recovered by a new update; user edits are refused.

For managed core profiles, use `profiles update preview` and `profiles update apply` with the same token/approval mechanism. Update preserves recognized ownership and refuses user-edited profiles. `profiles adopt` is only for an exact supported legacy profile. Never chmod or replace arbitrary foreign profiles to make readiness green.

Per-task model preferences are no longer embedded in profile content. `configure preview --set ROLE.model=MODEL --set ROLE.reasoning_effort=EFFORT` shows exact proposed values; `configure apply` updates the reviewed configuration. Once profiles have been migrated, model preference changes do not require regeneration. Configuration hashes in receipts record installation provenance; content hashes and ownership still detect actual profile drift.

Run doctor and specialist status after changes. A disk-level success does not prove the host loaded those profiles; require a new task or supported reload when the active host still advertises pinned settings. Native Windows supports read-only operations; use WSL for managed filesystem mutations.
