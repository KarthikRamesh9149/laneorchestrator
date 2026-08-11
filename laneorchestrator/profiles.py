"""Deterministic rendering and fail-closed lifecycle for managed profiles."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .config import MAX_CONFIG_BYTES, serialize_config
from .diagnostics import CommandResult, command_result
from .models import EffectiveConfig, LOGICAL_ROLES
from .plans import MutationPlan, Operation, PlanError, approval_digest, consume_plan, create_plan, load_plan, validate_json_nesting
from .security import (
    SecurityError,
    close_private_lock,
    open_owned_directory_nofollow,
    open_owned_lock_at,
    open_parent_directory_nofollow,
    open_private_lock_at,
    platform_mutation_supported,
    private_temporary_name,
    validate_destination_at,
    write_all,
)


PROFILE_NAMES = (
    "laneorchestrator-router.toml",
    "laneorchestrator-luna-executor.toml",
    "laneorchestrator-terra-executor.toml",
    "laneorchestrator-sol-reviewer.toml",
)
TEMPLATE_VERSION = "0.2.0"
MANAGED_MARKER = "# managed-by: laneorchestrator {0}\n".format(TEMPLATE_VERSION)
RECEIPT_NAME = "receipts.json"
PLANS_DIRECTORY = "plans"
BACKUPS_DIRECTORY = "backups"
MAX_PROFILE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
RECEIPT_SCHEMA_VERSION = 1

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = frozenset(("install", "adopt", "update", "uninstall"))
_ACTIVE_OPERATIONS = frozenset(("install", "adopt", "update"))
_V010_HASHES = {
    "laneorchestrator-luna-executor.toml": "1de0a4bf0ed0b3f32b8597991b8cc4ea5b3581d0736b4e7bb2dae47a8e9a5567",
    "laneorchestrator-router.toml": "c40f592272fb5ffe550c120fa48d1edb822a28b6b13085f9e30c8260c0d713a8",
    "laneorchestrator-sol-reviewer.toml": "078a82c418f1688b87b341463dcc59cf89c720e9434d4f3b897b991aa6f1b408",
    "laneorchestrator-terra-executor.toml": "5feb09a607e4b92b0cb251173e6ca9e6970f1fd3f256e2dcf58f90e6f972c88f",
}
_RECEIPT_KEYS = frozenset(("schema_version", "profiles"))
_RECEIPT_ENTRY_KEYS = frozenset(
    (
        "name",
        "destination",
        "template_version",
        "content_sha256",
        "config_sha256",
        "prior_backup_sha256",
        "operation",
    )
)

_PROFILE_SPECS = {
    "laneorchestrator-router.toml": (
        "router",
        "laneorchestrator-router",
        "Use to inspect project context, select relevant skills and agents, classify GPT-5.6 execution lanes, and emit a bounded delegation packet before work begins.",
        "read-only",
        """Act as LaneOrchestrator's read-only control plane. Inspect the user's objective, current conversation, project instructions, repository state, and capability inventory before routing.

Return a compact route card with: lane, evidence inspected, selected skills, selected specialist, bounded task packet, verification commands, safety status, and fallback if an intended profile/model is unavailable.

Use Luna only for one known, low-risk local change with explicit acceptance criteria. Use Terra as the normal implementation lane. For architecture-sensitive, public-contract, security/auth, financial, data-integrity, migration, concurrency, or high-blast-radius work, require Sol planning, Terra implementation, and a fresh Sol review.

Never edit files, install capabilities, or hide uncertainty. Do not delegate merely because a capability name was mentioned; select it only when it materially improves the task.

If Luna or an optional specialist is unavailable, fall back to Terra / High and report it. If Terra is unavailable, pause because implementation cannot proceed. If Sol is unavailable for required high-risk planning or independent review, pause rather than weakening the high-risk route.""",
    ),
    "laneorchestrator-luna-executor.toml": (
        "small_task_executor",
        "laneorchestrator-luna-executor",
        "Use only for router-approved, tightly scoped, low-risk tasks in one known area with explicit acceptance criteria.",
        "read-only",
        """Implement only the router-approved task packet. Keep changes small, test the stated acceptance criteria, and report exact files changed.

Stop and return the packet to Terra if the task expands beyond one known area or touches a public API, schema, auth, security, payments, persistent data, migration, concurrency, deployment, or external system. Never make external, destructive, costly, or scope-expanding actions without the parent obtaining the required approval.""",
    ),
    "laneorchestrator-terra-executor.toml": (
        "main_implementer",
        "laneorchestrator-terra-executor",
        "Use as the default GPT-5.6 implementation lane for multi-file, integration, or uncertain work after a bounded routing packet.",
        "workspace-write",
        """Implement the supplied bounded task packet. Inspect affected code before editing, preserve unrelated user changes, use selected skills and the relevant specialist where they improve correctness, and verify with the strongest available relevant checks.

