# Release channels, upgrades and removal

## Choose a source

| Source | What it contains | Update behavior |
| --- | --- | --- |
| `main` | The latest Astra source | Moving source channel; inspect the commit and CI before updating |
| `v0.3.0` | Astra-led adaptive orchestration and per-task model/thinking selection | Pinned release channel; check its assets, attestation and release evidence |
| `v0.2.4` | The previously published fixed-lane version | Immutable release; does not contain Astra support |

Use the Git commit as well as the version when reporting a source issue. Merging
source changes does not publish a release or create a tag. Check the repository's
release page for available tagged releases and their evidence.

After the verified `v0.3.0` release is public, install its pinned snapshot with:

```sh
codex plugin marketplace add KarthikRamesh9149/laneorchestrator --ref v0.3.0
codex plugin add laneorchestrator@laneorchestrator
```

Until then, follow the [source quickstart](getting-started.md) for current Astra behavior. You can also register a Git marketplace with `--ref main`; the source-checkout route is documented first because it gives you an explicit directory for setup and recovery. The existing `v0.2.4` command remains in its historical release notes.

## Upgrade an existing installation to v0.3.0

1. Finish active work using the old profiles. Record the source/tag you currently use and keep any local edits.
2. Obtain the current `main` checkout using the clone command in Getting Started. Review its commit, changelog and CI.
3. Remove the old plugin registration, then its marketplace registration:

```sh
codex plugin remove laneorchestrator@laneorchestrator
codex plugin marketplace remove laneorchestrator
```

4. From the new `laneorchestrator` checkout, register and install it:

```sh
codex plugin marketplace add .
codex plugin add laneorchestrator@laneorchestrator
```

5. If you have no managed profiles, run the interactive `setup` command. If you already have old profiles, migrate **both** sets through the reviewed lifecycle below. Exact v0.1.0 defaults and the repository's initial pre-v0.1.0 control profiles can use `profiles adopt preview`; unknown or user-edited files remain refused. Do not repair modes or overwrite files by hand.

Every module command below runs from the checkout. Prefix the command fragments with `python3 -m laneorchestrator`.

| Step | Command fragment | What to inspect |
| --- | --- | --- |
| Preview exact legacy adoption, when reported | `profiles adopt preview --json` | Four recognized legacy files, proposed v0.3.0 contents, private modes and receipt |
| Apply exact legacy adoption | `profiles adopt apply --token <bound-token> --approval approve:<approval-digest> --json` | Use only the token and digest from the reviewed adoption preview |
| Preview core migration | `profiles update preview --json` | Four destinations, proposed contents, exact changes |
| Apply that preview | `profiles update apply --token <bound-token> --approval approve:<approval-digest> --json` | Use only the token and digest from the preview you just approved |
| Preview specialist migration | `voltagent update preview --json` | All recognized old/current/missing specialist states |
| Apply that preview | `voltagent update apply --token <bound-token> --approval approve:<approval-digest> --json` | Refuses unknown or user-edited files |
| Check files | `doctor --json`, `status --json`, `voltagent status --json` | No unresolved relevant drift or missing profiles |

The placeholders are not usable approvals. Never copy tokens from another operation. Core updates keep managed backups. The specialist updater restores exact previous bytes after handled failures; it is not a general history store or a crash-atomic transaction across 172 files. Keep a separate backup of any custom content you maintain.

6. Open a new Codex task. If the host still advertises fixed `model` or `model_reasoning_effort` settings on the managed profiles, reload the client and recheck. Disk updates alone do not establish that the running host reloaded them.
7. Try a bounded task. Confirm that the chosen settings are passed at launch and that the final handoff reports real verification. Runtime-observed settings may remain unknown if the host does not expose them.

## Future updates

A marketplace refresh does **not** silently move a pinned installation to another release tag. To switch tags or a local source, remove and register the intended source explicitly. For a local checkout, fetch and review upstream changes before refreshing the plugin. Avoid updating files underneath a running agent.

Read the changelog for profile migration requirements; a new plugin version does not necessarily require rewriting profiles. Changing only model/thinking preferences in the current dynamic profiles does not require regeneration.

## Remove LaneOrchestrator

While the plugin or source checkout is still available, inspect `voltagent uninstall preview` and `profiles uninstall preview`. If desired, apply each separately with its matching reviewed token and approval. Only recognized managed files are removed; unrelated files remain untouched.

Then remove the plugin and marketplace using the two removal commands above. This does not remove LaneOrchestrator-managed profiles or configuration by itself. Configuration can remain for a future installation. Do not broadly delete your Codex directory.

## Recover from a failed migration

Stop using expired previews. Inspect the error and current `status` output. For a known partial specialist state, create a fresh `voltagent update preview`; for a recognized unreceipted historical control set, use `profiles adopt preview`; for a user-edited profile, compare and preserve your edits before deliberately reconciling it. See [troubleshooting](troubleshooting.md). Never remove a conflict merely because its filename starts with LaneOrchestrator.
