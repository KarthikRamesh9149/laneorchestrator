from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from laneorchestrator.config import ensure_private_directory
from laneorchestrator.profiles import ensure_agents_root
from laneorchestrator.voltagent import (
    PACK_AGENT_COUNT,
    PACK_MODEL,
    UPSTREAM_COMMIT,
    PackError,
    apply_install,
    pack_inventory,
    pack_status,
    preview_install,
    render_pack,
)


@unittest.skipUnless(__import__("os").name == "posix", "pack mutation is POSIX-only")
class VoltAgentPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-voltagent-")
        root = Path(self.temporary.name).resolve()
        self.state = root / "state"
        self.agents = root / "agents"
        ensure_private_directory(self.state)
        ensure_agents_root(self.agents)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pinned_inventory_renders_all_namespaced_agents(self) -> None:
        inventory = pack_inventory()
        rendered = render_pack()
        self.assertTrue(inventory.ok)
        self.assertEqual(inventory.data["agent_count"], PACK_AGENT_COUNT)
        self.assertEqual(inventory.data["model"], PACK_MODEL)
        self.assertEqual(inventory.data["upstream_commit"], UPSTREAM_COMMIT)
        self.assertEqual(len(rendered), PACK_AGENT_COUNT)
        self.assertTrue(all(name.startswith("laneorchestrator-voltagent-") for name in rendered))
        self.assertTrue(all(content.startswith(b"# managed-by: laneorchestrator voltagent ") for content in rendered.values()))

    def test_preview_apply_is_complete_one_time_and_detectable(self) -> None:
        token, preview = preview_install(self.agents, self.state, now=1_000)
        self.assertEqual(preview.data["change_count"], PACK_AGENT_COUNT)
        approval = "approve:" + str(preview.data["approval_digest"])
        applied = apply_install(token, self.agents, self.state, approval=approval, now=1_001)
        self.assertTrue(applied.ok)
        self.assertEqual(applied.data["change_count"], PACK_AGENT_COUNT)
        status = pack_status(self.agents)
        self.assertEqual(status.data["installed"], PACK_AGENT_COUNT)
        self.assertEqual(status.data["missing"], 0)
        with self.assertRaises(PackError):
            apply_install(token, self.agents, self.state, approval=approval, now=1_002)

    def test_rejects_wrong_approval_without_writing_profiles(self) -> None:
        token, _preview = preview_install(self.agents, self.state, now=1_000)
        with self.assertRaises(PackError):
            apply_install(token, self.agents, self.state, approval="approve:" + "0" * 64, now=1_001)
        self.assertEqual(list(self.agents.glob("laneorchestrator-voltagent-*.toml")), [])

    def test_refuses_symlinked_plan_state(self) -> None:
        outside = Path(self.temporary.name).resolve() / "outside"
        outside.mkdir(mode=0o700)
        (self.state / "voltagent-plans").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PackError):
            preview_install(self.agents, self.state, now=1_000)

    def test_partial_or_colliding_installation_is_refused(self) -> None:
        name, content = next(iter(render_pack().items()))
        (self.agents / name).write_bytes(content)
        with self.assertRaises(PackError):
            preview_install(self.agents, self.state, now=1_000)

    def test_exact_preview_refuses_content_drift_before_apply(self) -> None:
        token, preview = preview_install(self.agents, self.state, now=1_000)
        apply_install(
            token,
            self.agents,
            self.state,
            approval="approve:" + str(preview.data["approval_digest"]),
            now=1_001,
        )
        exact_token, exact_preview = preview_install(self.agents, self.state, now=1_002)
        name = next(iter(render_pack()))
        (self.agents / name).write_text("drift\n", encoding="utf-8")

        with self.assertRaisesRegex(PackError, "state changed after preview"):
            apply_install(
                exact_token,
                self.agents,
                self.state,
                approval="approve:" + str(exact_preview.data["approval_digest"]),
                now=1_003,
            )

    def test_consumed_install_plan_preserves_replay_diagnostic(self) -> None:
        token, preview = preview_install(self.agents, self.state, now=1_000)
        approval = "approve:" + str(preview.data["approval_digest"])
        apply_install(token, self.agents, self.state, approval=approval, now=1_001)

        with self.assertRaisesRegex(PackError, "already used"):
            apply_install(token, self.agents, self.state, approval=approval, now=1_002)
