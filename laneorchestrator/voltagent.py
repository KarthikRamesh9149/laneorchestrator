"""Pinned, attributed VoltAgent pack with safe one-time installation.

The upstream TOML profiles are bundled as a release asset.  They are never
executed while being inspected: this module verifies the exact source tree,
rewrites only the profile identity/model fields, and installs the resulting
namespaced profiles through a short-lived approved plan.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

from .diagnostics import CommandResult, command_result
from .plans import MutationPlan, Operation, PlanError, approval_digest, consume_plan, create_plan, load_plan
from .security import (
    SecurityError,
    close_private_lock,
    open_parent_directory_nofollow,
    open_private_lock_at,
    open_owned_directory_nofollow,
    open_owned_lock_at,
    private_temporary_name,
    read_regular_nofollow,
    validate_destination_at,
    write_all,
)


UPSTREAM_REPOSITORY = "https://github.com/VoltAgent/awesome-codex-subagents"
UPSTREAM_COMMIT = "5605c9c18b3687993919d6cc467af4a34898fee2"
UPSTREAM_LICENSE_SHA256 = "6d4bdc9a9cf30e7beb593475fdcdbf29f981ea6bd7923f202866145409f87b44"
UPSTREAM_TREE_SHA256 = "e80967711ac1b9153962ac1efd6fb57257b492d991ad0a3c1c1a4bccf851d56a"
PACK_AGENT_COUNT = 172
PACK_PREFIX = "laneorchestrator-voltagent-"
PACK_MODEL = "gpt-5.6-terra"
PACK_REASONING_EFFORT = "high"
PACK_PLAN_KIND = "voltagent.install"
PACK_PLANS_DIRECTORY = "voltagent-plans"
MAX_PACK_FILE_BYTES = 16 * 1024

_NAME_RE = re.compile(r'(?m)^name = "([a-z0-9][a-z0-9.-]{0,95})"$')
_DESCRIPTION_RE = re.compile(r'(?m)^description = "([^"\n]{1,2048})"$')
_MODEL_RE = re.compile(r'(?m)^model = "[^"]+"$')
_EFFORT_RE = re.compile(r'(?m)^model_reasoning_effort = "[^"]+"$')
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}\.toml$")


class PackError(SecurityError):
    """Raised when the attributed agent pack or its installation is unsafe."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_root() -> Path:
    return _repository_root() / "agents" / "voltagent-upstream"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source_files() -> Tuple[Path, ...]:
    """Return the exact regular upstream agent files without following links."""

    root = _source_root()
    try:
        root_info = root.lstat()
    except OSError as error:
        raise PackError("bundled VoltAgent source is unavailable") from error
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise PackError("bundled VoltAgent source root is unsafe")
    pending = [root / "profiles"]
    files = []
    while pending:
        directory = pending.pop()
        try:
            info = directory.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PackError("bundled VoltAgent source contains an unsafe directory")
            with os.scandir(directory) as entries:
                listed = sorted(entries, key=lambda entry: entry.name)
        except PackError:
            raise
        except OSError as error:
            raise PackError("bundled VoltAgent source cannot be traversed") from error
        for entry in reversed(listed):
            path = Path(entry.path)
            try:
                info = path.lstat()
            except OSError as error:
                raise PackError("bundled VoltAgent source cannot be inspected") from error
            if stat.S_ISLNK(info.st_mode):
                raise PackError("bundled VoltAgent source contains a symbolic link")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                if path.name == "README.md":
                    continue
                if path.suffix != ".toml":
                    raise PackError("bundled VoltAgent source contains an unexpected file")
                files.append(path)
            else:
                raise PackError("bundled VoltAgent source contains a non-regular file")
    ordered = tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))
    if len(ordered) != PACK_AGENT_COUNT:
        raise PackError("bundled VoltAgent agent count does not match the pinned source")
    return ordered


def _verified_source() -> Mapping[Path, bytes]:
    root = _source_root()
    try:
        license_bytes = read_regular_nofollow(root / "LICENSE", MAX_PACK_FILE_BYTES)
    except (OSError, SecurityError) as error:
        raise PackError("bundled VoltAgent license is unavailable") from error
    if _sha256(license_bytes) != UPSTREAM_LICENSE_SHA256:
        raise PackError("bundled VoltAgent license does not match the pinned source")
    records = []
    contents: Dict[Path, bytes] = {}
    for path in _source_files():
        try:
            content = read_regular_nofollow(path, MAX_PACK_FILE_BYTES)
        except (OSError, SecurityError) as error:
            raise PackError("bundled VoltAgent profile cannot be read safely") from error
        relative = path.relative_to(root).as_posix()
        records.append(relative.encode("utf-8") + b"\0" + _sha256(content).encode("ascii") + b"\n")
        contents[path] = content
    if _sha256(b"".join(records)) != UPSTREAM_TREE_SHA256:
        raise PackError("bundled VoltAgent profiles do not match the pinned source")
    return contents


