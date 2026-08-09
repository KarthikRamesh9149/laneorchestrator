"""Zero-configuration defaults and strict loading for logical role settings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple

from .models import (
    LOGICAL_ROLES,
    EffectiveConfig,
    RoleConfig,
    is_valid_model_id,
    is_valid_reasoning_effort,
)
from .security import SecurityError, read_regular_nofollow


SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 64 * 1024
MAX_VALUE_CHARS = 256
TOP_LEVEL_FIELDS = frozenset(("schema_version", "roles"))
ROLE_FIELDS = frozenset(("model", "reasoning_effort"))
SECRET_KEY_RE = re.compile(r"(?:^|[_\-.])(?:api[_\-.]?key|token|password|secret)(?:$|[_\-.])", re.IGNORECASE)

DEFAULT_ROLES = {
    "router": RoleConfig("gpt-5.6-sol", "high"),
    "small_task_executor": RoleConfig("gpt-5.6-luna", "high"),
    "main_implementer": RoleConfig("gpt-5.6-terra", "high"),
    "independent_reviewer": RoleConfig("gpt-5.6-sol", "high"),
}


class ConfigError(ValueError):
    """Raised when configuration is malformed or exceeds the v1 contract."""


def reject_duplicate_pairs(pairs: Sequence[Tuple[str, object]]) -> Mapping[str, object]:
    """Build one JSON object while rejecting duplicate names at every depth."""

    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate JSON object key: {0}".format(key))
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ConfigError("invalid JSON constant: {0}".format(value))


def parse_config_bytes(content: bytes) -> object:
    """Decode exactly one strict UTF-8 JSON document with duplicate detection."""

    if not isinstance(content, bytes):
        raise ConfigError("configuration content must be bytes")
    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as error:
        raise ConfigError("configuration must be UTF-8") from error
    except json.JSONDecodeError as error:
        raise ConfigError("configuration is not valid JSON") from error


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_secret_like_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(".", "_")
    compact = normalized.replace("_", "")
    return bool(SECRET_KEY_RE.search(normalized)) or any(
        marker in compact for marker in ("apikey", "token", "password", "secret")
    )


def _validate_safe_values(value: object) -> None:
    """Reject unsafe strings and credential-shaped keys before schema handling."""

    if isinstance(value, str):
        if len(value) > MAX_VALUE_CHARS:
            raise ConfigError("configuration string exceeds {0} characters".format(MAX_VALUE_CHARS))
        if _has_control_character(value):
            raise ConfigError("configuration contains a control character")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ConfigError("configuration object keys must be strings")
            _validate_safe_values(key)
            if _is_secret_like_key(key):
                raise ConfigError("configuration must not contain secret-like keys")
            _validate_safe_values(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _validate_safe_values(nested)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConfigError("{0} must be an object".format(label))
    if not all(isinstance(key, str) for key in value):
        raise ConfigError("{0} object keys must be strings".format(label))
    return value


def _exact_fields(payload: Mapping[str, object], allowed: frozenset, label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ConfigError("unknown {0} field: {1}".format(label, unknown[0]))


def _role_config(role: str, value: object) -> RoleConfig:
    payload = _mapping(value, "role {0}".format(role))
    _exact_fields(payload, ROLE_FIELDS, "role")
    missing = sorted(ROLE_FIELDS - set(payload))
    if missing:
        raise ConfigError("missing role field: {0}".format(missing[0]))
    model = payload["model"]
    effort = payload["reasoning_effort"]
    if not is_valid_model_id(model):
        raise ConfigError("invalid model identifier")
    if not is_valid_reasoning_effort(effort):
        raise ConfigError("invalid reasoning effort")
    return RoleConfig(model, effort)


def validate_config_payload(payload: object) -> EffectiveConfig:
    """Validate a schema-v1 payload and merge explicit roles over defaults."""

    _validate_safe_values(payload)
    document = _mapping(payload, "configuration")
    _exact_fields(document, TOP_LEVEL_FIELDS, "configuration")
    missing = sorted(TOP_LEVEL_FIELDS - set(document))
    if missing:
        raise ConfigError("missing configuration field: {0}".format(missing[0]))
    schema_version = document["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise ConfigError("schema_version must be {0}".format(SCHEMA_VERSION))
    role_payloads = _mapping(document["roles"], "roles")
    unknown_roles = sorted(set(role_payloads) - set(LOGICAL_ROLES))
    if unknown_roles:
        raise ConfigError("unknown logical role: {0}".format(unknown_roles[0]))
    roles = dict(DEFAULT_ROLES)
    for role in LOGICAL_ROLES:
        if role in role_payloads:
            roles[role] = _role_config(role, role_payloads[role])
    return EffectiveConfig(SCHEMA_VERSION, roles, "file")


def load_config(state_root: Path) -> EffectiveConfig:
    """Load ``config.json`` or return complete built-in defaults when absent."""

    path = Path(state_root) / "config.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return EffectiveConfig(SCHEMA_VERSION, DEFAULT_ROLES, "defaults")
    except OSError as error:
        raise ConfigError("could not inspect configuration") from error
    try:
        content = read_regular_nofollow(path, MAX_CONFIG_BYTES)
    except (OSError, SecurityError) as error:
        raise ConfigError("could not safely read configuration") from error
    return validate_config_payload(parse_config_bytes(content))


def serialize_config(config: EffectiveConfig) -> bytes:
    """Serialize a complete effective config as deterministic UTF-8 JSON."""

    if not isinstance(config, EffectiveConfig):
        raise ConfigError("config must be an EffectiveConfig")
    payload = {
        "schema_version": config.schema_version,
        "roles": {
            role: {
                "model": config.roles[role].model,
                "reasoning_effort": config.roles[role].reasoning_effort,
            }
            for role in LOGICAL_ROLES
        },
    }
    validate_config_payload(payload)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
