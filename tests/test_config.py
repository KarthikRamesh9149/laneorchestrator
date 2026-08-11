from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from laneorchestrator.config import (
    DEFAULT_ROLES,
    MAX_CONFIG_BYTES,
    ConfigError,
    load_config,
    parse_config_bytes,
    serialize_config,
    validate_config_payload,
)
from laneorchestrator.security import SecurityError, read_regular_nofollow


FIXTURES = Path(__file__).parent / "fixtures" / "config"


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def valid_payload(self) -> object:
        return json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))

    def test_no_file_uses_codex_first_defaults(self) -> None:
        config = load_config(self.state_root)
        self.assertEqual(config.source, "defaults")
        self.assertEqual(config.roles, DEFAULT_ROLES)
        self.assertEqual(config.roles["router"].model, "gpt-5.6-sol")
        self.assertEqual(config.roles["small_task_executor"].model, "gpt-5.6-luna")
        self.assertEqual(config.roles["main_implementer"].model, "gpt-5.6-terra")
        self.assertEqual(config.roles["independent_reviewer"].model, "gpt-5.6-sol")

    def test_valid_file_round_trips_in_stable_utf8_json(self) -> None:
        self.state_root.joinpath("config.json").write_bytes((FIXTURES / "valid.json").read_bytes())
        config = load_config(self.state_root)
        serialized = serialize_config(config)
        self.assertEqual(config.source, "file")
        self.assertTrue(serialized.endswith(b"\n"))
        self.assertFalse(serialized.endswith(b"\n\n"))
        self.assertEqual(serialized, serialize_config(config))
        self.assertEqual(json.loads(serialized), json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8")))

    def test_rejects_unknown_fields_and_unknown_roles(self) -> None:
        for payload in (
            json.loads((FIXTURES / "unknown-field.json").read_text(encoding="utf-8")),
            {"schema_version": 1, "roles": {"not_a_role": {"model": "gpt-5.6-terra", "reasoning_effort": "high"}}},
            {"schema_version": 1, "roles": {"router": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "extra": True}}},
        ):
            with self.assertRaises(ConfigError):
                validate_config_payload(payload)

    def test_rejects_duplicate_keys_before_mapping_conversion(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config_bytes(b'{"schema_version": 1, "schema_version": 1, "roles": {}}')
        with self.assertRaises(ConfigError):
            parse_config_bytes(b'{"schema_version": 1, "roles": {"router": {"model": "a", "reasoning_effort": "high"}, "router": {"model": "b", "reasoning_effort": "high"}}}')
        with self.assertRaises(ConfigError):
            parse_config_bytes(b'{"schema_version": 1, "roles": {"router": {"model": "a", "model": "b", "reasoning_effort": "high"}}}')

    def test_deeply_nested_json_is_a_domain_failure_not_recursion_error(self) -> None:
        nested = (b"[" * 1200) + b"0" + (b"]" * 1200)
        with self.assertRaisesRegex(ConfigError, "nesting"):
            parse_config_bytes(nested)

    def test_rejects_every_secret_key_at_any_depth(self) -> None:
        payload = self.valid_payload()
        for key in ("api_key", "token", "password", "secret"):
            candidate = json.loads(json.dumps(payload))
            candidate["roles"]["router"]["metadata"] = {"nested": {key: "never"}}
            with self.assertRaises(ConfigError, msg=key):
                validate_config_payload(candidate)
        with self.assertRaises(ConfigError):
            validate_config_payload(json.loads((FIXTURES / "secret-key.json").read_text(encoding="utf-8")))

    def test_rejects_invalid_types_schema_model_effort_and_text_bounds(self) -> None:
        candidates = [
            None,
            [],
            {"schema_version": 2, "roles": {}},
            {"schema_version": 1.0, "roles": {}},
            {"schema_version": True, "roles": {}},
            {"schema_version": 1, "roles": []},
            {"schema_version": 1, "roles": {"router": []}},
            {"schema_version": 1, "roles": {"router": {"model": "GPT-5.6-terra", "reasoning_effort": "high"}}},
            {"schema_version": 1, "roles": {"router": {"model": "gpt-5.6-terra", "reasoning_effort": "highest"}}},
            {"schema_version": 1, "roles": {"router": {"model": "gpt-5.6-terra\n", "reasoning_effort": "high"}}},
            {"schema_version": 1, "roles": {"router": {"model": "a" * 257, "reasoning_effort": "high"}}},
        ]
        for payload in candidates:
            with self.assertRaises(ConfigError):
                validate_config_payload(payload)

    def test_present_invalid_config_fails_closed(self) -> None:
        self.state_root.joinpath("config.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(self.state_root)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW unavailable")
    def test_present_linked_config_fails_closed(self) -> None:
        outside = self.state_root / "outside.json"
        outside.write_bytes((FIXTURES / "valid.json").read_bytes())
        self.state_root.joinpath("config.json").symlink_to(outside)
        with self.assertRaises(ConfigError):
            load_config(self.state_root)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW unavailable")
    def test_read_regular_nofollow_rejects_links_non_regular_files_and_oversize(self) -> None:
        content = self.state_root / "content.json"
        content.write_bytes(b"{}")
        link = self.state_root / "link.json"
        link.symlink_to(content)
        with self.assertRaises(SecurityError):
            read_regular_nofollow(link, MAX_CONFIG_BYTES)
        with self.assertRaises(SecurityError):
            read_regular_nofollow(self.state_root, MAX_CONFIG_BYTES)
        with self.assertRaises(SecurityError):
            read_regular_nofollow(content, 1)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW unavailable")
    def test_read_regular_nofollow_fails_closed_without_platform_support(self) -> None:
        content = self.state_root / "content.json"
        content.write_bytes(b"{}")
        patcher = mock.patch.object(os, "O_NOFOLLOW", os.O_NOFOLLOW)
        patcher.start()
        try:
            del os.O_NOFOLLOW
            with self.assertRaises(SecurityError):
                read_regular_nofollow(content, MAX_CONFIG_BYTES)
        finally:
            patcher.stop()


if __name__ == "__main__":
    unittest.main()