def _render_one(content: bytes) -> Tuple[str, bytes]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackError("bundled VoltAgent profile is not UTF-8") from error
    name_match = _NAME_RE.search(text)
    if name_match is None or len(_NAME_RE.findall(text)) != 1 or len(_DESCRIPTION_RE.findall(text)) != 1:
        raise PackError("bundled VoltAgent profile has an invalid public header")
    if len(_MODEL_RE.findall(text)) != 1 or len(_EFFORT_RE.findall(text)) != 1:
        raise PackError("bundled VoltAgent profile has an invalid model header")
    filename = PACK_PREFIX + name_match.group(1).replace(".", "-") + ".toml"
    if _PROFILE_RE.fullmatch(filename) is None:
        raise PackError("bundled VoltAgent profile name is unsafe")
    text = _NAME_RE.sub('name = "{0}"'.format(filename[:-5]), text, count=1)
    text = _MODEL_RE.sub('model = "{0}"'.format(PACK_MODEL), text, count=1)
    text = _EFFORT_RE.sub('model_reasoning_effort = "{0}"'.format(PACK_REASONING_EFFORT), text, count=1)
    marker = "# managed-by: laneorchestrator voltagent {0}\n".format(UPSTREAM_COMMIT)
    return filename, (marker + text).encode("utf-8")


def render_pack() -> Mapping[str, bytes]:
    """Render every pinned specialist as a namespaced Terra profile."""

    rendered: Dict[str, bytes] = {}
    for content in _verified_source().values():
        name, profile = _render_one(content)
        if name in rendered:
            raise PackError("bundled VoltAgent profiles have a duplicate name")
        rendered[name] = profile
    if len(rendered) != PACK_AGENT_COUNT:
        raise PackError("bundled VoltAgent rendering is incomplete")
    return dict(sorted(rendered.items()))


def pack_inventory() -> CommandResult:
    """Return the pinned source identity without mutating user state."""

    profiles = render_pack()
    return command_result(
        "voltagent",
        data={
            "agent_count": len(profiles),
            "model": PACK_MODEL,
            "reasoning_effort": PACK_REASONING_EFFORT,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_repository": UPSTREAM_REPOSITORY,
        },
    )


