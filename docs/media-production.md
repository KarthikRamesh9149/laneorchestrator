# LaneOrchestrator launch media

The launch deliverable is one 78-second film at 1920×1080 and 30 fps. It uses five scenes: a LaneOrchestrator opening, three sustained workflows, and a LaneOrchestrator closing. The interfaces are deliberately labeled **DEMO RE-CREATION**. They illustrate how the skill is used; they are not recordings of a desktop session or proof of a successful model run. See [live validation](live-validation.md) for separate execution evidence.

The [production renderer](../scripts/render_astra_launch.py) uses the existing dark purple/cyan identity, readable Arial typography, progressive task and code displays, restrained transitions, and an original synthesized score. Its MP4 uses H.264 video, stereo AAC audio and fast-start metadata. Separate SRT captions and an uncompressed audio master are generated alongside it.

Rendering requires optional Pillow, NumPy, an ffmpeg executable, and Arial/SF or DejaVu Sans fonts. Supply the executable through `--ffmpeg` and a destination through `--output`. The default export is the complete film. `--preview` exports one still per scene. These are optional production dependencies; the plugin runtime remains standard-library-only.

The [GIF renderer](../scripts/render_demo_gif.py) produces a compact 20-second preview from the same desktop and CLI scenes. Both README placements link to the same full film. The release verifier checks the declared media formats and dimensions, with a 1 MB preview target and a 10 MiB full-film limit.

The procedural artwork and synthesized score are original project assets distributed under the repository's MIT license. No stock music, third-party footage or voiceover is used. Fonts are rendered locally and are not redistributed.

## The three routing examples

All prompts describe work without naming a model. These are authored product demonstrations grounded in the [adaptive routing policy](../skills/laneorchestrator/references/routing-policy.md), not recordings or measurements of these three tasks.

| Workflow | Inspected context | Automatic selection illustrated |
| --- | --- | --- |
| Event-stream recovery | Replay ordering, duplicate delivery and transactional checkpoints interact across failure paths. | Astra/xhigh implements; a separate Astra/high agent reviews the diff and acceptance criteria. |
| Notification preferences | Existing settings components and API, with integration across form state, persistence and defaults. | Astra coordinates, Sol/high implements, Astra/high independently reviews. |
| Project pagination, in Codex CLI | Existing cursor helper and response schema; separate backend and typed-client file ownership. | Astra coordinates Terra/medium for the established backend pattern and Terra/high for the bounded typed-client change, then reviews contract consistency. |

These choices illustrate task-dependent reasoning, not a fixed mapping of feature names to models or a comparative model benchmark. The live host must support each selected model/thinking pair. Consequential implementation retains separate review even when every participating agent uses Astra.
