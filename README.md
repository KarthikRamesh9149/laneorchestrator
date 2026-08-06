# LaneOrchestrator

LaneOrchestrator is a Codex plugin that turns one task prompt into a visible, safe execution route: project context → relevant skills and agents → GPT-5.6 lane → implementation → verification.

## Everyday use

```text
$laneorchestrator implement OAuth token rotation for this service
```

The router emits the lane, selected capabilities, evidence, verification plan, and any safety pause. Routine workspace work proceeds automatically.

| Lane | Model | Use |
| --- | --- | --- |
| Luna | `gpt-5.6-luna` / High | One known, low-risk local change |
| Terra | `gpt-5.6-terra` / High | Default implementation lane |
| Sol | `gpt-5.6-sol` / High | High-risk planning and independent review |

For project-owned long-term context, run `$laneorchestrator init`. This is the only normal operation that writes `.laneorchestrator/BRIEF.md`.

## One-time custom-agent setup

Install the namespaced templates explicitly; the installer validates them and refuses to overwrite an existing profile.

```bash
sh scripts/install-agents.sh
sh scripts/install-agents.sh --check
```

The plugin itself does not modify shell startup files, global Git settings, Codex configuration, hooks, MCP configuration, or existing agents.

## Development

```bash
python3 skills/laneorchestrator/scripts/catalog.py --query "fix a React accessibility bug" --cwd .
python3 ../.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/laneorchestrator
```

Use the validation commands in `tests/` before release.

```bash
python3 scripts/healthcheck.py
python3 tests/test_catalog.py
python3 tests/test_routes.py
sh tests/test_installer.sh
python3 -m unittest discover -s tests -v
```

## Provenance

This is a clean-room implementation. It takes high-level inspiration from [my-codex](https://github.com/sehoon787/my-codex), [SkillMesh](https://github.com/varunreddy/SkillMesh), [Sol Advisor](https://github.com/DannyMac180/sol-advisor), and [awesome-codex-subagents](https://github.com/VoltAgent/awesome-codex-subagents). No upstream implementation code or prompts are included.

## License

MIT. See [LICENSE](LICENSE).
