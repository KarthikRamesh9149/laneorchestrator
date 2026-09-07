# Support

| Need | Channel |
| --- | --- |
| Installation or model-selection help | [Troubleshooting](docs/troubleshooting.md), then [Discussions](https://github.com/KarthikRamesh9149/laneorchestrator/discussions) |
| Reproducible bug | [Bug report](https://github.com/KarthikRamesh9149/laneorchestrator/issues/new?template=bug.yml) |
| Focused feature proposal | [Feature request](https://github.com/KarthikRamesh9149/laneorchestrator/issues/new?template=feature.yml) |
| Security vulnerability | Private reporting through [SECURITY.md](SECURITY.md) |

## Useful diagnostic information

Include the source channel (release tag or `main`), Git commit, Codex client/version, operating system, Python version, a minimal task and the expected versus observed behavior. For dispatch issues, distinguish the selected model/thinking from any runtime settings the host actually exposed.

From the source checkout or resolved plugin root, collect `doctor --json`, `status --json` and, for specialist issues, `voltagent status --json` using the `python3 -m laneorchestrator` entry point. Read the output before posting: remove secrets, access tokens, private paths, private repository content and approval tokens. You do not need to publish an entire session or private source tree.

For a reproducible source-development issue, this quick check can help:

```sh
python3 scripts/healthcheck.py
```

The maintainer validation gate is `sh scripts/validate.sh`; ordinary users do not need to run the entire suite just to ask for setup help. This is a community-maintained project with no response-time commitment.

Public issues must not include exploit details. Use private vulnerability reporting instead.
