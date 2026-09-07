from __future__ import annotations

import unittest

from laneorchestrator.adaptive import ASTRA, policy, spawn_settings, validate_selection


HOST = {
    ASTRA: ["low", "medium", "high", "xhigh", "max", "ultra"],
    "gpt-5.6-sol": ["low", "medium", "high", "xhigh", "max", "ultra"],
    "gpt-5.6-terra": ["low", "medium", "high", "xhigh", "max", "ultra"],
    "gpt-5.6-luna": ["low", "medium", "high", "xhigh", "max"],
    "host-enabled-model": ["low", "high"],
}


def choice(model, effort):
    return {"model": model, "reasoning_effort": effort, "reason": "Astra inspected the task's complexity and verification needs."}


class AdaptiveSelectionTests(unittest.TestCase):
    def test_routine_sol_and_terra_allow_every_host_supported_thinking_level(self):
        for model in ("gpt-5.6-sol", "gpt-5.6-terra"):
            for effort in HOST[model]:
                with self.subTest(model=model, effort=effort):
                    selected = validate_selection(choice(model, effort), HOST, task_kind="routine")
                    self.assertEqual(spawn_settings(selected), {"model": model, "reasoning_effort": effort, "fork_turns": "none"})

    def test_small_policy_is_luna_or_terra_high(self):
        for model in ("gpt-5.6-luna", "gpt-5.6-terra"):
            self.assertEqual(validate_selection(choice(model, "high"), HOST, task_kind="small")["model"], model)
            with self.assertRaisesRegex(ValueError, "small changes"):
                validate_selection(choice(model, "medium"), HOST, task_kind="small")

    def test_explicit_user_override_supports_any_host_model(self):
        for model, efforts in HOST.items():
            for effort in efforts:
                selected = validate_selection(choice(model, effort), HOST, task_kind="small", user_override=True)
                self.assertEqual(selected["reasoning_effort"], effort)

    def test_unsupported_combo_never_silently_falls_back(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_selection(choice("gpt-5.6-luna", "ultra"), HOST, task_kind="demanding")
        with self.assertRaisesRegex(ValueError, "host catalog"):
            validate_selection(choice("unavailable-model", "high"), HOST, task_kind="demanding")

    def test_all_astra_retains_per_task_thinking(self):
        for effort in HOST[ASTRA]:
            self.assertEqual(validate_selection(choice(ASTRA, effort), HOST, task_kind="routine", preset="all-astra")["reasoning_effort"], effort)

    def test_malformed_host_catalog_and_explanations_fail(self):
        for catalog in ({}, {ASTRA: "high"}, {ASTRA: ["high", "high"]}, {ASTRA: ["invented"]}):
            with self.assertRaises(ValueError):
                validate_selection(choice(ASTRA, "high"), catalog, task_kind="demanding")
        for reason in ("", "\n", "x" * 1001):
            with self.assertRaises(ValueError):
                validate_selection({**choice(ASTRA, "high"), "reason": reason}, HOST, task_kind="demanding")

    def test_policy_does_not_claim_a_runtime_observation(self):
        self.assertFalse(policy()["runtime_observed"])
        self.assertEqual(policy()["routine"]["reasoning_effort"], "chosen_by_astra")


if __name__ == "__main__":
    unittest.main()
