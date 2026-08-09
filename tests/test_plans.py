from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import stat
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from laneorchestrator.plans import (
    MAX_PLAN_BYTES,
    MutationPlan,
    Operation,
    PlanError,
    create_plan,
    load_plan,
    consume_plan,
)


class MutationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve() / "plans"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.operations = (
            Operation(
                path="agents/example.toml",
                before_sha256=None,
                after_sha256=(
                    "1c3ef9a7c817b4642bcb3cb1456fbce92a6f992df2e1d6ad9d8a2dfb4fdf42f6"
                ),
                content_b64="bmV3IGNvbnRlbnQK",
            ),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def plan_path(self, token: str) -> Path:
        name = hashlib.sha256(token.encode("ascii")).hexdigest() + ".json"
        return self.root / name

    def test_create_returns_urlsafe_256_bit_token_and_private_file(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)

        self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")
        plan_path = self.plan_path(token)
        self.assertTrue(plan_path.is_file())
        self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.root / "consumed").stat().st_mode), 0o700)

    def test_raw_token_is_never_persisted(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)

        persisted = b"".join(
            path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        )
        self.assertNotIn(token.encode("ascii"), persisted)
        self.assertNotIn(token, self.plan_path(token).name)

    def test_create_never_reissues_a_live_or_consumed_token(self) -> None:
        fixed_token = "A" * 43
        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe", return_value=fixed_token
        ):
            token = create_plan("profiles.install", self.operations, self.root, now=100)
            with self.assertRaisesRegex(PlanError, "unique"):
                create_plan("profiles.install", self.operations, self.root, now=101)
            consume_plan(token, "profiles.install", self.root, lambda plan: None, now=102)
            with self.assertRaisesRegex(PlanError, "unique"):
                create_plan("profiles.install", self.operations, self.root, now=103)

    def test_create_retries_collision_with_a_fresh_token(self) -> None:
        first_token = "A" * 43
        second_token = "D" * 43
        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe", return_value=first_token
        ):
            self.assertEqual(
                create_plan("profiles.install", self.operations, self.root, now=100),
                first_token,
            )
        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe",
            side_effect=[first_token, second_token],
        ):
            self.assertEqual(
                create_plan("profiles.remove", self.operations, self.root, now=101),
                second_token,
            )

        self.assertEqual(
            load_plan(first_token, "profiles.install", self.root, now=102).kind,
            "profiles.install",
        )
        self.assertEqual(
            load_plan(second_token, "profiles.remove", self.root, now=102).kind,
            "profiles.remove",
        )

    def test_create_retries_a_leading_dash_token_that_argparse_cannot_consume(self) -> None:
        option_shaped_token = "-" + ("A" * 42)
        command_safe_token = "B" * 43
        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe",
            side_effect=[option_shaped_token, command_safe_token],
        ):
            token = create_plan(
                "profiles.install", self.operations, self.root, now=100
            )

        self.assertEqual(token, command_safe_token)
        self.assertFalse(token.startswith("-"))
        self.assertEqual(
            load_plan(token, "profiles.install", self.root, now=101).kind,
            "profiles.install",
        )

    def test_concurrent_fixed_token_creators_never_replace_each_other(self) -> None:
        fixed_token = "C" * 43
        start_barrier = threading.Barrier(2)
        other_operations = (
            Operation(
                path="agents/other.toml",
                before_sha256=None,
                after_sha256="b" * 64,
                content_b64=None,
            ),
        )

        def attempt(kind: str, operations: tuple) -> tuple:
            start_barrier.wait(timeout=5)
            try:
                token = create_plan(kind, operations, self.root, now=100)
            except PlanError as error:
                return ("error", kind, error)
            return ("created", kind, token)

        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe", return_value=fixed_token
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(attempt, "profiles.install", self.operations),
                    executor.submit(attempt, "profiles.remove", other_operations),
                )
                outcomes = [future.result(timeout=10) for future in futures]

        created = [outcome for outcome in outcomes if outcome[0] == "created"]
        rejected = [outcome for outcome in outcomes if outcome[0] == "error"]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][2], fixed_token)
        self.assertEqual(len(rejected), 1)
        self.assertRegex(str(rejected[0][2]), "unique")
        loaded = load_plan(fixed_token, created[0][1], self.root, now=101)
        self.assertEqual(loaded.kind, created[0][1])

    def test_load_round_trips_an_immutable_plan_and_operations(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        plan = load_plan(token, "profiles.install", self.root, now=700)

        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(plan.kind, "profiles.install")
        self.assertEqual(plan.created_at, 100)
        self.assertEqual(plan.expires_at, 700)
        self.assertIsInstance(plan.operations, tuple)
        self.assertEqual(plan.operations, self.operations)
        with self.assertRaises(FrozenInstanceError):
            plan.kind = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            plan.operations[0].path = "changed"  # type: ignore[misc]

    def test_serialization_is_deterministic_for_identical_inputs(self) -> None:
        with mock.patch(
            "laneorchestrator.plans.secrets.token_urlsafe",
            side_effect=["A" * 43, "B" * 43],
        ):
            first = create_plan("profiles.install", self.operations, self.root, now=100)
            second = create_plan("profiles.install", self.operations, self.root, now=100)

        self.assertEqual(self.plan_path(first).read_bytes(), self.plan_path(second).read_bytes())

    def test_load_rejects_invalid_token_syntax_and_wrong_kind(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)

        for invalid in ("short", "a" * 42, "a" * 44, "../" + ("a" * 40)):
            with self.subTest(token=invalid):
                with self.assertRaisesRegex(PlanError, "token"):
                    load_plan(invalid, "profiles.install", self.root, now=101)
        with self.assertRaisesRegex(PlanError, "kind"):
            load_plan(token, "profiles.remove", self.root, now=101)

    def test_expiry_occurs_at_601_seconds(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)

        load_plan(token, "profiles.install", self.root, now=700)
        with self.assertRaisesRegex(PlanError, "expired"):
            load_plan(token, "profiles.install", self.root, now=701)

    def test_load_rejects_corrupt_oversized_and_noncanonical_schema(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        path = self.plan_path(token)
        path.write_bytes(b"not json\n")
        path.chmod(0o600)
        with self.assertRaisesRegex(PlanError, "corrupt"):
            load_plan(token, "profiles.install", self.root, now=101)

        path.write_bytes(b"{" + (b" " * MAX_PLAN_BYTES) + b"}")
        path.chmod(0o600)
        with self.assertRaisesRegex(PlanError, "size"):
            load_plan(token, "profiles.install", self.root, now=101)

        path.write_text(
            '{"created_at":100,"expires_at":700,"kind":"profiles.install",'
            '"operations":[],"schema_version":2,"state_fingerprint":"'
            + ("0" * 64)
            + '"}\n',
            encoding="utf-8",
        )
        path.chmod(0o600)
        with self.assertRaisesRegex(PlanError, "schema"):
            load_plan(token, "profiles.install", self.root, now=101)

    def test_load_rejects_wrong_mode_symlink_and_directory(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        path = self.plan_path(token)
        path.chmod(0o644)
        with self.assertRaisesRegex(PlanError, "mode"):
            load_plan(token, "profiles.install", self.root, now=101)

        path.unlink()
        outside = self.root.parent / "outside"
        outside.write_bytes(b"outside")
        path.symlink_to(outside)
        with self.assertRaises(PlanError):
            load_plan(token, "profiles.install", self.root, now=101)

        path.unlink()
        path.mkdir()
        with self.assertRaises(PlanError):
            load_plan(token, "profiles.install", self.root, now=101)

    def test_changed_fingerprint_is_rejected(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        path = self.plan_path(token)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["state_fingerprint"] = "0" * 64
        path.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)

        with self.assertRaisesRegex(PlanError, "fingerprint"):
            load_plan(token, "profiles.install", self.root, now=101)

    def test_consume_returns_callback_value_and_prevents_replay(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        expected = object()

        actual = consume_plan(
            token, "profiles.install", self.root, lambda plan: expected, now=101
        )

        self.assertIs(actual, expected)
        self.assertFalse(self.plan_path(token).exists())
        with self.assertRaisesRegex(PlanError, "already used"):
            load_plan(token, "profiles.install", self.root, now=102)
        with self.assertRaisesRegex(PlanError, "already used"):
            consume_plan(token, "profiles.install", self.root, lambda plan: None, now=102)

    def test_failed_apply_still_consumes_token(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        with self.assertRaisesRegex(RuntimeError, "boom"):
            consume_plan(
                token,
                "profiles.install",
                self.root,
                lambda plan: (_ for _ in ()).throw(RuntimeError("boom")),
                now=101,
            )
        with self.assertRaisesRegex(PlanError, "already used"):
            load_plan(token, "profiles.install", self.root, now=102)

    def test_unlink_failure_leaves_durable_replay_tombstone(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        callback = mock.Mock()

        with mock.patch(
            "laneorchestrator.plans._unlink_regular_nofollow_locked",
            side_effect=OSError("injected unlink failure"),
        ):
            with self.assertRaisesRegex(OSError, "injected"):
                consume_plan(
                    token, "profiles.install", self.root, callback, now=101
                )

        callback.assert_not_called()
        with self.assertRaisesRegex(PlanError, "already used"):
            load_plan(token, "profiles.install", self.root, now=102)

    def test_concurrent_cooperating_consumers_apply_exactly_once(self) -> None:
        token = create_plan("profiles.install", self.operations, self.root, now=100)
        applied = []

        def attempt() -> object:
            return consume_plan(
                token,
                "profiles.install",
                self.root,
                lambda plan: applied.append(plan),
                now=101,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt) for _ in range(2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=5))
                except PlanError as error:
                    outcomes.append(error)

        self.assertEqual(len(applied), 1)
        self.assertEqual(sum(isinstance(value, PlanError) for value in outcomes), 1)

    def test_constructor_copies_mutable_operation_sequence(self) -> None:
        operations = list(self.operations)
        plan = MutationPlan(1, "profiles.install", 100, 700, "a" * 64, operations)
        operations.clear()

        self.assertEqual(plan.operations, self.operations)


if __name__ == "__main__":
    unittest.main()