def _plans_root(state_root: Path) -> Path:
    """Create or validate the exact private plan child without following links."""

    state = Path(state_root)
    parent_fd = lock_fd = -1
    try:
        parent_fd = open_parent_directory_nofollow(state)
        lock_fd = open_private_lock_at(parent_fd)
        try:
            metadata = os.stat(PACK_PLANS_DIRECTORY, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.mkdir(PACK_PLANS_DIRECTORY, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            metadata = os.stat(PACK_PLANS_DIRECTORY, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise PackError("private VoltAgent plan state is unsafe")
    except OSError as error:
        raise PackError("could not create private VoltAgent plan state") from error
    except SecurityError as error:
        raise PackError("private VoltAgent plan state is unsafe") from error
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
    return state / PACK_PLANS_DIRECTORY


def _destination_hash(path: Path) -> Optional[str]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise PackError("could not inspect VoltAgent destination") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PackError("VoltAgent destination is not a safe regular file")
    try:
        return _sha256(read_regular_nofollow(path, MAX_PACK_FILE_BYTES))
    except (OSError, SecurityError) as error:
        raise PackError("could not read VoltAgent destination safely") from error


def pack_status(agents_root: Path) -> CommandResult:
    """Report whether all bundled specialist profiles are present and exact."""

    rendered = render_pack()
    root = Path(agents_root)
    installed = missing = drifted = 0
    for name, expected in rendered.items():
        observed = _destination_hash(root / name)
        if observed is None:
            missing += 1
        elif observed == _sha256(expected):
            installed += 1
        else:
            drifted += 1
    return command_result(
        "voltagent",
        data={"agent_count": len(rendered), "installed": installed, "missing": missing, "drifted": drifted},
    )


def preview_install(agents_root: Path, state_root: Path, now: Optional[int] = None) -> Tuple[str, CommandResult]:
    """Create an exact, short-lived plan for installing the entire agent pack."""

    rendered = render_pack()
    root = Path(agents_root)
    if not root.is_absolute() or not Path(state_root).is_absolute():
        raise PackError("VoltAgent roots must be absolute")
    observed = {name: _destination_hash(root / name) for name in rendered}
    present = {name: digest for name, digest in observed.items() if digest is not None}
    expected = {name: _sha256(content) for name, content in rendered.items()}
    if present and set(present) != set(rendered):
        raise PackError("partial VoltAgent installation is refused; resolve existing names first")
    if present and any(present[name] != expected[name] for name in rendered):
        raise PackError("VoltAgent profile collision or drift is refused")
    operations = tuple(
        Operation(
            path=os.fspath(root / name),
            before_sha256=observed[name],
            after_sha256=expected[name],
            content_b64=None,
        )
        for name in rendered
    )
    plans_root = _plans_root(Path(state_root))
    try:
        token = create_plan(PACK_PLAN_KIND, operations, plans_root, now=now)
        plan = load_plan(token, PACK_PLAN_KIND, plans_root, now=now)
    except PlanError as error:
        raise PackError("could not create VoltAgent installation plan") from error
    return token, command_result(
        "voltagent",
        data={
            "action": "install",
            "agent_count": len(rendered),
            "approval_digest": approval_digest(plan),
            "change_count": sum(1 for value in observed.values() if value is None),
            "expires_in_seconds": 600,
            "phase": "preview",
            "token": token,
            "upstream_commit": UPSTREAM_COMMIT,
        },
    )


def _validate_plan(plan: MutationPlan, agents_root: Path, rendered: Mapping[str, bytes]) -> bool:
    expected = {os.fspath(Path(agents_root) / name): _sha256(content) for name, content in rendered.items()}
    if len(plan.operations) != len(expected):
        raise PackError("VoltAgent plan is incomplete")
    no_change = True
    for operation in plan.operations:
        if operation.path not in expected or operation.after_sha256 != expected[operation.path] or operation.content_b64 is not None:
            raise PackError("VoltAgent plan does not match the pinned pack")
        if operation.before_sha256 is None:
            no_change = False
        elif operation.before_sha256 != operation.after_sha256:
            raise PackError("VoltAgent plan has an invalid destination state")
    if {operation.path for operation in plan.operations} != set(expected):
        raise PackError("VoltAgent plan has duplicate or missing destinations")
    return no_change


def _write_temporary(parent_fd: int, final_name: str, content: bytes) -> str:
    temporary = private_temporary_name(final_name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise PackError("VoltAgent temporary file is unsafe")
        os.fchmod(descriptor, 0o600)
        write_all(descriptor, content)
        os.fsync(descriptor)
        return temporary
    except OSError as error:
        raise PackError("could not stage VoltAgent profile safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlink_if_present(parent_fd: int, name: str) -> None:
    try:
        info = validate_destination_at(parent_fd, name)
        if info is not None:
            os.unlink(name, dir_fd=parent_fd)
    except OSError as error:
        raise PackError("could not roll back VoltAgent installation") from error


def _apply_install(plan: MutationPlan, agents_root: Path) -> CommandResult:
    rendered = render_pack()
    root = Path(agents_root)
    no_change = _validate_plan(plan, root, rendered)
    directory_fd = lock_fd = -1
    staged: Dict[str, str] = {}
    published = []
    try:
        directory_fd = open_owned_directory_nofollow(root)
        lock_fd = open_owned_lock_at(directory_fd)
        for name, content in rendered.items():
            current = validate_destination_at(directory_fd, name)
            if no_change:
                if current is None:
                    raise PackError("VoltAgent state changed after preview")
                continue
            if current is not None:
                raise PackError("VoltAgent state changed after preview")
            staged[name] = _write_temporary(directory_fd, name, content)
        if not no_change:
            for name in rendered:
                os.replace(staged[name], name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                published.append(name)
            os.fsync(directory_fd)
    except (OSError, SecurityError, PackError) as error:
        rollback_errors = []
        for name in reversed(published):
            try:
                _unlink_if_present(directory_fd, name)
            except PackError as rollback_error:
                rollback_errors.append(str(rollback_error))
        for temporary in staged.values():
            try:
                _unlink_if_present(directory_fd, temporary)
            except PackError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if directory_fd >= 0:
            try:
                os.fsync(directory_fd)
            except OSError:
                rollback_errors.append("directory sync failed")
        if rollback_errors:
            raise PackError("VoltAgent installation rollback was incomplete") from error
        if isinstance(error, PackError):
            raise
        raise PackError("VoltAgent installation failed safely") from error
    finally:
        if lock_fd >= 0:
            close_private_lock(lock_fd)
        if directory_fd >= 0:
            os.close(directory_fd)
    return command_result(
        "voltagent",
        data={"action": "install", "agent_count": len(rendered), "change_count": 0 if no_change else len(rendered), "phase": "apply", "upstream_commit": UPSTREAM_COMMIT},
    )


def apply_install(token: str, agents_root: Path, state_root: Path, approval: Optional[str] = None, now: Optional[int] = None) -> CommandResult:
    """Consume exactly one approved plan and install all pinned specialists."""

    plans_root = _plans_root(Path(state_root))
    try:
        return consume_plan(token, PACK_PLAN_KIND, plans_root, lambda plan: _apply_install(plan, Path(agents_root)), approval=approval, now=now)
    except PackError:
        raise
    except (PlanError, SecurityError) as error:
        raise PackError("VoltAgent installation plan could not be applied") from error