Escalate rather than guessing when the task changes public contracts, auth/security boundaries, financial behavior, data integrity, migrations, concurrency, deployment, or external side effects. Return evidence, remaining risks, and rollback notes when relevant.""",
    ),
    "laneorchestrator-sol-reviewer.toml": (
        "independent_reviewer",
        "laneorchestrator-sol-reviewer",
        "Use as a fresh independent final reviewer for high-risk LaneOrchestrator changes after implementation and verification.",
        "read-only",
        """Independently review the implementation against the original route packet and project constraints. Focus on public contracts, security/auth, data integrity, migrations, concurrency, failure handling, tests, and rollback safety.

Return only a ship verdict: approve, approve with follow-ups, or block. Support every material finding with exact evidence. Do not edit files or repeat the implementer's reasoning uncritically.""",
    ),
}


class ProfileConflict(SecurityError):
    """Raised when profile state cannot be mutated without losing user data."""


def ensure_agents_root(agents_root: Path) -> Path:
    """Create the managed agents leaf or validate an existing safe owned root."""

    candidate = Path(agents_root)
    if not candidate.is_absolute() or candidate.name in ("", ".", ".."):
        raise ProfileConflict("agents root must be an absolute safe path")
    parent_fd = -1
    try:
        parent_fd = open_owned_directory_nofollow(candidate.parent)
        try:
            os.mkdir(candidate.name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
        except OSError as error:
            raise ProfileConflict("could not create managed agents root") from error
    except SecurityError as error:
        raise ProfileConflict("agents root parent is unsafe: {0}".format(error)) from error
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    try:
        descriptor = open_owned_directory_nofollow(candidate)
    except SecurityError as error:
        raise ProfileConflict("agents root is unsafe: {0}".format(error)) from error
    else:
        os.close(descriptor)
    return candidate


def _validate_config(config: EffectiveConfig) -> None:
    if not isinstance(config, EffectiveConfig):
        raise ValueError("config must be an EffectiveConfig")
    if config.schema_version != 1 or set(config.roles) != set(LOGICAL_ROLES):
        raise ValueError("config must define every logical role")
    # The canonical serializer validates model and effort values as well.
    serialize_config(config)


def render_profile(name: str, config: EffectiveConfig) -> str:
    """Render one namespaced profile in stable TOML field order."""

    _validate_config(config)
    try:
        role, profile_name, description, sandbox_mode, instructions = _PROFILE_SPECS[name]
    except (KeyError, TypeError) as error:
        raise ValueError("unknown managed profile name") from error
    role_config = config.roles[role]
    return (
        MANAGED_MARKER
        + 'name = "{0}"\n'.format(profile_name)
        + 'description = "{0}"\n'.format(description)
        + 'model = "{0}"\n'.format(role_config.model)
        + 'model_reasoning_effort = "{0}"\n'.format(role_config.reasoning_effort)
        + 'sandbox_mode = "{0}"\n'.format(sandbox_mode)
        + 'developer_instructions = """\n{0}\n"""\n'.format(instructions)
    )


def render_profiles(config: EffectiveConfig) -> Mapping[str, bytes]:
    """Render all and only the four LaneOrchestrator profile files."""

    return {
        name: render_profile(name, config).encode("utf-8") for name in PROFILE_NAMES
    }


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileConflict("receipt contains a duplicate JSON key")
        result[key] = value
    return result


def _validate_root(path: Path, label: str, *, owned_agents: bool = False) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ProfileConflict("{0} must be an absolute private directory".format(label))
    try:
        descriptor = (
            open_owned_directory_nofollow(candidate)
            if owned_agents
            else open_parent_directory_nofollow(candidate)
        )
    except SecurityError as error:
        raise ProfileConflict("{0} is unsafe: {1}".format(label, error)) from error
    else:
        os.close(descriptor)
    return candidate


def _root_device(path: Path, *, owned_agents: bool = False) -> int:
    descriptor = (
        open_owned_directory_nofollow(Path(path))
        if owned_agents
        else open_parent_directory_nofollow(Path(path))
    )
    try:
        return os.fstat(descriptor).st_dev
    finally:
        os.close(descriptor)


def _validate_environment(agents_root: Path, state_root: Path) -> Tuple[Path, Path]:
    supported, reason = platform_mutation_supported()
    if not supported:
        raise ProfileConflict(reason)
    agents = _validate_root(agents_root, "agents root", owned_agents=True)
    state = _validate_root(state_root, "state root")
    try:
        agents_device = _root_device(agents, owned_agents=True)
        state_device = _root_device(state)
    except SecurityError as error:
        raise ProfileConflict("could not validate profile root devices") from error
    if agents_device != state_device:
        raise ProfileConflict("cross-device profile operations are refused")
    return agents, state


def _ensure_private_child(root: Path, name: str) -> Path:
    """Create or validate one exact private child directory under a safe root."""

    parent_fd = open_parent_directory_nofollow(root)
    lock_fd = -1
    try:
        lock_fd = open_private_lock_at(parent_fd)
        try:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
                metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as error:
                raise ProfileConflict("could not create private {0} directory".format(name)) from error
        except OSError as error:
            raise ProfileConflict("could not inspect private {0} directory".format(name)) from error
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ProfileConflict("private {0} directory is unsafe".format(name))
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        os.close(parent_fd)
    return root / name


def _read_at(
    parent_fd: int,
    name: str,
    max_bytes: int,
    required_mode: Optional[int] = None,
) -> Optional[bytes]:
    metadata = validate_destination_at(parent_fd, name)
    if metadata is None:
        return None
    if required_mode is not None and stat.S_IMODE(metadata.st_mode) != required_mode:
        raise SecurityError("destination mode must be {0:04o}".format(required_mode))
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise SecurityError("could not open destination safely") from error
    try:
        opened = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise SecurityError("destination changed while opening")
        content = b""
        while len(content) <= max_bytes:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - len(content)))
            if not chunk:
                break
            content += chunk
        if len(content) > max_bytes:
            raise SecurityError("destination exceeds maximum size")
        current = validate_destination_at(parent_fd, name)
        if current is None or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise SecurityError("destination changed while reading")
        return content
    finally:
        os.close(descriptor)


