from __future__ import annotations

import unittest
from pathlib import Path

from laneorchestrator.models import (
    Availability,
    EffectiveConfig,
    RoleConfig,
    RoleEvidence,
    codex_home,
    is_valid_model_id,
    is_valid_reasoning_effort,
)


class ModelTests(unittest.TestCase):
    def test_types_are_immutable(self) -> None:
        role = RoleConfig("gpt-5.6-sol", "high")
        config = EffectiveConfig(1, {"router": role}, "defaults")
        evidence = RoleEvidence("router", role.model, None, Availability.UNKNOWN)

        with self.assertRaises((AttributeError, TypeError)):
            role.model = "gpt-5.6-terra"  # type: ignore[misc]
        with self.assertRaises((AttributeError, TypeError)):
            config.source = "file"  # type: ignore[misc]
        with self.assertRaises((AttributeError, TypeError)):
            evidence.role = "main_implementer"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            config.roles["router"] = role  # type: ignore[index]

    def test_availability_has_only_the_public_values(self) -> None:
        self.assertEqual(
            [item.value for item in Availability],
            ["AVAILABLE", "MISSING", "UNKNOWN"],
        )

    def test_codex_home_honors_only_absolute_environment_override(self) -> None:
        home = (Path.cwd() / "model-home").resolve()
        absolute_override = (home / "codex").resolve()
        self.assertEqual(codex_home({}, home), home / ".codex")
        self.assertEqual(codex_home({"CODEX_HOME": str(absolute_override)}, home), absolute_override)
        self.assertEqual(codex_home({"CODEX_HOME": "relative/codex"}, home), home / ".codex")
        self.assertEqual(codex_home({"CODEX_HOME": "~/custom"}, home), home / ".codex")

    def test_model_and_effort_validation_are_strict(self) -> None:
        self.assertTrue(is_valid_model_id("gpt-5.6-terra"))
        self.assertTrue(is_valid_model_id("a"))
        self.assertFalse(is_valid_model_id("GPT-5.6-terra"))
        self.assertFalse(is_valid_model_id("-gpt-5.6-terra"))
        self.assertFalse(is_valid_model_id("a" * 129))
        self.assertTrue(is_valid_reasoning_effort("ultra"))
        self.assertFalse(is_valid_reasoning_effort("highest"))


if __name__ == "__main__":
    unittest.main()
