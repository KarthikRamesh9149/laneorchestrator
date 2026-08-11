"""Zero-configuration defaults and strict loading for logical role settings."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .models import (
    LOGICAL_ROLES,
    EffectiveConfig,
    RoleConfig,
    is_valid_model_id,
    is_valid_reasoning_effort,
)
from .diagnostics import CommandResult, command_result
from .plans import MutationPlan, Operation, PlanError, approval_digest, consume_plan, create_plan, load_plan, validate_json_nesting
from .security import (
    SecurityError,
    close_private_lock,
    open_owned_directory_nofollow,
    open_parent_directory_nofollow,
    open_private_lock_at,
    private_temporary_name,
    read_regular_nofollow,
    validate_destination_at,
    write_all,
)


SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 64 * 1024
MAX_VALUE_CHARS = 256
TOP_LEVEL_FIELDS = frozenset(("schema_version", "roles"))
ROLE_FIELDS = frozenset(("model", "reasoning_effort"))
SECRET_KEY_RE = re.compile(r"(?:^|[_\-.])(?:api[_\-.]?key|token|password|secret)(?:$|[_\-.])", re.IGNORECASE)
CONFIG_NAME = "config.json"
PLANS_DIRECTORY = "plans"
CONFIG_PLAN_KIND = "configure"
MAX_CONFIG_SETS = 8
MAX_CONFIG_NESTING = 64

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
        validate_json_nesting(content, limit=MAX_CONFIG_NESTING)
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except PlanError as error:
        raise ConfigError("configuration JSON nesting exceeds {0}".format(MAX_CONFIG_NESTING)) from error
    except (UnicodeDecodeError, RecursionError) as error:
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


def _validate_safe_values(value: object, depth: int = 0) -> None:
    """Reject unsafe strings and credential-shaped keys before schema handling."""

    if depth > MAX_CONFIG_NESTING:
        raise ConfigError("configuration nesting exceeds {0}".format(MAX_CONFIG_NESTING))
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
            _validate_safe_values(key, depth + 1)
            if _is_secret_like_key(key):
                raise ConfigError("configuration must not contain secret-like keys")
            _validate_safe_values(nested, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _validate_safe_values(nested, depth + 1)


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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identity_hash(metadata: os.stat_result) -> str:
    value = "{0}:{1}:{2}:{3}".format(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
    ).encode("ascii")
    return _sha256(value)


def ensure_private_directory(path: Path) -> Path:
    """Create one private leaf below a safe owned parent, or validate it."""

    candidate = Path(path)
    if not candidate.is_absolute() or candidate.name in ("", ".", ".."):
        raise ConfigError("state root must be an absolute safe path")
    parent_fd = -1
    try:
        parent_fd = open_owned_directory_nofollow(candidate.parent)
        try:
            os.mkdir(candidate.name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
        except OSError as error:
            raise ConfigError("could not create private state directory") from error
    except SecurityError as error:
        raise ConfigError("state root parent is unsafe: {0}".format(error)) from error
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    try:
        descriptor = open_parent_directory_nofollow(candidate)
    except SecurityError as error:
        raise ConfigError("state root is unsafe: {0}".format(error)) from error
    else:
        os.close(descriptor)
    return candidate


def _read_config_snapshot(state_root: Path) -> Tuple[Optional[bytes], str]:
    descriptor = open_parent_directory_nofollow(state_root)
    lock_fd = -1
    try:
        lock_fd = open_private_lock_at(descriptor)
        root_hash = _identity_hash(os.fstat(descriptor))
        metadata = validate_destination_at(descriptor, CONFIG_NAME)
        if metadata is None:
            return None, root_hash
        content = _read_config_at(descriptor, metadata)
        return content, root_hash
    except SecurityError as error:
        raise ConfigError("could not safely inspect configuration state") from error
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        os.close(descriptor)


def _read_config_at(parent_fd: int, metadata: os.stat_result) -> bytes:
    """Read the exact held-parent config object and recheck its identity."""

    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ConfigError("configuration file mode must be 0600")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(CONFIG_NAME, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ConfigError("could not open configuration safely") from error
    try:
        opened = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise ConfigError("configuration changed while opening")
        content = b""
        while len(content) <= MAX_CONFIG_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, MAX_CONFIG_BYTES + 1 - len(content)),
            )
            if not chunk:
                break
            content += chunk
        if len(content) > MAX_CONFIG_BYTES:
            raise ConfigError("configuration exceeds maximum size")
        current = validate_destination_at(parent_fd, CONFIG_NAME)
        if current is None or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise ConfigError("configuration changed while reading")
        return content
    finally:
        os.close(descriptor)


def _validate_updates(updates: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(updates, Mapping) or not updates:
        raise ConfigError("at least one configuration setting is required")
    if len(updates) > MAX_CONFIG_SETS:
        raise ConfigError("configuration accepts at most {0} settings".format(MAX_CONFIG_SETS))
    validated: Dict[str, str] = {}
    for key, value in updates.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError("configuration settings must be strings")
        role, separator, field = key.partition(".")
        if separator != "." or role not in LOGICAL_ROLES or field not in ROLE_FIELDS:
            raise ConfigError("setting must use ROLE.model or ROLE.reasoning_effort")
        if len(value) > MAX_VALUE_CHARS or _has_control_character(value):
            raise ConfigError("configuration setting value is unsafe")
        if _is_secret_like_key(value):
            raise ConfigError("configuration setting resembles a secret")
        if field == "model" and not is_valid_model_id(value):
            raise ConfigError("invalid model identifier")
        if field == "reasoning_effort" and not is_valid_reasoning_effort(value):
            raise ConfigError("invalid reasoning effort")
        validated[key] = value
    return validated


def preview_config(
    updates: Mapping[str, str], state_root: Path, now: Optional[int] = None
) -> Tuple[str, CommandResult]:
    """Create a private exact-state plan for a configuration update."""

    changes = _validate_updates(updates)
    state = ensure_private_directory(state_root)
    before, root_hash = _read_config_snapshot(state)
    current = (
        EffectiveConfig(SCHEMA_VERSION, DEFAULT_ROLES, "defaults")
        if before is None
        else validate_config_payload(parse_config_bytes(before))
    )
    roles = dict(current.roles)
    for key, value in changes.items():
        role, field = key.split(".", 1)
        existing = roles[role]
        roles[role] = RoleConfig(
            value if field == "model" else existing.model,
            value if field == "reasoning_effort" else existing.reasoning_effort,
        )
    proposed = serialize_config(EffectiveConfig(SCHEMA_VERSION, roles, "file"))
    destination = state / CONFIG_NAME
    operations = (
        Operation(os.fspath(state), root_hash, root_hash, None),
        Operation(
            os.fspath(destination),
            None if before is None else _sha256(before),
            _sha256(proposed),
            base64.b64encode(proposed).decode("ascii"),
        ),
    )
    plans_root = ensure_private_directory(state / PLANS_DIRECTORY)
    try:
        token = create_plan(CONFIG_PLAN_KIND, operations, plans_root, now=now)
    except (PlanError, SecurityError) as error:
        raise ConfigError("could not create configuration preview") from error
    return token, command_result(
        "configure",
        data={
            "after_sha256": _sha256(proposed),
            "before_sha256": None if before is None else _sha256(before),
            "destination": os.fspath(destination),
            "expires_in_seconds": 600,
            "approval_digest": approval_digest(load_plan(token, CONFIG_PLAN_KIND, plans_root, now=now)),
            "phase": "preview",
            "settings": sorted(changes),
            "token": token,
        },
    )


def _decode_planned_content(operation: Operation) -> bytes:
    if operation.content_b64 is None:
        raise ConfigError("configuration plan has no proposed content")
    try:
        content = base64.b64decode(operation.content_b64.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as error:
        raise ConfigError("configuration plan content is invalid") from error
    if _sha256(content) != operation.after_sha256:
        raise ConfigError("configuration plan content hash is invalid")
    validate_config_payload(parse_config_bytes(content))
    return content


def _write_config_at_locked(parent_fd: int, content: bytes) -> None:
    before = validate_destination_at(parent_fd, CONFIG_NAME)
    temporary = private_temporary_name(CONFIG_NAME)
    descriptor = -1
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        created = True
        os.fchmod(descriptor, 0o600)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        current = validate_destination_at(parent_fd, CONFIG_NAME)
        if (before is None) != (current is None) or before is not None and current is not None and (
            before.st_dev,
            before.st_ino,
        ) != (current.st_dev, current.st_ino):
            raise ConfigError("configuration changed before publication")
        os.replace(temporary, CONFIG_NAME, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        created = False
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass


def _apply_config_plan(plan: MutationPlan, state_root: Path) -> CommandResult:
    if len(plan.operations) != 2:
        raise ConfigError("configuration plan operation count is invalid")
    root_operation, config_operation = plan.operations
    expected_root = os.fspath(state_root)
    expected_config = os.fspath(state_root / CONFIG_NAME)
    if (
        root_operation.path != expected_root
        or root_operation.before_sha256 != root_operation.after_sha256
        or root_operation.content_b64 is not None
        or config_operation.path != expected_config
        or config_operation.after_sha256 is None
    ):
        raise ConfigError("configuration plan destination binding is invalid")
    proposed = _decode_planned_content(config_operation)
    parent_fd = open_parent_directory_nofollow(state_root)
    lock_fd = -1
    try:
        lock_fd = open_private_lock_at(parent_fd)
        if _identity_hash(os.fstat(parent_fd)) != root_operation.before_sha256:
            raise ConfigError("configuration state root changed after preview")
        metadata = validate_destination_at(parent_fd, CONFIG_NAME)
        if metadata is None:
            current_hash = None
        else:
            current_hash = _sha256(_read_config_at(parent_fd, metadata))
        if current_hash != config_operation.before_sha256:
            raise ConfigError("configuration changed after preview")
        _write_config_at_locked(parent_fd, proposed)
    except (OSError, SecurityError) as error:
        raise ConfigError("configuration apply failed safely") from error
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        os.close(parent_fd)
    return command_result(
        "configure",
        data={
            "after_sha256": config_operation.after_sha256,
            "before_sha256": config_operation.before_sha256,
            "destination": expected_config,
            "phase": "apply",
        },
    )


def apply_config(
    token: str, state_root: Path, approval: Optional[str] = None, now: Optional[int] = None
) -> CommandResult:
    """Consume and apply an unchanged, unexpired configuration plan."""

    state = Path(state_root)
    try:
        return consume_plan(
            token,
            CONFIG_PLAN_KIND,
            state / PLANS_DIRECTORY,
            lambda plan: _apply_config_plan(plan, state),
            approval=approval,
            now=now,
        )
    except (PlanError, ConfigError):
        raise
    except SecurityError as error:
        raise ConfigError("configuration plan could not be applied") from error
