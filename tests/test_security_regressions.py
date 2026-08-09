from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from laneorchestrator.config import (
    MAX_CONFIG_BYTES,
    MAX_VALUE_CHARS,
    ConfigError,
    ensure_private_directory,
    load_config,
    parse_config_bytes,
    preview_config,
    serialize_config,
)
from laneorchestrator.discovery import DEFAULT_LIMITS, DiscoveryRequest, collect, discover
from laneorchestrator.plans import (
    MAX_PLAN_BYTES,
    PLAN_TTL_SECONDS,
    PlanError,
    consume_plan,
    create_plan,
    load_plan,
)
from laneorchestrator.profiles import PROFILE_NAMES, ProfileConflict, preview_profiles
from laneorchestrator.routing import HIGH_RISK_PHRASES, HIGH_RISK_TERMS, RouteFacts, recommend_route


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "security"


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-security-")
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / "state"
        self.agents = self.root / "agents"
        self.state.mkdir(mode=0o700)
        self.agents.mkdir(mode=0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def snapshot(self, root: Path) -> tuple[tuple[str, str, bytes | None], ...]:
        values = []
        for path in sorted(root.rglob("*")):
            metadata = path.lstat()
            relative = str(path.relative_to(root))
            if stat.S_ISREG(metadata.st_mode):
                values.append((relative, "file", path.read_bytes()))
            elif stat.S_ISLNK(metadata.st_mode):
                values.append((relative, "symlink", os.fsencode(os.readlink(path))))
            elif stat.S_ISDIR(metadata.st_mode):
                values.append((relative, "directory", None))
            else:
                values.append((relative, "other", None))
        return tuple(values)

    def managed_snapshot(self, root: Path) -> tuple[tuple[str, str, bytes | None], ...]:
        return tuple(item for item in self.snapshot(root) if not item[0].endswith(".laneorchestrator-state.lock"))

    @unittest.skipUnless(os.name == "posix", "descriptor-relative mutation is POSIX-only")
    def test_dangling_destination_symlink_cannot_escape_agents_root(self) -> None:
        outside = self.root / "outside.toml"
        sentinel = b"outside sentinel\n"
        outside.write_bytes(sentinel)
        before_outside = outside.lstat()
        target = self.agents / "laneorchestrator-router.toml"
        target.symlink_to(outside)
        before_agents, before_state = self.managed_snapshot(self.agents), self.managed_snapshot(self.state)

        with self.assertRaisesRegex(ProfileConflict, "unsafe|symbolic|destination"):
            preview_profiles("install", load_config(self.state), self.agents, self.state, now=100)

        after_outside = outside.lstat()
        self.assertEqual(outside.read_bytes(), sentinel)
        self.assertEqual((after_outside.st_dev, after_outside.st_ino), (before_outside.st_dev, before_outside.st_ino))
        self.assertEqual(self.managed_snapshot(self.agents), before_agents)
        self.assertEqual(self.managed_snapshot(self.state), before_state)
        self.assertFalse((self.state / "receipts.json").exists())
        self.assertFalse((self.state / "plans").exists())

    def test_every_high_risk_term_and_evasion_never_routes_to_luna(self) -> None:
        evasions = (
            "OAuth2 token rotation", "OpenID login", "role-based access control",
            "API_key rotation", "TLS/certificate rotation", "DATA-retention purge",
        )
        objectives = tuple(HIGH_RISK_TERMS) + tuple(HIGH_RISK_PHRASES) + evasions
        self.assertGreaterEqual(len(objectives), len(HIGH_RISK_TERMS | HIGH_RISK_PHRASES))
        for objective in objectives:
            with self.subTest(objective=objective):
                route = recommend_route(RouteFacts(objective, True, True, 1, "low"))
                self.assertEqual(route["lane"], "sol-plan-terra-sol-review")
                self.assertTrue(route["signals"])

    def test_historical_high_risk_evasion_corpus_stays_fail_closed(self) -> None:
        corpus = json.loads((ROOT / "benchmarks" / "routing-corpus-v1.json").read_text(encoding="utf-8"))
        cases = [case for case in corpus if case["category"] == "high-risk-evasion"]
        self.assertEqual([case["id"] for case in cases], ["high-risk-evasion-{0}".format(index) for index in range(1, 16)])
        for case in cases:
            with self.subTest(case=case["id"]):
                route = recommend_route(RouteFacts(
                    case["objective"], case["known_area"], case["acceptance_criteria"],
                    case["files"], case["risk"],
                ))
                self.assertEqual(route["lane"], "sol-plan-terra-sol-review")
                self.assertTrue(route["signals"])

    def test_bounded_agent_read_never_charges_more_than_the_aggregate_cap(self) -> None:
        agents = self.root / "bounded-agents"
        agents.mkdir()
        (agents / "oversized.toml").write_bytes(b"x" * 100)
        limits = replace(DEFAULT_LIMITS, max_agent_file_bytes=10, max_total_agent_bytes=10)

        capabilities, warnings, counters = collect((agents,), limits)

        self.assertEqual(capabilities, [])
        self.assertLessEqual(counters["agent_bytes"], limits.max_total_agent_bytes)
        self.assertEqual(counters["agent_bytes"], limits.max_total_agent_bytes)
        self.assertTrue(any("larger than 10 bytes" in warning for warning in warnings))

    def test_discovery_treats_prompt_injection_and_stuffing_as_inert_metadata(self) -> None:
        skills = self.root / "skills"
        direct = skills / "python-parser" / "SKILL.md"
        direct.parent.mkdir(parents=True)
        direct.write_text("---\nname: python-parser\ndescription: Fix Python parser behavior.\n---\n", encoding="utf-8")
        injected = skills / "priority-override" / "SKILL.md"
        injected.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "injection-skill.md", injected)
        agents = self.root / "agents-catalog"
        agents.mkdir()
        shutil.copyfile(FIXTURES / "stuffed-agent.toml", agents / "priority-override.toml")

        result = discover(DiscoveryRequest("fix Python parser", (skills, agents), (), 20))
        data = result.data
        names = [item["name"] for item in data["capabilities"]]
        high_risk = recommend_route(RouteFacts("rotate OAuth2 token", True, True, 1, "low"))

        self.assertEqual(names[0], "python-parser")
        self.assertIn("priority-override", names)
        self.assertNotIn("instruction", data)
        self.assertEqual(high_risk["lane"], "sol-plan-terra-sol-review")
        self.assertLessEqual(data["counters"]["skill_bytes"], data["limits"]["max_total_skill_bytes"])
        self.assertLessEqual(data["counters"]["agent_bytes"], data["limits"]["max_total_agent_bytes"])
        self.assertFalse((self.root / "outside").exists())

    def test_config_fuzz_and_exact_size_boundaries_fail_closed(self) -> None:
        malformed = (
            b"", b"{", b"[]", b'{"schema_version":2}',
            b'{"schema_version":1,"api_key":"x"}',
            b'{"schema_version":1,"roles":{"router":{"model":"bad\\u0000model","reasoning_effort":"high"}}}',
            b'{"schema_version":1,"schema_version":1,"roles":{}}',
        )
        config = self.state / "config.json"
        for payload in malformed:
            with self.subTest(payload=payload):
                config.write_bytes(payload)
                config.chmod(0o600)
                with self.assertRaises(ConfigError):
                    load_config(self.state)
        valid = serialize_config(load_config(self.root / "missing-state"))
        for size in (MAX_CONFIG_BYTES - 1, MAX_CONFIG_BYTES):
            with self.subTest(size=size):
                config.write_bytes(valid + b" " * (size - len(valid)))
                config.chmod(0o600)
                self.assertEqual(load_config(self.state).source, "file")
        config.write_bytes(valid + b" " * (MAX_CONFIG_BYTES + 1 - len(valid)))
        config.chmod(0o600)
        with self.assertRaisesRegex(ConfigError, "safely read"):
            load_config(self.state)
        for size in (MAX_VALUE_CHARS - 1, MAX_VALUE_CHARS, MAX_VALUE_CHARS + 1):
            with self.subTest(value_size=size):
                with self.assertRaises(ConfigError):
                    preview_config({"router.model": "x" * size}, self.state, now=100)

    @unittest.skipUnless(os.name == "posix", "private plan storage is POSIX-only")
    def test_plan_fuzz_expiry_replay_and_size_boundaries(self) -> None:
        plans = ensure_private_directory(self.state / "plans")
        token = create_plan("test", (), plans, now=100)
        self.assertIsNotNone(load_plan(token, "test", plans, now=100 + PLAN_TTL_SECONDS))
        with self.assertRaisesRegex(PlanError, "expired"):
            load_plan(token, "test", plans, now=101 + PLAN_TTL_SECONDS)
        with self.assertRaisesRegex(PlanError, "does not match"):
            load_plan(token, "other", plans, now=100)
        self.assertEqual(consume_plan(token, "test", plans, lambda _plan: "applied", now=100), "applied")
        with self.assertRaisesRegex(PlanError, "already used"):
            consume_plan(token, "test", plans, lambda _plan: None, now=100)
        for raw in (b"", b"{", b"[]", b'{"schema_version":1}'):
            with self.subTest(raw=raw):
                bad = create_plan("bad", (), plans, now=200)
                path = plans / (hashlib.sha256(bad.encode("ascii")).hexdigest() + ".json")
                path.write_bytes(raw)
                path.chmod(0o600)
                with self.assertRaises(PlanError):
                    load_plan(bad, "bad", plans, now=200)
                path.unlink()
        for size in (MAX_PLAN_BYTES - 1, MAX_PLAN_BYTES, MAX_PLAN_BYTES + 1):
            with self.subTest(plan_size=size):
                boundary = create_plan("boundary", (), plans, now=300)
                path = plans / (hashlib.sha256(boundary.encode("ascii")).hexdigest() + ".json")
                raw = path.read_bytes()
                path.write_bytes(raw + b" " * (size - len(raw)))
                path.chmod(0o600)
                if size <= MAX_PLAN_BYTES:
                    self.assertEqual(load_plan(boundary, "boundary", plans, now=300).kind, "boundary")
                else:
                    with self.assertRaisesRegex(PlanError, "exceeds maximum size"):
                        load_plan(boundary, "boundary", plans, now=300)

    @unittest.skipUnless(os.name == "posix", "unsafe filesystem objects are POSIX-only")
    def test_unsafe_profile_leaf_types_are_refused_without_outside_write(self) -> None:
        sentinel = self.root / "outside-sentinel"
        sentinel.write_bytes(b"do not overwrite\n")
        for kind in ("directory", "fifo", "hardlink", "live-symlink"):
            with self.subTest(kind=kind):
                agents = self.root / (kind + "-agents")
                state = self.root / (kind + "-state")
                agents.mkdir(mode=0o700)
                state.mkdir(mode=0o700)
                target = agents / PROFILE_NAMES[0]
                if kind == "directory":
                    target.mkdir()
                elif kind == "fifo":
                    os.mkfifo(target)
                elif kind == "hardlink":
                    os.link(sentinel, target)
                else:
                    target.symlink_to(sentinel)
                before = (self.managed_snapshot(agents), self.managed_snapshot(state), sentinel.read_bytes(), sentinel.lstat().st_ino)
                with self.assertRaises(ProfileConflict):
                    preview_profiles("install", load_config(state), agents, state, now=100)
                after = (self.managed_snapshot(agents), self.managed_snapshot(state), sentinel.read_bytes(), sentinel.lstat().st_ino)
                self.assertEqual(after, before)

    @unittest.skipUnless(os.name == "posix", "cooperating mutation race is POSIX-only")
    def test_cooperating_plan_consumers_publish_once_without_partial_state(self) -> None:
        plans = ensure_private_directory(self.state / "plans-race")
        token = create_plan("race", (), plans, now=100)
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def consume() -> None:
            try:
                barrier.wait(timeout=2)
                outcomes.append(str(consume_plan(token, "race", plans, lambda _plan: "applied", now=100)))
            except PlanError:
                outcomes.append("refused")

        workers = [threading.Thread(target=consume) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(sorted(outcomes), ["applied", "refused"])
        self.assertEqual(len(list((plans / "consumed").glob("*.json"))), 1)
        self.assertEqual(list(plans.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
