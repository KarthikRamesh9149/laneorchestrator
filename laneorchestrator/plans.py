"""Expiring, one-time mutation plans stored as private local state.

The state fingerprint is deliberately narrow: it is SHA-256 over the
canonical serialized operation list, which includes every operation path,
before/after hash, and optional proposed content.  It detects corruption of a
plan without expanding the public API to accept a separate state root.

Mutation safety inherits :mod:`laneorchestrator.security`'s boundary: callers
with the same EUID must cooperate with the advisory lock.  A same-EUID process
that deliberately bypasses that lock is outside this module's threat model.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple, TypeVar

from laneorchestrator.security import (
    SecurityError,
    atomic_private_write,
    close_private_lock,
    create_private_file_at_locked,
    open_parent_directory_nofollow,
    open_private_lock_at,
    read_regular_nofollow,
    validate_destination_at,
)


SCHEMA_VERSION = 1
PLAN_TTL_SECONDS = 600
MAX_PLAN_BYTES = 1024 * 1024
MAX_JSON_NESTING = 64

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_KIND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DOCUMENT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "created_at",
        "expires_at",
        "state_fingerprint",
        "operations",
    }
)
_OPERATION_KEYS = frozenset(
    {"path", "before_sha256", "after_sha256", "content_b64"}
)
_CONSUMED_DIRECTORY_NAME = "consumed"
_CONSUMED_CONTENT = b"consumed\n"
_TOKEN_GENERATION_ATTEMPTS = 16

T = TypeVar("T")


class PlanError(SecurityError):
    """Raised when a mutation plan is invalid, unsafe, expired, or consumed."""


def validate_json_nesting(content: bytes, *, limit: int = MAX_JSON_NESTING) -> None:
    """Reject structurally over-nested JSON before CPython can recurse."""

    if not isinstance(content, bytes):
        raise PlanError("JSON content must be bytes")
    depth = 0
    quoted = False
    escaped = False
    for byte in content:
        if quoted:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                quoted = False
            continue
        if byte == ord('"'):
            quoted = True
        elif byte in (ord("["), ord("{")):
            depth += 1
            if depth > limit:
                raise PlanError("JSON nesting exceeds {0}".format(limit))
        elif byte in (ord("]"), ord("}")):
            depth -= 1
            if depth < 0:
                return


def approval_digest(plan: "MutationPlan") -> str:
    """Return the exact review digest a host must bind to human approval."""

    payload = {
        "action": plan.kind,
        "expires_at": plan.expires_at,
        "state_fingerprint": plan.state_fingerprint,
        "targets": sorted(operation.path for operation in plan.operations),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _validate_approval_event(approval: object, plan: "MutationPlan") -> None:
    """Require an independently supplied host approval for this exact preview."""

    expected = "approve:" + approval_digest(plan)
    if not isinstance(approval, str) or not secrets.compare_digest(approval, expected):
        raise PlanError("plan requires an explicit approval event for this preview")


@dataclass(frozen=True)
class Operation:
    """One immutable file mutation described by before and after state."""

    path: str
    before_sha256: Optional[str]
    after_sha256: Optional[str]
    content_b64: Optional[str]


@dataclass(frozen=True)
class MutationPlan:
    """An immutable preview whose raw authorization token is never retained."""

    schema_version: int
    kind: str
    created_at: int
    expires_at: int
    state_fingerprint: str
    operations: Sequence[Operation]

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))


def _validate_token(token: str) -> None:
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise PlanError("plan token has invalid syntax")


def _validate_kind(kind: str) -> None:
    if not isinstance(kind, str) or _KIND_PATTERN.fullmatch(kind) is None:
        raise PlanError("plan kind has invalid syntax")


def _resolve_now(now: Optional[int]) -> int:
    value = int(time.time()) if now is None else now
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlanError("plan time must be a non-negative integer")
    return value


def _validate_optional_hash(value: Optional[str], field: str) -> None:
    if value is not None and (
        not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None
    ):
        raise PlanError("operation {0} must be a lowercase SHA-256 digest".format(field))


def _decode_content(content_b64: str) -> bytes:
    try:
        encoded = content_b64.encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise PlanError("operation content_b64 is not canonical base64") from error
    if base64.b64encode(decoded).decode("ascii") != content_b64:
        raise PlanError("operation content_b64 is not canonical base64")
    return decoded


def _validated_operations(operations: Sequence[Operation]) -> Tuple[Operation, ...]:
    if isinstance(operations, (str, bytes)) or not isinstance(operations, Sequence):
        raise PlanError("plan operations must be a sequence")
    validated: List[Operation] = []
    for operation in operations:
        if not isinstance(operation, Operation):
            raise PlanError("plan operations must contain Operation values")
        if (
            not isinstance(operation.path, str)
            or not operation.path
            or "\x00" in operation.path
        ):
            raise PlanError("operation path must be a non-empty string")
        _validate_optional_hash(operation.before_sha256, "before_sha256")
        _validate_optional_hash(operation.after_sha256, "after_sha256")
        if operation.content_b64 is not None:
            if not isinstance(operation.content_b64, str):
                raise PlanError("operation content_b64 must be a string or null")
            decoded = _decode_content(operation.content_b64)
            if operation.after_sha256 is None:
                raise PlanError("operation content requires an after_sha256 digest")
            if hashlib.sha256(decoded).hexdigest() != operation.after_sha256:
                raise PlanError("operation content does not match after_sha256")
        validated.append(operation)
    return tuple(validated)


def _operation_document(operation: Operation) -> Dict[str, Optional[str]]:
    return {
        "after_sha256": operation.after_sha256,
        "before_sha256": operation.before_sha256,
        "content_b64": operation.content_b64,
        "path": operation.path,
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _state_fingerprint(operations: Sequence[Operation]) -> str:
    operation_bytes = _canonical_json_bytes(
        {"operations": [_operation_document(operation) for operation in operations]}
    )
    return hashlib.sha256(operation_bytes).hexdigest()


def _encode_plan(plan: MutationPlan) -> bytes:
    operations = _validated_operations(plan.operations)
    document = {
        "created_at": plan.created_at,
        "expires_at": plan.expires_at,
        "kind": plan.kind,
        "operations": [_operation_document(operation) for operation in operations],
        "schema_version": plan.schema_version,
        "state_fingerprint": plan.state_fingerprint,
    }
    return _canonical_json_bytes(document)


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanError("plan is corrupt: duplicate JSON key")
        result[key] = value
    return result


def _require_exact_keys(document: Dict[str, Any], expected: frozenset, label: str) -> None:
    if frozenset(document) != expected:
        raise PlanError("plan {0} schema is invalid".format(label))


def _decode_plan(content: bytes) -> MutationPlan:
    try:
        validate_json_nesting(content)
        document = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except PlanError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PlanError("plan is corrupt JSON") from error
    if not isinstance(document, dict):
        raise PlanError("plan schema is invalid")
    _require_exact_keys(document, _DOCUMENT_KEYS, "document")

    schema_version = document["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise PlanError("plan schema version is unsupported")

    kind = document["kind"]
    _validate_kind(kind)
    created_at = document["created_at"]
    expires_at = document["expires_at"]
    for timestamp, label in ((created_at, "created_at"), (expires_at, "expires_at")):
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise PlanError("plan {0} schema is invalid".format(label))
    if expires_at != created_at + PLAN_TTL_SECONDS:
        raise PlanError("plan expiry schema is invalid")

    fingerprint = document["state_fingerprint"]
    if not isinstance(fingerprint, str) or _HASH_PATTERN.fullmatch(fingerprint) is None:
        raise PlanError("plan state fingerprint schema is invalid")

    operation_documents = document["operations"]
    if not isinstance(operation_documents, list):
        raise PlanError("plan operations schema is invalid")
    operations: List[Operation] = []
    for operation_document in operation_documents:
        if not isinstance(operation_document, dict):
            raise PlanError("plan operation schema is invalid")
        _require_exact_keys(operation_document, _OPERATION_KEYS, "operation")
        operations.append(
            Operation(
                path=operation_document["path"],
                before_sha256=operation_document["before_sha256"],
                after_sha256=operation_document["after_sha256"],
                content_b64=operation_document["content_b64"],
            )
        )
    validated = _validated_operations(operations)
    return MutationPlan(
        schema_version=schema_version,
        kind=kind,
        created_at=created_at,
        expires_at=expires_at,
        state_fingerprint=fingerprint,
        operations=validated,
    )


def _plan_path_for_token(token: str, plans_root: Path) -> Path:
    _validate_token(token)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return Path(plans_root) / (digest + ".json")


def _consumed_path_for_plan(plan_path: Path) -> Path:
    return plan_path.parent / _CONSUMED_DIRECTORY_NAME / plan_path.name


def _validate_private_directory_metadata(metadata: os.stat_result) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise PlanError("consumed plan root is not a directory")
    if metadata.st_uid != os.geteuid():
        raise PlanError("consumed plan root has the wrong owner")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise PlanError("consumed plan root mode must be 0700")


def _ensure_consumed_root_locked(parent_fd: int) -> None:
    try:
        metadata = os.stat(
            _CONSUMED_DIRECTORY_NAME, dir_fd=parent_fd, follow_symlinks=False
        )
    except FileNotFoundError:
        try:
            os.mkdir(_CONSUMED_DIRECTORY_NAME, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            metadata = os.stat(
                _CONSUMED_DIRECTORY_NAME, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as error:
            raise PlanError("could not create consumed plan root safely") from error
    except OSError as error:
        raise PlanError("could not inspect consumed plan root safely") from error
    _validate_private_directory_metadata(metadata)


@contextmanager
def _locked_plans_root(plans_root: Path) -> Iterator[Tuple[int, int]]:
    parent_fd = -1
    lock_fd = -1
    try:
        parent_fd = open_parent_directory_nofollow(Path(plans_root))
        lock_fd = open_private_lock_at(parent_fd)
        yield parent_fd, lock_fd
    except PlanError:
        raise
    except SecurityError as error:
        raise PlanError("plans root is not safe: {0}".format(error)) from error
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _tombstone_exists(plan_path: Path) -> bool:
    consumed_root = plan_path.parent / _CONSUMED_DIRECTORY_NAME
    consumed_fd = -1
    try:
        consumed_fd = open_parent_directory_nofollow(consumed_root)
        try:
            os.stat(plan_path.name, dir_fd=consumed_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise PlanError("could not inspect plan tombstone safely") from error
        return True
    except PlanError:
        raise
    except SecurityError as error:
        raise PlanError("consumed plan root is not safe: {0}".format(error)) from error
    finally:
        if consumed_fd >= 0:
            os.close(consumed_fd)


def _create_unique_plan_locked(
    parent_fd: int, plans_root: Path, content: bytes
) -> str:
    for _attempt in range(_TOKEN_GENERATION_ATTEMPTS):
        token = secrets.token_urlsafe(32)
        _validate_token(token)
        # A raw value beginning with '-' is valid base64url but argparse treats
        # it as another option in the documented ``--token TOKEN`` form.
        # Rejection sampling preserves the 32-byte CSPRNG source policy while
        # guaranteeing every token we issue is directly command-consumable.
        if token.startswith("-"):
            continue
        plan_path = _plan_path_for_token(token, plans_root)
        if _tombstone_exists(plan_path):
            continue
        try:
            create_private_file_at_locked(
                parent_fd, plan_path.name, content, mode=0o600
            )
        except FileExistsError:
            continue
        else:
            return token
    raise PlanError("could not generate a unique plan token")


def _read_private_plan(plan_path: Path) -> bytes:
    parent_fd = -1
    try:
        parent_fd = open_parent_directory_nofollow(plan_path.parent)
        metadata = validate_destination_at(parent_fd, plan_path.name)
        if metadata is None:
            raise PlanError("plan was not found")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise PlanError("plan file mode must be 0600")
        try:
            content = read_regular_nofollow(plan_path, MAX_PLAN_BYTES)
        except FileNotFoundError as error:
            raise PlanError("plan was not found") from error
        except SecurityError as error:
            if "maximum size" in str(error):
                raise PlanError("plan exceeds maximum size") from error
            raise PlanError("plan file is unsafe: {0}".format(error)) from error
        current = validate_destination_at(parent_fd, plan_path.name)
        if current is None or (metadata.st_dev, metadata.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise PlanError("plan file changed while reading")
        if stat.S_IMODE(current.st_mode) != 0o600:
            raise PlanError("plan file mode must be 0600")
        return content
    except PlanError:
        raise
    except SecurityError as error:
        raise PlanError("plan file is unsafe: {0}".format(error)) from error
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def _load_plan_locked(
    token: str, expected_kind: str, plans_root: Path, now: int
) -> MutationPlan:
    plan_path = _plan_path_for_token(token, plans_root)
    if _tombstone_exists(plan_path):
        raise PlanError("plan token was already used")
    plan = _decode_plan(_read_private_plan(plan_path))
    if plan.kind != expected_kind:
        raise PlanError("plan kind does not match the requested mutation")
    if now < plan.created_at:
        raise PlanError("plan is not valid before its creation time")
    if now > plan.expires_at:
        raise PlanError("plan has expired")
    expected_fingerprint = _state_fingerprint(plan.operations)
    if not secrets.compare_digest(plan.state_fingerprint, expected_fingerprint):
        raise PlanError("plan state fingerprint does not match its operations")
    return plan


def _unlink_regular_nofollow_locked(parent_fd: int, name: str) -> None:
    metadata = validate_destination_at(parent_fd, name)
    if metadata is None:
        return
    try:
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError as error:
        raise OSError("could not durably remove consumed plan") from error


def _unlink_regular_nofollow(path: Path) -> None:
    candidate = Path(path)
    with _locked_plans_root(candidate.parent) as (parent_fd, _lock_fd):
        _unlink_regular_nofollow_locked(parent_fd, candidate.name)


def create_plan(
    kind: str,
    operations: Sequence[Operation],
    plans_root: Path,
    now: Optional[int] = None,
) -> str:
    """Create a private ten-minute mutation plan and return its raw token."""

    _validate_kind(kind)
    created_at = _resolve_now(now)
    validated = _validated_operations(operations)
    fingerprint = _state_fingerprint(validated)
    plan = MutationPlan(
        schema_version=SCHEMA_VERSION,
        kind=kind,
        created_at=created_at,
        expires_at=created_at + PLAN_TTL_SECONDS,
        state_fingerprint=fingerprint,
        operations=validated,
    )
    content = _encode_plan(plan)
    if len(content) > MAX_PLAN_BYTES:
        raise PlanError("plan exceeds maximum size")

    root = Path(plans_root)
    try:
        with _locked_plans_root(root) as (parent_fd, _lock_fd):
            _ensure_consumed_root_locked(parent_fd)
            token = _create_unique_plan_locked(parent_fd, root, content)
    except PlanError:
        raise
    except SecurityError as error:
        raise PlanError("could not create private plan: {0}".format(error)) from error
    return token


def load_plan(
    token: str,
    expected_kind: str,
    plans_root: Path,
    now: Optional[int] = None,
) -> MutationPlan:
    """Load and validate an unexpired, unconsumed mutation plan."""

    _validate_token(token)
    _validate_kind(expected_kind)
    current_time = _resolve_now(now)
    root = Path(plans_root)
    with _locked_plans_root(root):
        return _load_plan_locked(token, expected_kind, root, current_time)


def consume_plan(
    token: str,
    expected_kind: str,
    plans_root: Path,
    apply: Callable[[MutationPlan], T],
    approval: Optional[str] = None,
    now: Optional[int] = None,
) -> T:
    """Durably consume a valid plan before invoking ``apply`` exactly once."""

    _validate_token(token)
    _validate_kind(expected_kind)
    if not callable(apply):
        raise PlanError("plan apply callback must be callable")
    current_time = _resolve_now(now)
    root = Path(plans_root)
    plan_path = _plan_path_for_token(token, root)
    with _locked_plans_root(root) as (parent_fd, _lock_fd):
        plan = _load_plan_locked(token, expected_kind, root, current_time)
        _validate_approval_event(approval, plan)
        try:
            atomic_private_write(
                _consumed_path_for_plan(plan_path), _CONSUMED_CONTENT, mode=0o600
            )
        except SecurityError as error:
            raise PlanError("could not persist plan tombstone: {0}".format(error)) from error
        _unlink_regular_nofollow_locked(parent_fd, plan_path.name)
    return apply(plan)
