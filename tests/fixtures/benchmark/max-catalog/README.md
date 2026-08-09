# Generated maximum catalog fixture

This directory intentionally contains no generated tree. `evaluate_max_catalog`
creates the fixture in a `TemporaryDirectory` from fixed seed `20260809`, then
measures only bounded discovery with `time.monotonic` and removes it.

The generated catalog saturates the default skill and agent file/total-byte
limits: 2,048 `SKILL.md` files of 16 KiB (32 MiB) and 1,024 agent TOML files of
8 KiB (8 MiB). Directory and entry limits are separate ceilings and cannot be
simultaneously saturated with this file layout; the benchmark reports all
counters and limits instead of claiming otherwise.