def _read_optional(
    root: Path,
    name: str,
    max_bytes: int,
    required_mode: Optional[int] = None,
) -> Optional[bytes]:
    parent_fd = open_parent_directory_nofollow(root)
    try:
        return _read_at(parent_fd, name, max_bytes, required_mode)
    finally:
        os.close(parent_fd)


def _read_existing_backup(
    state_root: Path, name: str
) -> Optional[bytes]:
    """Inspect an optional private backup without creating its directory."""

    backup_root = state_root / BACKUPS_DIRECTORY
    try:
        backup_root.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProfileConflict("could not inspect profile backup directory") from error
    try:
        return _read_optional(
            backup_root,
            name,
            MAX_PROFILE_BYTES,
            required_mode=0o600,
        )
    except (OSError, SecurityError) as error:
        raise ProfileConflict("existing profile backup is unsafe") from error


@contextmanager
def _locked_roots(
    roots: Sequence[Path], *, agents_root: Optional[Path] = None
) -> Iterator[Mapping[Path, int]]:
    """Lock distinct private roots in lexical order to prevent deadlocks."""

    unique = sorted({Path(root) for root in roots}, key=lambda item: os.fspath(item))
    descriptors: Dict[Path, int] = {}
    locks: List[int] = []
    try:
        for root in unique:
            owned_agents = agents_root is not None and root == agents_root
            descriptor = (
                open_owned_directory_nofollow(root)
                if owned_agents
                else open_parent_directory_nofollow(root)
            )
            descriptors[root] = descriptor
            locks.append(
                open_owned_lock_at(descriptor)
                if owned_agents
                else open_private_lock_at(descriptor)
            )
        yield descriptors
    finally:
        for lock in reversed(locks):
            close_private_lock(lock)
        for descriptor in reversed(list(descriptors.values())):
            os.close(descriptor)


