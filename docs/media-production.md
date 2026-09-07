# Astra launch media

The launch deliverable is one 65-second film at 1920×1080 and 30 fps. It combines a cinematic opening, recreated Codex desktop and CLI workflows, and a closing LaneOrchestrator reveal. The interfaces are deliberately labeled **DEMO RE-CREATION**. They illustrate how the skill is used; they are not recordings of a desktop session or proof of a successful model run. See [live validation](live-validation.md) for separate execution evidence.

The [production renderer](../scripts/render_astra_launch.py) uses the existing dark purple/cyan identity, native-style typography, progressive task and code displays, camera pushes, and an original synthesized score. Its MP4 uses H.264 video, stereo AAC audio and fast-start metadata. Separate SRT captions and an uncompressed audio master are generated alongside it.

Rendering requires optional Pillow, NumPy, an ffmpeg executable, and Arial/SF or DejaVu Sans fonts. Supply the executable through `--ffmpeg` and a destination through `--output`. The default export is the complete film. `--preview` exports one still per scene. These are optional production dependencies; the plugin runtime remains standard-library-only.

The [GIF renderer](../scripts/render_demo_gif.py) produces a compact 20-second preview from the same desktop and CLI scenes. Both README placements link to the same full film. The release verifier checks the declared media formats and dimensions, with a 1 MB preview target and a 10 MiB full-film limit.

The procedural artwork and synthesized score are original project assets distributed under the repository's MIT license. No stock music, third-party footage or voiceover is used. Fonts are rendered locally and are not redistributed.
