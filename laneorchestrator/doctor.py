"""Read-only, truthful environment diagnostics and status summaries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .config import (
    DEFAULT_ROLES,
    MAX_CONFIG_BYTES,
    ConfigError,
    parse_config_bytes,
    serialize_config,
    validate_config_payload,
)
from .diagnostics import CommandResult, Diagnostic, Level, command_result
from .models import Availability, EffectiveConfig, LOGICAL_ROLES, RoleEvidence
from .profiles import (
    MAX_PROFILE_BYTES,
    MAX_RECEIPT_BYTES,
    PROFILE_NAMES,
    RECEIPT_SCHEMA_VERSION,
    TEMPLATE_VERSION,
    render_profiles,
)
from .security import SecurityError, read_regular_nofollow


CODEX_TIMEOUT_SECONDS = 5.0
MAX_CODEX_OUTPUT_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
_VERSION_RE = re.compile(r"\bcodex(?:-cli)?\s+(\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?)\b", re.IGNORECASE)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_OPERATIONS = frozenset(("install", "adopt", "update"))
_OPERATIONS = frozenset(("install", "adopt", "update", "uninstall"))
_ROLE_PROFILE = {
    "router": "laneorchestrator-router.toml",
    "small_task_executor": "laneorchestrator-luna-executor.toml",
    "main_implementer": "laneorchestrator-terra-executor.toml",
    "independent_reviewer": "laneorchestrator-sol-reviewer.toml",
}


class _InspectionError(ValueError):
    """A bounded read-only inspection could not establish safe evidence."""


def _safe_text(value: object, limit: int = 256) -> str:
    text = str(value)
    cleaned = "".join(character if 32 <= ord(character) < 127 else "?" for character in text)
    return cleaned[:limit]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _root_state(path: Path, kind: str) -> Tuple[bool, str]:
    """Inspect an absolute root chain without following a symbolic link."""

    candidate = Path(path)
    if not candidate.is_absolute():
        return False, "relative"
    parts = candidate.parts
    if any(component in ("", ".", "..") for component in parts[1:]):
        return False, "unsafe_component"
    current = Path(parts[0])
    for index, component in enumerate(parts[1:], 1):
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return True, "absent"
        except OSError:
            return False, "uninspectable"
        if _is_link_or_reparse(metadata):
            return False, "symlink"
        if not stat.S_ISDIR(metadata.st_mode):
            return False, "not_directory"
        final = index == len(parts) - 1
        if not final:
            writable = metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            if writable and not metadata.st_mode & stat.S_ISVTX:
                return False, "unsafe_ancestor_mode"
    try:
        metadata = candidate.lstat()
    except (FileNotFoundError, OSError):
        return True, "absent"
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        return False, "wrong_owner"
    mode = stat.S_IMODE(metadata.st_mode)
    if kind == "state" and os.name == "posix" and mode != 0o700:
        return False, "unsafe_mode"
    if kind == "agents" and os.name == "posix" and mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False, "unsafe_mode"
    return True, "present"


def _dir_fd_read_supported() -> bool:
    return (
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
    )


def _read_child_portable(
    root: Path,
    name: str,
    max_bytes: int,
    required_mode: Optional[int],
) -> Tuple[str, Optional[bytes]]:
    """Portable identity-checked read for hosts without dir-fd support."""

    candidate = Path(root) / name
    try:
        before = candidate.lstat()
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unsafe", None
    if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        return "unsafe", None
    if before.st_nlink != 1:
        return "unsafe", None
    if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
        return "unsafe", None
    if required_mode is not None and os.name == "posix" and stat.S_IMODE(before.st_mode) != required_mode:
        return "bad_mode", None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError:
        return "unsafe", None
    try:
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            return "unsafe", None
        chunks: List[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(8192, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            return "oversized", None
        try:
            after = candidate.lstat()
        except OSError:
            return "unsafe", None
        if _is_link_or_reparse(after) or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino):
            return "unsafe", None
        return "present", b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_child(
    root: Path,
    name: str,
    max_bytes: int,
    required_mode: Optional[int] = None,
) -> Tuple[str, Optional[bytes]]:
    """Read one direct child through a held no-follow root descriptor."""

    safe, root_status = _root_state(root, "state" if name in ("config.json", "receipts.json") else "agents")
    if not safe:
        return "unsafe", None
    if root_status == "absent":
        return "missing", None
    if not _dir_fd_read_supported():
        return _read_child_portable(root, name, max_bytes, required_mode)
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        root_fd = os.open(root, flags)
    except OSError:
        return "unsafe", None
    descriptor = -1
    try:
        try:
            metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return "missing", None
        except (OSError, TypeError):
            return "unsafe", None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return "unsafe", None
        if metadata.st_nlink != 1:
            return "unsafe", None
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            return "unsafe", None
        if required_mode is not None and os.name == "posix" and stat.S_IMODE(metadata.st_mode) != required_mode:
            return "bad_mode", None
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(name, file_flags, dir_fd=root_fd)
        except OSError:
            return "unsafe", None
        opened = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            return "unsafe", None
        chunks: List[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(8192, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            return "oversized", None
        try:
            current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except OSError:
            return "unsafe", None
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            return "unsafe", None
        return "present", b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(root_fd)


def _strict_json(content: bytes) -> object:
    def pairs(items: Sequence[Tuple[str, object]]) -> Mapping[str, object]:
        result: Dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise _InspectionError("duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=pairs)
    except (_InspectionError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _InspectionError("invalid JSON") from error


def check_python_and_platform() -> Sequence[Diagnostic]:
    version = tuple(sys.version_info[:3])
    python_level = Level.PASS if version >= (3, 9, 0) else Level.FAIL
    python_message = "Python version is supported" if python_level is Level.PASS else "Python 3.9 or newer is required"
    if os.name == "posix":
        platform_level = Level.PASS
        platform_message = "POSIX read-only and mutation primitives are supported"
    elif os.name == "nt":
        platform_level = Level.WARN
        platform_message = "Read-only commands are usable; native Windows profile mutation is unsupported"
    else:
        platform_level = Level.WARN
        platform_message = "Read-only commands are usable; profile mutation support is unverified"
    return (
        Diagnostic("PYTHON_VERSION", python_level, python_message, {"version": ".".join(str(item) for item in version)}),
        Diagnostic("PLATFORM_SUPPORT", platform_level, platform_message, {"os_name": _safe_text(os.name, 32), "platform": _safe_text(sys.platform, 64)}),
    )


def _codex_executable(environment: Mapping[str, str]) -> Tuple[Optional[Path], str]:
    path_value = environment.get("PATH", "")
    if not isinstance(path_value, str) or not path_value:
        return None, "missing"
    entries = path_value.split(os.pathsep)
    if any(not entry or not Path(entry).is_absolute() for entry in entries):
        return None, "unsafe_path"
    for entry in entries:
        candidate = Path(entry) / ("codex.exe" if os.name == "nt" else "codex")
        try:
            metadata = candidate.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            return None, "unsafe_executable"
        if stat.S_ISREG(metadata.st_mode) and os.access(candidate, os.X_OK):
            return candidate, "found"
    return None, "missing"


def _kill_probe(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass
    if process.stdout is not None:
        try:
            process.stdout.close()
        except OSError:
            pass
    try:
        process.wait(timeout=0.2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _probe_codex(executable: Path, environment: Mapping[str, str]) -> Tuple[str, bytes, Optional[int]]:
    started = time.monotonic()
    deadline = started + CODEX_TIMEOUT_SECONDS - 0.25
    try:
        process = subprocess.Popen(
            [os.fspath(executable), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            env=dict(environment),
            start_new_session=os.name == "posix",
        )
    except OSError:
        return "execution_error", b"", None
    assert process.stdout is not None
    output = bytearray()
    selector: Optional[selectors.BaseSelector] = None
    completed_normally = False
    try:
        try:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
        except (OSError, ValueError):
            _kill_probe(process)
            return "execution_error", b"", None
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_probe(process)
                return "timeout", bytes(output), None
            try:
                events = selector.select(min(0.05, remaining))
            except (OSError, ValueError):
                _kill_probe(process)
                return "execution_error", bytes(output), None
            for key, _mask in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), min(8192, MAX_CODEX_OUTPUT_BYTES + 1 - len(output)))
                except OSError:
                    chunk = b""
                if not chunk:
                    eof = True
                    break
                output.extend(chunk)
                if len(output) > MAX_CODEX_OUTPUT_BYTES:
                    _kill_probe(process)
                    return "output_limit", bytes(output[:MAX_CODEX_OUTPUT_BYTES]), None
            if process.poll() is not None and not events:
                # The main process exited. A descendant retaining the pipe is
                # not allowed to extend this bounded probe.
                _kill_probe(process)
                return "descendant_pipe", bytes(output), None
        remaining = max(0.01, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _kill_probe(process)
            return "timeout", bytes(output), None
        completed_normally = True
        return "completed", bytes(output), returncode
    finally:
        if selector is not None:
            selector.close()
        if not completed_normally:
            _kill_probe(process)
        elif process.stdout is not None:
            process.stdout.close()


def check_codex_cli(env: Optional[Mapping[str, str]] = None) -> Diagnostic:
    supplied = os.environ if env is None else env
    if not isinstance(supplied, Mapping) or any(
        not isinstance(key, str)
        or not key
        or "=" in key
        or "\x00" in key
        or not isinstance(value, str)
        or "\x00" in value
        for key, value in supplied.items()
    ):
        return Diagnostic("CODEX_CLI", Level.FAIL, "Codex CLI environment is invalid", {"probe": "invalid_environment"})
    environment = dict(supplied)
    executable, state = _codex_executable(environment)
    if executable is None:
        message = "Codex CLI search path or executable is unsafe" if state in ("unsafe_path", "unsafe_executable") else "Codex CLI was not found"
        return Diagnostic("CODEX_CLI", Level.FAIL, message, {"probe": state})
    outcome, output, returncode = _probe_codex(executable, environment)
    if outcome != "completed":
        return Diagnostic("CODEX_CLI", Level.FAIL, "Codex CLI version probe failed safely", {"probe": outcome, "retained_bytes": len(output)})
    if returncode != 0:
        return Diagnostic("CODEX_CLI", Level.FAIL, "Codex CLI version probe returned a failure", {"probe": "nonzero_exit", "returncode": returncode})
    text = output.decode("utf-8", "replace")
    match = _VERSION_RE.search(text)
    if match is None:
        return Diagnostic("CODEX_CLI", Level.FAIL, "Codex CLI version output was malformed", {"probe": "malformed_version", "retained_bytes": len(output)})
    return Diagnostic("CODEX_CLI", Level.PASS, "Codex CLI version was directly verified", {"version": _safe_text(match.group(1), 64)})


def _read_repo_file(path: Path, max_bytes: int) -> bytes:
    try:
        return read_regular_nofollow(path, max_bytes)
    except (FileNotFoundError, OSError, SecurityError) as error:
        raise _InspectionError("repository file is missing or unsafe") from error


def check_manifests(repo_root: Path) -> Sequence[Diagnostic]:
    paths = (
        Path(repo_root) / ".codex-plugin" / "plugin.json",
        Path(repo_root) / "plugin.json",
        Path(repo_root) / ".agents" / "plugins" / "marketplace.json",
    )
    manifest_evidence: Dict[str, str] = {}
    valid = True
    for label, path in zip(("codex", "plugin", "marketplace"), paths):
        try:
            payload = _strict_json(_read_repo_file(path, MAX_MANIFEST_BYTES))
            if not isinstance(payload, Mapping) or payload.get("name") != "laneorchestrator":
                raise _InspectionError("manifest identity mismatch")
            if label != "marketplace" and payload.get("version") != TEMPLATE_VERSION:
                raise _InspectionError("manifest version mismatch")
            if label == "marketplace":
                plugins = payload.get("plugins")
                if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], Mapping) or plugins[0].get("name") != "laneorchestrator":
                    raise _InspectionError("marketplace entry mismatch")
            manifest_evidence[label] = "valid"
        except _InspectionError:
            manifest_evidence[label] = "invalid_or_missing"
            valid = False
    plugin = Diagnostic(
        "PLUGIN_MANIFEST",
        Level.PASS if valid else Level.FAIL,
        "Plugin manifests are internally consistent" if valid else "Plugin manifests are missing or inconsistent",
        {"manifests": manifest_evidence},
    )

    config = EffectiveConfig(1, DEFAULT_ROLES, "defaults")
    expected = render_profiles(config)
    bundled_evidence: Dict[str, str] = {}
    bundled_valid = True
    for name in PROFILE_NAMES:
        try:
            content = _read_repo_file(Path(repo_root) / "agents" / name, MAX_PROFILE_BYTES)
            status_value = "verified" if content == expected[name] else "drift"
        except _InspectionError:
            status_value = "missing_or_unsafe"
        bundled_evidence[name] = status_value
        bundled_valid = bundled_valid and status_value == "verified"
    bundled = Diagnostic(
        "BUNDLED_PROFILES",
        Level.PASS if bundled_valid else Level.FAIL,
        "Bundled profiles match canonical templates" if bundled_valid else "Bundled profiles are missing, unsafe, or drifted",
        {"profiles": bundled_evidence},
    )
    return plugin, bundled


def _load_config_readonly(state_root: Path) -> Tuple[Optional[EffectiveConfig], str]:
    safe, root_status = _root_state(state_root, "state")
    if not safe:
        return None, "unsafe_root"
    if root_status == "absent":
        return EffectiveConfig(1, DEFAULT_ROLES, "defaults"), "defaults"
    status_value, content = _read_child(state_root, "config.json", MAX_CONFIG_BYTES, required_mode=0o600)
    if status_value == "missing":
        return EffectiveConfig(1, DEFAULT_ROLES, "defaults"), "defaults"
    if status_value != "present" or content is None:
        return None, status_value
    try:
        return validate_config_payload(parse_config_bytes(content)), "file"
    except ConfigError:
        return None, "invalid"


def check_config_and_paths(state_root: Path, agents_root: Path) -> Sequence[Diagnostic]:
    config, config_status = _load_config_readonly(state_root)
    config_ok = config is not None
    config_diagnostic = Diagnostic(
        "CONFIG_SCHEMA",
        Level.PASS if config_ok else Level.FAIL,
        "Effective configuration is valid" if config_ok else "Configuration is malformed or unsafe",
        {"source": config.source if config is not None else "invalid", "inspection": config_status},
    )
    state_safe, state_status = _root_state(state_root, "state")
    agents_safe, agents_status = _root_state(agents_root, "agents")
    path_safe = state_safe and agents_safe
    path_diagnostic = Diagnostic(
        "STATE_PATH_SAFETY",
        Level.PASS if path_safe else Level.FAIL,
        "State and profile roots are safe for read-only inspection" if path_safe else "State or profile root is unsafe",
        {"state_root": state_status, "agents_root": agents_status},
    )
    return config_diagnostic, path_diagnostic


def _validate_receipt(content: bytes, agents_root: Path) -> Mapping[str, object]:
    payload = _strict_json(content)
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "profiles"}:
        raise _InspectionError("receipt schema")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise _InspectionError("receipt version")
    profiles = payload["profiles"]
    if not isinstance(profiles, list) or len(profiles) != len(PROFILE_NAMES):
        raise _InspectionError("receipt profile count")
    keys = {
        "name", "destination", "template_version", "content_sha256",
        "config_sha256", "prior_backup_sha256", "operation",
    }
    seen = set()
    for entry in profiles:
        if not isinstance(entry, Mapping) or set(entry) != keys:
            raise _InspectionError("receipt entry schema")
        name = entry["name"]
        if not isinstance(name, str) or name not in PROFILE_NAMES or name in seen:
            raise _InspectionError("receipt profile identity")
        seen.add(name)
        if entry["destination"] != os.fspath(agents_root / name):
            raise _InspectionError("receipt destination")
        if entry["template_version"] != TEMPLATE_VERSION:
            raise _InspectionError("receipt template")
        if not isinstance(entry["content_sha256"], str) or _HASH_RE.fullmatch(entry["content_sha256"]) is None:
            raise _InspectionError("receipt content hash")
        if not isinstance(entry["config_sha256"], str) or _HASH_RE.fullmatch(entry["config_sha256"]) is None:
            raise _InspectionError("receipt config hash")
        backup = entry["prior_backup_sha256"]
        if backup is not None and (not isinstance(backup, str) or _HASH_RE.fullmatch(backup) is None):
            raise _InspectionError("receipt backup hash")
        if not isinstance(entry["operation"], str) or entry["operation"] not in _OPERATIONS:
            raise _InspectionError("receipt operation")
    if seen != set(PROFILE_NAMES):
        raise _InspectionError("receipt profile set")
    if len({entry["config_sha256"] for entry in profiles}) != 1:
        raise _InspectionError("receipt config hashes")
    if len({entry["operation"] for entry in profiles}) != 1:
        raise _InspectionError("receipt operations")
    return payload


def _inspect_profiles_readonly(
    config: Optional[EffectiveConfig], state_root: Path, agents_root: Path
) -> Tuple[Mapping[str, str], Optional[Mapping[str, object]]]:
    profile_bytes: Dict[str, Optional[bytes]] = {}
    statuses: Dict[str, str] = {}
    for name in PROFILE_NAMES:
        status_value, content = _read_child(agents_root, name, MAX_PROFILE_BYTES, required_mode=0o600)
        profile_bytes[name] = content
        if status_value == "missing":
            statuses[name] = "missing"
        elif status_value == "bad_mode":
            statuses[name] = "bad_mode"
        elif status_value != "present":
            statuses[name] = "unsafe"

    receipt_status, receipt_content = _read_child(state_root, "receipts.json", MAX_RECEIPT_BYTES, required_mode=0o600)
    receipt: Optional[Mapping[str, object]] = None
    receipt_invalid = receipt_status not in ("missing", "present")
    if receipt_status == "present" and receipt_content is not None:
        try:
            receipt = _validate_receipt(receipt_content, agents_root)
        except _InspectionError:
            receipt_invalid = True
    if receipt_invalid:
        for name in PROFILE_NAMES:
            if statuses.get(name) not in ("missing", "bad_mode", "unsafe"):
                statuses[name] = "invalid_receipt"
        return statuses, None

    entries: Mapping[str, Mapping[str, object]] = {}
    active = False
    if receipt is not None:
        raw_entries = receipt["profiles"]
        assert isinstance(raw_entries, list)
        entries = {entry["name"]: entry for entry in raw_entries}  # type: ignore[index, misc]
        active = all(entry["operation"] in _ACTIVE_OPERATIONS for entry in raw_entries)
    expected = render_profiles(config) if config is not None else {}
    expected_config_hash = _sha256(serialize_config(config)) if config is not None else None
    for name in PROFILE_NAMES:
        if name in statuses:
            continue
        content = profile_bytes[name]
        assert content is not None
        if receipt is None or not active:
            statuses[name] = "unmanaged"
            continue
        entry = entries[name]
        if (
            _sha256(content) != entry["content_sha256"]
            or expected_config_hash is None
            or entry["config_sha256"] != expected_config_hash
            or content != expected[name]
        ):
            statuses[name] = "drift"
        else:
            statuses[name] = "managed"
    return statuses, receipt


def _installed_profiles_diagnostic(statuses: Mapping[str, str]) -> Diagnostic:
    required = {
        "laneorchestrator-router.toml",
        "laneorchestrator-terra-executor.toml",
        "laneorchestrator-sol-reviewer.toml",
    }
    fail_states = {"drift", "bad_mode", "unsafe", "invalid_receipt"}
    mandatory_bad = any(statuses[name] in fail_states or statuses[name] == "missing" for name in required)
    any_degraded = any(value != "managed" for value in statuses.values())
    if mandatory_bad:
        level = Level.FAIL
        message = "Required installed profiles are missing, unsafe, or inconsistent; affected routes are blocked"
    elif any(value in fail_states for value in statuses.values()):
        level = Level.FAIL
        message = "Installed profile state is unsafe or inconsistent"
    elif any_degraded:
        level = Level.WARN
        message = "Installed profiles are usable with missing or unmanaged profile degradation"
    else:
        level = Level.PASS
        message = "Installed profiles and receipt were directly verified"
    return Diagnostic("INSTALLED_PROFILES", level, message, {"profiles": dict(statuses)})


def check_profiles(state_root: Path, agents_root: Path) -> Diagnostic:
    config, _status = _load_config_readonly(state_root)
    statuses, _receipt = _inspect_profiles_readonly(config, state_root, agents_root)
    return _installed_profiles_diagnostic(statuses)


def inspect_role_evidence(config: EffectiveConfig, agents_root: Path) -> Mapping[str, RoleEvidence]:
    """Report exact local profile evidence without claiming host entitlement."""

    if not isinstance(config, EffectiveConfig) or set(config.roles) != set(LOGICAL_ROLES):
        raise ValueError("config must define every logical role")
    expected = render_profiles(config)
    evidence: Dict[str, RoleEvidence] = {}
    for role in LOGICAL_ROLES:
        name = _ROLE_PROFILE[role]
        status_value, content = _read_child(agents_root, name, MAX_PROFILE_BYTES, required_mode=0o600)
        if status_value == "missing":
            availability = Availability.MISSING
            profile_path: Optional[str] = None
        elif status_value == "present" and content == expected[name]:
            availability = Availability.AVAILABLE
            profile_path = _safe_text(agents_root / name, 1024)
        else:
            availability = Availability.UNKNOWN
            profile_path = _safe_text(agents_root / name, 1024)
        evidence[role] = RoleEvidence(role, config.roles[role].model, profile_path, availability)
    return evidence


def check_roles(state_root: Path, agents_root: Path) -> Sequence[Diagnostic]:
    config, _status = _load_config_readonly(state_root)
    if config is None:
        mapping = {
            role: RoleEvidence(role, "", None, Availability.UNKNOWN)
            for role in LOGICAL_ROLES
        }
    else:
        mapping = inspect_role_evidence(config, agents_root)
    specifications = (
        ("router", "ROLE_ROUTER", True, "Router profile evidence was verified", "Required router profile evidence is missing or unverified"),
        ("small_task_executor", "ROLE_SMALL", False, "Small-task profile evidence was verified", "Small-task profile is unavailable; Terra is the documented fallback"),
        ("main_implementer", "ROLE_MAIN", True, "Main implementer profile evidence was verified", "Required Terra main implementer profile evidence is missing or unverified"),
        ("independent_reviewer", "ROLE_REVIEWER", True, "Independent reviewer profile evidence was verified for high-risk readiness", "Independent Sol reviewer evidence is missing or unverified; high-risk readiness is blocked"),
    )
    diagnostics: List[Diagnostic] = []
    for role, code, required, pass_message, degraded_message in specifications:
        item = mapping[role]
        if item.availability is Availability.AVAILABLE:
            level = Level.PASS
            message = pass_message
        elif required:
            level = Level.FAIL
            message = degraded_message
        else:
            level = Level.WARN
            message = degraded_message
        payload: Dict[str, object] = {
            "role": role,
            "configured_model": item.configured_model,
            "profile_path": item.profile_path,
            "profile_evidence": item.availability.value,
        }
        if role == "small_task_executor" and level is not Level.PASS:
            payload["fallback_role"] = "main_implementer"
        if role == "independent_reviewer":
            payload["scope"] = "high-risk planning and independent review"
        diagnostics.append(Diagnostic(code, level, message, payload))
    return tuple(diagnostics)


def check_discovery_readiness(repo_root: Path) -> Diagnostic:
    try:
        content = _read_repo_file(Path(repo_root) / "skills" / "laneorchestrator" / "SKILL.md", 16 * 1024)
        text = content.decode("utf-8")
        ready = text.startswith("---\n") and "name: laneorchestrator" in text and "description:" in text
    except (_InspectionError, UnicodeDecodeError):
        ready = False
    return Diagnostic(
        "CAPABILITY_DISCOVERY",
        Level.PASS if ready else Level.WARN,
        "Bundled capability metadata is ready for bounded discovery" if ready else "Capability discovery is usable without optional bundled metadata",
        {"bundled_skill": "verified" if ready else "missing_or_invalid", "optional_specialists": "not_required"},
    )


def check_model_entitlement_unknown() -> Diagnostic:
    return Diagnostic(
        "MODEL_ENTITLEMENT",
        Level.UNKNOWN,
        "Host model entitlement is not authoritatively observable",
        {"authoritative_query": "not_supported"},
    )


def run_doctor(
    repo_root: Path,
    state_root: Path,
    agents_root: Path,
    env: Optional[Mapping[str, str]] = None,
) -> CommandResult:
    """Run every stable read-only readiness check in canonical order."""

    diagnostics: List[Diagnostic] = []
    diagnostics.extend(check_python_and_platform())
    diagnostics.append(check_codex_cli(env))
    diagnostics.extend(check_manifests(repo_root))
    diagnostics.append(check_profiles(state_root, agents_root))
    diagnostics.extend(check_config_and_paths(state_root, agents_root))
    diagnostics.extend(check_roles(state_root, agents_root))
    diagnostics.append(check_discovery_readiness(repo_root))
    diagnostics.append(check_model_entitlement_unknown())
    return command_result("doctor", diagnostics=diagnostics)


def _receipt_summary(receipt: Optional[Mapping[str, object]]) -> Optional[Mapping[str, object]]:
    if receipt is None:
        return None
    raw_entries = receipt["profiles"]
    assert isinstance(raw_entries, list)
    operations = {entry["operation"] for entry in raw_entries}
    templates = {entry["template_version"] for entry in raw_entries}
    if len(operations) != 1 or len(templates) != 1:
        return None
    return {
        "operation": next(iter(operations)),
        "profile_count": len(raw_entries),
        "schema_version": receipt["schema_version"],
        "template_version": next(iter(templates)),
    }


def run_status(state_root: Path, agents_root: Path) -> CommandResult:
    """Return a shorter read-only summary without creating state or locks."""

    config, _config_status = _load_config_readonly(state_root)
    config_diagnostic, path_diagnostic = check_config_and_paths(state_root, agents_root)
    statuses, receipt = _inspect_profiles_readonly(config, state_root, agents_root)
    profile_diagnostic = _installed_profiles_diagnostic(statuses)
    if config is None:
        effective_roles: Mapping[str, object] = {}
        config_source = "invalid"
    else:
        role_evidence = inspect_role_evidence(config, agents_root)
        effective_roles = {
            role: {
                "model": config.roles[role].model,
                "reasoning_effort": config.roles[role].reasoning_effort,
                "profile_evidence": role_evidence[role].availability.value,
                "profile_path": role_evidence[role].profile_path,
            }
            for role in LOGICAL_ROLES
        }
        config_source = config.source
    data = {
        "effective_roles": effective_roles,
        "config_source": config_source,
        "managed_profile_state": dict(statuses),
        "fallback_policy": {
            "router": "pause_all_routes",
            "small_task_executor": "main_implementer",
            "main_implementer": "pause",
            "high_risk_reviewer": "pause",
            "optional_specialist": "continue_without_specialist",
        },
        "latest_receipt": _receipt_summary(receipt),
    }
    return command_result(
        "status",
        data=data,
        diagnostics=(config_diagnostic, path_diagnostic, profile_diagnostic),
    )