def _write_at_locked(parent_fd: int, name: str, content: bytes) -> None:
    inspected = validate_destination_at(parent_fd, name)
    temporary = private_temporary_name(name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = -1
    created = False
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        created = True
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise SecurityError("private temporary object is unsafe")
        os.fchmod(descriptor, 0o600)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        current = validate_destination_at(parent_fd, name)
        same = (
            inspected is None
            and current is None
            or inspected is not None
            and current is not None
            and (inspected.st_dev, inspected.st_ino) == (current.st_dev, current.st_ino)
        )
        if not same:
            raise SecurityError("destination changed before replacement")
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        created = False
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            try:
                metadata = validate_destination_at(parent_fd, temporary)
                if metadata is not None:
                    os.unlink(temporary, dir_fd=parent_fd)
                    os.fsync(parent_fd)
            except (OSError, SecurityError):
                pass


def _delete_at_locked(parent_fd: int, name: str) -> None:
    if validate_destination_at(parent_fd, name) is None:
        return
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _load_receipt(content: Optional[bytes], agents_root: Path) -> Optional[Mapping[str, object]]:
    if content is None:
        return None
    try:
        validate_json_nesting(content)
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except PlanError as error:
        raise ProfileConflict("receipt JSON nesting is unsafe") from error
    except ProfileConflict:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise ProfileConflict("receipt is malformed") from error
    if not isinstance(value, dict) or frozenset(value) != _RECEIPT_KEYS:
        raise ProfileConflict("receipt schema is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ProfileConflict("receipt schema version is unsupported")
    entries = value["profiles"]
    if not isinstance(entries, list) or len(entries) != len(PROFILE_NAMES):
        raise ProfileConflict("receipt profile list is invalid")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or frozenset(entry) != _RECEIPT_ENTRY_KEYS:
            raise ProfileConflict("receipt profile schema is invalid")
        name = entry["name"]
        if not isinstance(name, str) or name not in PROFILE_NAMES or name in seen:
            raise ProfileConflict("receipt profile name is invalid")
        seen.add(name)
        if not isinstance(entry["destination"], str) or entry["destination"] != os.fspath(agents_root / name):
            raise ProfileConflict("receipt destination does not match the requested agents root")
        if not isinstance(entry["template_version"], str) or entry["template_version"] != TEMPLATE_VERSION:
            raise ProfileConflict("receipt template version is unsupported")
        for key in ("content_sha256", "config_sha256"):
            if not isinstance(entry[key], str) or _HASH_RE.fullmatch(entry[key]) is None:
                raise ProfileConflict("receipt hash is invalid")
        backup_hash = entry["prior_backup_sha256"]
        if backup_hash is not None and (
            not isinstance(backup_hash, str) or _HASH_RE.fullmatch(backup_hash) is None
        ):
            raise ProfileConflict("receipt backup hash is invalid")
        if not isinstance(entry["operation"], str) or entry["operation"] not in _ACTIONS:
            raise ProfileConflict("receipt operation is invalid")
    if seen != set(PROFILE_NAMES):
        raise ProfileConflict("receipt profile set is incomplete")
    config_hashes = {entry["config_sha256"] for entry in entries}
    if len(config_hashes) != 1:
        raise ProfileConflict("receipt configuration hashes are inconsistent")
    return value


def _receipt_entries(receipt: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    entries = receipt["profiles"]
    assert isinstance(entries, list)
    return {entry["name"]: entry for entry in entries}  # type: ignore[index, misc]


def _read_snapshot(
    agents_root: Path, state_root: Path
) -> Tuple[
    Mapping[str, Optional[bytes]],
    Optional[bytes],
    Optional[bytes],
    str,
    str,
]:
    try:
        with _locked_roots(
            (agents_root, state_root), agents_root=agents_root
        ) as descriptors:
            agents_fd = descriptors[agents_root]
            state_fd = descriptors[state_root]
            profiles = {
                name: _read_at(agents_fd, name, MAX_PROFILE_BYTES)
                for name in PROFILE_NAMES
            }
            receipt = _read_at(
                state_fd, RECEIPT_NAME, MAX_RECEIPT_BYTES, required_mode=0o600
            )
            config = _read_at(state_fd, "config.json", MAX_CONFIG_BYTES)
            return (
                profiles,
                receipt,
                config,
                _identity_hash(os.fstat(agents_fd)),
                _identity_hash(os.fstat(state_fd)),
            )
    except (OSError, SecurityError) as error:
        raise ProfileConflict("profile state is unsafe: {0}".format(error)) from error


def _active_receipt(receipt: Optional[Mapping[str, object]]) -> bool:
    if receipt is None:
        return False
    return all(
        entry["operation"] in _ACTIVE_OPERATIONS
        for entry in _receipt_entries(receipt).values()
    )


def _require_private_managed_profile_modes(agents_root: Path) -> None:
    try:
        with _locked_roots((agents_root,), agents_root=agents_root) as descriptors:
            for name in PROFILE_NAMES:
                _read_at(
                    descriptors[agents_root],
                    name,
                    MAX_PROFILE_BYTES,
                    required_mode=0o600,
                )
    except (OSError, SecurityError) as error:
        raise ProfileConflict("managed profile permissions are unsafe") from error


def _verify_receipt_matches(
    receipt: Optional[Mapping[str, object]],
    profiles: Mapping[str, Optional[bytes]],
) -> Mapping[str, Mapping[str, object]]:
    if receipt is None or not _active_receipt(receipt):
        raise ProfileConflict("an active receipt is required")
    entries = _receipt_entries(receipt)
    for name in PROFILE_NAMES:
        content = profiles[name]
        if content is None or _sha256(content) != entries[name]["content_sha256"]:
            raise ProfileConflict("managed profile does not match its receipt")
    return entries


def _receipt_content(
    action: str,
    agents_root: Path,
    config_hash: str,
    rendered: Mapping[str, bytes],
    prior_entries: Optional[Mapping[str, Mapping[str, object]]] = None,
    prior_profiles: Optional[Mapping[str, Optional[bytes]]] = None,
) -> bytes:
    entries = []
    for name in PROFILE_NAMES:
        prior = None if prior_profiles is None else prior_profiles[name]
        changed = prior is not None and _sha256(prior) != _sha256(rendered[name])
        backup_hash = _sha256(prior) if action == "update" and changed and prior is not None else None
        if action == "uninstall" and prior_entries is not None:
            content_hash = prior_entries[name]["content_sha256"]
            entry_config_hash = prior_entries[name]["config_sha256"]
            backup_hash = prior_entries[name]["prior_backup_sha256"]
        else:
            content_hash = _sha256(rendered[name])
            entry_config_hash = config_hash
        entries.append(
            {
                "name": name,
                "destination": os.fspath(agents_root / name),
                "template_version": TEMPLATE_VERSION,
                "content_sha256": content_hash,
                "config_sha256": entry_config_hash,
                "prior_backup_sha256": backup_hash,
                "operation": action,
            }
        )
    return _canonical_json({"schema_version": RECEIPT_SCHEMA_VERSION, "profiles": entries})


def _operation(path: Path, before: Optional[bytes], after: Optional[bytes]) -> Operation:
    return Operation(
        path=os.fspath(path),
        before_sha256=None if before is None else _sha256(before),
        after_sha256=None if after is None else _sha256(after),
        content_b64=None if after is None else base64.b64encode(after).decode("ascii"),
    )


def _observation(path: Path, digest: Optional[str]) -> Operation:
    return Operation(
        path=os.fspath(path),
        before_sha256=digest,
        after_sha256=digest,
        content_b64=None,
    )


def _config_observation(
    path: Path, raw_digest: Optional[str], effective_digest: str
) -> Operation:
    return Operation(
        path=os.fspath(path),
        before_sha256=raw_digest,
        after_sha256=effective_digest,
        content_b64=None,
    )


def _identity_hash(metadata: os.stat_result) -> str:
    identity = "{0}:{1}:{2}:{3}".format(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
    ).encode("ascii")
    return _sha256(identity)


def is_adoptable_profile(name: str, content: Optional[bytes]) -> bool:
    """Return whether bytes are an exact historical default eligible for adoption."""

    if name not in PROFILE_NAMES:
        return False
    if content is None:
        return False
    marker = MANAGED_MARKER.encode("utf-8")
    candidate = content[len(marker) :] if content.startswith(marker) else content
    return _sha256(candidate) == _V010_HASHES[name]


def _build_preview(
    action: str,
    config: EffectiveConfig,
    agents_root: Path,
    state_root: Path,
) -> Tuple[Sequence[Operation], int]:
    rendered = render_profiles(config)
    (
        profiles,
        receipt_bytes,
        config_bytes,
        agents_identity,
        state_identity,
    ) = _read_snapshot(agents_root, state_root)
    receipt = _load_receipt(receipt_bytes, agents_root)
    if _active_receipt(receipt):
        _require_private_managed_profile_modes(agents_root)
    config_hash = _sha256(serialize_config(config))
    operations: List[Operation] = [
        _observation(agents_root, agents_identity),
        _observation(state_root, state_identity),
        _config_observation(
            state_root / "config.json",
            None if config_bytes is None else _sha256(config_bytes),
            config_hash,
        ),
        _observation(
            state_root / RECEIPT_NAME,
            None if receipt_bytes is None else _sha256(receipt_bytes),
        ),
    ] + [
        _observation(
            agents_root / name,
            None if profiles[name] is None else _sha256(profiles[name]),
        )
        for name in PROFILE_NAMES
    ]

    def replace_receipt_observation(content: bytes) -> None:
        operations[3] = _operation(
            state_root / RECEIPT_NAME, receipt_bytes, content
        )

    def replace_profile_observation(
        name: str, before: Optional[bytes], after: Optional[bytes]
    ) -> None:
        operations[4 + PROFILE_NAMES.index(name)] = _operation(
            agents_root / name, before, after
        )

    if action == "install":
        if _active_receipt(receipt):
            entries = _verify_receipt_matches(receipt, profiles)
            if all(
                _sha256(rendered[name]) == entries[name]["content_sha256"]
                and entries[name]["config_sha256"] == config_hash
                for name in PROFILE_NAMES
            ):
                return tuple(operations), 0
            raise ProfileConflict("profiles are already managed; use update")
        if any(profiles[name] is not None for name in PROFILE_NAMES):
            raise ProfileConflict("unmanaged profile collision; use adopt only for exact v0.1.0 files")
        for name in PROFILE_NAMES:
            replace_profile_observation(name, None, rendered[name])
        new_receipt = _receipt_content(action, agents_root, config_hash, rendered)
        replace_receipt_observation(new_receipt)
        return operations, len(PROFILE_NAMES)

    if action == "adopt":
        if receipt is not None and _active_receipt(receipt):
            raise ProfileConflict("profiles already have an active receipt")
        for name in PROFILE_NAMES:
            if not is_adoptable_profile(name, profiles[name]):
                raise ProfileConflict("adoption requires an exact v0.1.0 bundled profile match")
            replace_profile_observation(name, profiles[name], rendered[name])
        new_receipt = _receipt_content(action, agents_root, config_hash, rendered)
        replace_receipt_observation(new_receipt)
        return operations, len(PROFILE_NAMES)

    entries = _verify_receipt_matches(receipt, profiles)
    if action == "update":
        changed = 0
        for name in PROFILE_NAMES:
            prior = profiles[name]
            assert prior is not None
            if prior == rendered[name]:
                continue
            changed += 1
            backup_hash = _sha256(prior)
            backup_path = state_root / BACKUPS_DIRECTORY / (
                name + "." + backup_hash + ".bak"
            )
            existing_backup = _read_existing_backup(
                state_root, backup_path.name
            )
            if existing_backup is None:
                operations.append(_operation(backup_path, None, prior))
            elif existing_backup == prior:
                operations.append(_observation(backup_path, backup_hash))
            else:
                raise ProfileConflict("existing profile backup does not match its hash")
            replace_profile_observation(name, prior, rendered[name])
        if changed == 0:
            if any(entry["config_sha256"] != config_hash for entry in entries.values()):
                raise ProfileConflict("receipt configuration hash does not match current configuration")
            return tuple(operations), 0
        new_receipt = _receipt_content(
            action,
            agents_root,
            config_hash,
            rendered,
            prior_entries=entries,
            prior_profiles=profiles,
        )
        replace_receipt_observation(new_receipt)
        return operations, changed

    assert action == "uninstall"
    for name in PROFILE_NAMES:
        replace_profile_observation(name, profiles[name], None)
    new_receipt = _receipt_content(
        action,
        agents_root,
        config_hash,
        rendered,
        prior_entries=entries,
        prior_profiles=profiles,
    )
    replace_receipt_observation(new_receipt)
    return operations, len(PROFILE_NAMES)


def preview_profiles(
    action: str,
    config: EffectiveConfig,
    agents_root: Path,
    state_root: Path,
    now: Optional[int] = None,
) -> Tuple[str, CommandResult]:
    """Create a ten-minute exact-state plan for a managed profile action."""

    if action not in _ACTIONS:
        raise ValueError("profile action must be install, adopt, update, or uninstall")
    _validate_config(config)
    agents, state = _validate_environment(agents_root, state_root)
    operations, change_count = _build_preview(action, config, agents, state)
    plans_root = _ensure_private_child(state, PLANS_DIRECTORY)
    try:
        token = create_plan("profiles.{0}".format(action), operations, plans_root, now=now)
    except (PlanError, SecurityError) as error:
        raise ProfileConflict("could not create profile preview: {0}".format(error)) from error
    return token, command_result(
        "profiles",
        data={
            "action": action,
            "change_count": change_count,
            "expires_in_seconds": 600,
            "approval_digest": approval_digest(load_plan(token, "profiles.{0}".format(action), plans_root, now=now)),
            "phase": "preview",
            "profiles": list(PROFILE_NAMES),
            "token": token,
        },
    )


def _decode_operation_content(operation: Operation) -> Optional[bytes]:
    if operation.content_b64 is None:
        return None
    return base64.b64decode(operation.content_b64.encode("ascii"), validate=True)


def _classify_operations(
    plan: MutationPlan, action: str, agents_root: Path, state_root: Path
) -> Mapping[str, Tuple[str, Path, str, Operation]]:
    classified: Dict[str, Tuple[str, Path, str, Operation]] = {}
    for operation in plan.operations:
        path = Path(operation.path)
        if not path.is_absolute() or os.fspath(path) != operation.path:
            raise ProfileConflict("profile plan path is not canonical and absolute")
        if operation.path in classified:
            raise ProfileConflict("profile plan contains a duplicate destination")
        if path == agents_root:
            kind = "root"
            root = agents_root
            name = ""
        elif path == state_root:
            kind = "root"
            root = state_root
            name = ""
        elif path == state_root / "config.json":
            kind = "observe"
            root = state_root
            name = "config.json"
        elif path.parent == agents_root and path.name in PROFILE_NAMES:
            kind = (
                "observe"
                if operation.content_b64 is None
                and operation.before_sha256 == operation.after_sha256
                else "mutate"
            )
            root = agents_root
            name = path.name
        elif path == state_root / RECEIPT_NAME:
            kind = (
                "observe"
                if operation.content_b64 is None
                and operation.before_sha256 == operation.after_sha256
                else "mutate"
            )
            root = state_root
            name = path.name
        elif path.parent == state_root / BACKUPS_DIRECTORY:
            matched_backup = None
            for profile_name in PROFILE_NAMES:
                prefix = profile_name + "."
                if path.name.startswith(prefix) and path.name.endswith(".bak"):
                    digest = path.name[len(prefix) : -len(".bak")]
                    if _HASH_RE.fullmatch(digest) is not None:
                        matched_backup = digest
                        break
            if action != "update" or matched_backup is None:
                raise ProfileConflict("profile plan contains an unexpected backup path")
            kind = (
                "observe"
                if operation.content_b64 is None
                and operation.before_sha256 == operation.after_sha256
                else "mutate"
            )
            root = state_root / BACKUPS_DIRECTORY
            name = path.name
            expected_backup_hash = (
                operation.after_sha256
                if kind == "mutate"
                else operation.before_sha256
            )
            if expected_backup_hash != matched_backup:
                raise ProfileConflict("profile backup path does not match its content hash")
        else:
            raise ProfileConflict("profile plan contains an unexpected destination")
        is_config_observation = path == state_root / "config.json"
        if kind in ("root", "observe") and (
            (operation.before_sha256 != operation.after_sha256 and not is_config_observation)
            or operation.content_b64 is not None
            or is_config_observation
            and operation.after_sha256 is None
        ):
            raise ProfileConflict("profile plan observation is not read-only")
        classified[operation.path] = (kind, root, name, operation)
    required_observations = {
        os.fspath(agents_root),
        os.fspath(state_root),
        os.fspath(state_root / "config.json"),
    }
    if not required_observations.issubset(classified):
        raise ProfileConflict("profile plan is missing a root or configuration binding")
    has_mutation = any(item[0] == "mutate" for item in classified.values())
    receipt_item = classified.get(os.fspath(state_root / RECEIPT_NAME))
    if has_mutation and (receipt_item is None or receipt_item[0] != "mutate"):
        raise ProfileConflict("profile plan does not include its receipt")

    all_profile_items = {
        Path(key).name: item
        for key, item in classified.items()
        if item[1] == agents_root and Path(key) != agents_root
    }
    if set(all_profile_items) != set(PROFILE_NAMES):
        raise ProfileConflict("profile plan does not bind every managed profile")
    profile_items = {
        Path(key).name: item
        for key, item in classified.items()
        if item[0] == "mutate" and item[1] == agents_root
    }
    if (
        has_mutation
        and action in ("install", "adopt", "uninstall")
        and set(profile_items) != set(PROFILE_NAMES)
    ):
        raise ProfileConflict("profile plan has an incomplete action vocabulary")
    for name, (_kind, _root, _basename, operation) in profile_items.items():
        after = _decode_operation_content(operation)
        if action == "install" and (operation.before_sha256 is not None or after is None):
            raise ProfileConflict("install plan operation is invalid")
        if action in ("adopt", "update") and (
            operation.before_sha256 is None or after is None
        ):
            raise ProfileConflict("profile replacement operation is invalid")
        if action == "uninstall" and (
            operation.before_sha256 is None or after is not None
        ):
            raise ProfileConflict("profile uninstall operation is invalid")
    if action == "update" and receipt_item is not None and receipt_item[0] == "mutate" and not profile_items:
        raise ProfileConflict("update plan has no profile changes")

    if receipt_item is not None and receipt_item[0] == "mutate":
        receipt_after = _decode_operation_content(receipt_item[3])
        if receipt_after is None:
            raise ProfileConflict("profile receipt mutation must publish content")
        receipt_document = _load_receipt(receipt_after, agents_root)
        assert receipt_document is not None
        receipt_entries = _receipt_entries(receipt_document)
        config_item = classified[os.fspath(state_root / "config.json")][3]
        for name, (_kind, _root, _basename, operation) in all_profile_items.items():
            intended_content = _decode_operation_content(operation)
            intended_hash = (
                operation.before_sha256
                if action == "uninstall" or intended_content is None
                else _sha256(intended_content)
            )
            if receipt_entries[name]["operation"] != action:
                raise ProfileConflict("profile receipt operation does not match the plan")
            if receipt_entries[name]["content_sha256"] != intended_hash:
                raise ProfileConflict("profile receipt hash does not match the plan")
            if action != "uninstall" and (
                receipt_entries[name]["config_sha256"]
                != config_item.after_sha256
            ):
                raise ProfileConflict("profile receipt configuration does not match the plan")
    return classified


def _apply_plan(
    plan: MutationPlan,
    action: str,
    agents_root: Path,
    state_root: Path,
) -> CommandResult:
    classified = _classify_operations(plan, action, agents_root, state_root)
    backup_root = state_root / BACKUPS_DIRECTORY
    if any(
        kind == "mutate" and root == backup_root
        for kind, root, _name, _operation_item in classified.values()
    ):
        _ensure_private_child(state_root, BACKUPS_DIRECTORY)
    roots = sorted(
        {root for _kind, root, _name, _operation_item in classified.values()},
        key=os.fspath,
    )
    before_contents: Dict[str, Optional[bytes]] = {}
    applied: List[str] = []
    try:
        with _locked_roots(roots, agents_root=agents_root) as descriptors:
            try:
                for key, (kind, root, name, operation) in classified.items():
                    if kind == "root":
                        content = None
                        digest = _identity_hash(os.fstat(descriptors[root]))
                    else:
                        required_mode = None
                        if operation.before_sha256 is not None and (
                            root == backup_root
                            or root == state_root and name == RECEIPT_NAME
                            or root == agents_root and action != "adopt"
                        ):
                            required_mode = 0o600
                        content = _read_at(
                            descriptors[root],
                            name,
                            MAX_CONFIG_BYTES
                            if kind == "observe"
                            else MAX_RECEIPT_BYTES
                            if root == state_root
                            else MAX_PROFILE_BYTES,
                            required_mode=required_mode,
                        )
                        digest = None if content is None else _sha256(content)
                    before_contents[key] = content
                    if digest != operation.before_sha256:
                        raise ProfileConflict("profile state changed after preview")

                for key, (kind, root, name, operation) in classified.items():
                    if kind != "mutate":
                        continue
                    after = _decode_operation_content(operation)
                    # Journal before entering a primitive whose final fsync can
                    # fail after publication.
                    applied.append(key)
                    if after is None:
                        _delete_at_locked(descriptors[root], name)
                    else:
                        _write_at_locked(descriptors[root], name, after)
            except (ProfileConflict, OSError, SecurityError, ValueError) as error:
                # Preflight conflicts occur before mutation and need no rollback.
                if not applied and isinstance(error, ProfileConflict):
                    raise
                rollback_errors = []
                for key in reversed(applied):
                    _kind, root, name, _operation = classified[key]
                    prior = before_contents[key]
                    try:
                        if prior is None:
                            _delete_at_locked(descriptors[root], name)
                        else:
                            _write_at_locked(descriptors[root], name, prior)
                    except (OSError, SecurityError) as rollback_error:
                        rollback_errors.append(str(rollback_error))
                if rollback_errors:
                    raise ProfileConflict(
                        "profile apply failed and rollback was incomplete: {0}".format(
                            "; ".join(rollback_errors)
                        )
                    ) from error
                raise ProfileConflict(
                    "profile apply failed safely: {0}".format(error)
                ) from error
    except ProfileConflict:
        raise
    except (OSError, SecurityError, ValueError) as error:
        raise ProfileConflict("profile apply failed safely: {0}".format(error)) from error

    profile_changes = sum(
        1
        for kind, root, _name, _operation_item in classified.values()
        if kind == "mutate" and root == agents_root
    )
    return command_result(
        "profiles",
        data={
            "action": action,
            "change_count": profile_changes,
            "phase": "apply",
            "profiles": list(PROFILE_NAMES),
        },
    )


def apply_profiles(
    action: str,
    token: str,
    agents_root: Path,
    state_root: Path,
    approval: Optional[str] = None,
    now: Optional[int] = None,
) -> CommandResult:
    """Consume and apply one exact profile preview token."""

    if action not in _ACTIONS:
        raise ValueError("profile action must be install, adopt, update, or uninstall")
    agents, state = _validate_environment(agents_root, state_root)
    plans_root = state / PLANS_DIRECTORY
    try:
        return consume_plan(
            token,
            "profiles.{0}".format(action),
            plans_root,
            lambda plan: _apply_plan(plan, action, agents, state),
            approval=approval,
            now=now,
        )
    except ProfileConflict:
        raise
    except (PlanError, SecurityError) as error:
        raise ProfileConflict("profile plan could not be applied: {0}".format(error)) from error


def inspect_profiles(
    config: EffectiveConfig, agents_root: Path, state_root: Path
) -> Mapping[str, str]:
    """Return exact managed-profile status without creating a preview token."""

    _validate_config(config)
    agents, state = _validate_environment(agents_root, state_root)
    rendered = render_profiles(config)
    profiles, receipt_bytes, _config_bytes, _agents_identity, _state_identity = (
        _read_snapshot(agents, state)
    )
    receipt = _load_receipt(receipt_bytes, agents)
    statuses: Dict[str, str] = {}
    entries = _receipt_entries(receipt) if receipt is not None and _active_receipt(receipt) else {}
    expected_config_hash = _sha256(serialize_config(config))
    config_drift = bool(entries) and any(
        entry["config_sha256"] != expected_config_hash
        for entry in entries.values()
    )
    for name in PROFILE_NAMES:
        content = profiles[name]
        try:
            metadata = os.lstat(agents / name)
            private_mode = stat.S_IMODE(metadata.st_mode) == 0o600
        except FileNotFoundError:
            private_mode = False
        except OSError:
            private_mode = False
        if content is None:
            statuses[name] = "missing"
        elif (
            not config_drift
            and private_mode
            and name in entries
            and _sha256(content) == entries[name]["content_sha256"]
        ):
            statuses[name] = "unchanged" if content == rendered[name] else "managed"
        else:
            statuses[name] = "conflict"
    return statuses
