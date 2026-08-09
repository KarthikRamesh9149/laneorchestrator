"""Fail-closed filesystem primitives used by the control plane.

Reads reject terminal links and inspection/open replacement races.  State
mutation is POSIX-only for v0.2.0 and keeps the validated parent directory
descriptor held for every destination operation.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import secrets
import stat
from pathlib import Path
from typing import Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - native Windows is mutation-unsupported.
    fcntl = None  # type: ignore


PRIVATE_MUTATION_LOCK_NAME = ".laneorchestrator-state.lock"


class SecurityError(ValueError):
    """Raised when an untrusted filesystem object fails a safety check."""


try:
    _REPLACE_SUPPORTS_DIR_FD = {"src_dir_fd", "dst_dir_fd"}.issubset(
        inspect.signature(os.replace).parameters
    )
except (TypeError, ValueError):
    _REPLACE_SUPPORTS_DIR_FD = False


def platform_mutation_supported() -> Tuple[bool, str]:
    """Report whether required descriptor-relative mutation guarantees exist."""

    if os.name == "nt":
        return False, "native Windows mutation is unsupported in v0.2.0"
    if os.name != "posix":
        return False, "filesystem mutation requires POSIX descriptor semantics"
    if fcntl is None:
        return False, "filesystem mutation requires POSIX advisory locking"
    if not callable(getattr(fcntl, "flock", None)):
        return False, "filesystem mutation requires callable fcntl.flock"
    lock_ex = getattr(fcntl, "LOCK_EX", None)
    lock_un = getattr(fcntl, "LOCK_UN", None)
    if (
        isinstance(lock_ex, bool)
        or not isinstance(lock_ex, int)
        or lock_ex <= 0
        or isinstance(lock_un, bool)
        or not isinstance(lock_un, int)
        or lock_un <= 0
        or lock_ex == lock_un
    ):
        return False, "filesystem mutation requires usable fcntl.LOCK_EX and fcntl.LOCK_UN"
    required_constants = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    missing_constants = [name for name in required_constants if not hasattr(os, name)]
    if missing_constants:
        return False, "filesystem mutation requires {0}".format(missing_constants[0])
    required_functions = ("fchmod", "fstat", "fsync", "geteuid", "replace")
    missing_functions = [name for name in required_functions if not hasattr(os, name)]
    if missing_functions:
        return False, "filesystem mutation requires os.{0}".format(missing_functions[0])
    for function in (os.open, os.stat, os.unlink):
        if function not in os.supports_dir_fd:
            return False, "filesystem mutation requires descriptor-relative {0}".format(
                function.__name__
            )
    if os.stat not in os.supports_follow_symlinks:
        return False, "filesystem mutation requires no-follow descriptor-relative stat"
    if not _REPLACE_SUPPORTS_DIR_FD:
        return False, "filesystem mutation requires descriptor-relative replace"
    return True, ""


def _require_mutation_support() -> None:
    supported, reason = platform_mutation_supported()
    if not supported:
        raise SecurityError(reason)


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _validate_ancestor_directory(metadata: os.stat_result) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise SecurityError("path component is not a directory")
    writable_by_others = metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    if writable_by_others and not metadata.st_mode & stat.S_ISVTX:
        raise SecurityError("writable ancestor directory must have the sticky bit")


def _validate_private_leaf(metadata: os.stat_result) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise SecurityError("private root is not a directory")
    if metadata.st_uid != os.geteuid():
        raise SecurityError("private root is not owned by the current user")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise SecurityError("private root mode must be 0700")


def _validate_owned_mutation_leaf(metadata: os.stat_result) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise SecurityError("managed root is not a directory")
    if metadata.st_uid != os.geteuid():
        raise SecurityError("managed root is not owned by the current user")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise SecurityError("managed root must not be group or other writable")


def _open_absolute_directory(path: Path, *, owned_mutation_leaf: bool) -> int:
    """Open and validate one absolute directory chain without links."""

    _require_mutation_support()
    candidate = Path(path)
    if not candidate.is_absolute():
        raise SecurityError("private root must be an absolute path")
    components = candidate.parts[1:]
    if any(component in ("", ".", "..") for component in components):
        raise SecurityError("private root contains an unsafe path component")

    flags = _directory_open_flags()
    try:
        descriptor = os.open(os.path.sep, flags)
    except OSError as error:
        raise SecurityError("could not open filesystem root safely") from error
    try:
        root_metadata = os.fstat(descriptor)
        if components:
            _validate_ancestor_directory(root_metadata)
        else:
            (
                _validate_owned_mutation_leaf(root_metadata)
                if owned_mutation_leaf
                else _validate_private_leaf(root_metadata)
            )
        for index, component in enumerate(components):
            try:
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                raise SecurityError("could not open private directory chain safely") from error
            try:
                metadata = os.fstat(child_descriptor)
                if index == len(components) - 1:
                    (
                        _validate_owned_mutation_leaf(metadata)
                        if owned_mutation_leaf
                        else _validate_private_leaf(metadata)
                    )
                else:
                    _validate_ancestor_directory(metadata)
            except BaseException:
                os.close(child_descriptor)
                raise
            previous_descriptor = descriptor
            descriptor = child_descriptor
            os.close(previous_descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_absolute_private_directory(path: Path) -> int:
    """Open and validate an absolute mode-0700 directory without links."""

    return _open_absolute_directory(path, owned_mutation_leaf=False)


def validate_absolute_private_root(path: Path) -> None:
    """Reject a state root whose complete directory chain is not private."""

    descriptor = _open_absolute_private_directory(path)
    os.close(descriptor)


def open_parent_directory_nofollow(path: Path) -> int:
    """Open one absolute mode-0700 parent through a no-follow directory chain."""

    return _open_absolute_private_directory(path)


def open_owned_directory_nofollow(path: Path) -> int:
    """Open an EUID-owned final directory that is not writable by others."""

    return _open_absolute_directory(path, owned_mutation_leaf=True)


def _validate_basename(name: str) -> None:
    if not isinstance(name, str) or not name or name in (".", "..") or "\x00" in name:
        raise SecurityError("destination name must be a safe basename")
    if os.path.basename(name) != name or os.path.sep in name:
        raise SecurityError("destination name must be a safe basename")
    if os.path.altsep is not None and os.path.altsep in name:
        raise SecurityError("destination name must be a safe basename")


def validate_destination_at(parent_fd: int, name: str) -> Optional[os.stat_result]:
    """Inspect an optional regular destination relative to a held parent."""

    _validate_basename(name)
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SecurityError("could not inspect destination safely") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise SecurityError("destination must not be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise SecurityError("destination is not a regular file")
    if metadata.st_nlink != 1:
        raise SecurityError("destination must not have multiple hard links")
    if metadata.st_uid != os.geteuid():
        raise SecurityError("destination is not owned by the current user")
    return metadata


def private_temporary_name(name: str) -> str:
    """Return an unpredictable, bounded sibling name for private publication."""

    _validate_basename(name)
    label = hashlib.sha256(name.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    return ".laneorchestrator-{0}-{1}.tmp".format(label, secrets.token_hex(16))


def write_all(descriptor: int, content: bytes) -> None:
    """Write all bytes to a held descriptor, including across short writes."""

    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise SecurityError("write made no forward progress")
        remaining = remaining[written:]


def _validate_private_lock_identity(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise SecurityError("private mutation lock is not a regular file")
    if metadata.st_nlink != 1:
        raise SecurityError("private mutation lock must not have multiple hard links")
    if metadata.st_uid != os.geteuid():
        raise SecurityError("private mutation lock has the wrong owner")


def _validate_private_lock_metadata(metadata: os.stat_result) -> None:
    _validate_private_lock_identity(metadata)
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise SecurityError("private mutation lock mode must be 0600")


def _open_lock_at(parent_fd: int, *, owned_mutation_parent: bool) -> int:
    """Open, validate, and exclusively lock one mutation lock file."""

    _require_mutation_support()
    try:
        parent_metadata = os.fstat(parent_fd)
    except OSError as error:
        raise SecurityError("could not inspect private lock parent") from error
    (
        _validate_owned_mutation_leaf(parent_metadata)
        if owned_mutation_parent
        else _validate_private_leaf(parent_metadata)
    )
    common_flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        common_flags |= os.O_CLOEXEC
    created = False
    try:
        try:
            descriptor = os.open(
                PRIVATE_MUTATION_LOCK_NAME,
                common_flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_fd,
            )
            created = True
        except FileExistsError:
            descriptor = os.open(
                PRIVATE_MUTATION_LOCK_NAME,
                common_flags,
                dir_fd=parent_fd,
            )
    except OSError as error:
        raise SecurityError("could not open private mutation lock safely") from error

    locked = False
    successful = False
    try:
        opened = os.fstat(descriptor)
        _validate_private_lock_identity(opened)
        assert fcntl is not None
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        if created:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            os.fsync(parent_fd)
        opened = os.fstat(descriptor)
        _validate_private_lock_metadata(opened)
        current = os.stat(
            PRIVATE_MUTATION_LOCK_NAME,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        _validate_private_lock_metadata(current)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SecurityError("private mutation lock changed while acquiring it")
        successful = True
        return descriptor
    except OSError as error:
        raise SecurityError("could not acquire private mutation lock") from error
    finally:
        if not successful:
            if locked:
                assert fcntl is not None
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)
            else:
                os.close(descriptor)


def open_private_lock_at(parent_fd: int) -> int:
    """Lock one exact mode-0700 private mutation root."""

    return _open_lock_at(parent_fd, owned_mutation_parent=False)


def open_owned_lock_at(parent_fd: int) -> int:
    """Lock one safe EUID-owned managed-agents mutation root."""

    return _open_lock_at(parent_fd, owned_mutation_parent=True)


def close_private_lock(descriptor: int) -> None:
    """Release and close a descriptor returned by ``open_private_lock_at``."""

    assert fcntl is not None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def create_private_file_at_locked(
    parent_fd: int, name: str, content: bytes, mode: int = 0o600
) -> None:
    """Create one complete private file without replacing an existing name.

    The caller must hold the lock returned by :func:`open_private_lock_at` for
    ``parent_fd``.  Cooperating readers take the same lock, so they cannot
    observe the destination until its content and directory entry are durable.
    ``FileExistsError`` is intentionally preserved so callers can select a new
    unpredictable destination without weakening no-replace publication.
    """

    _require_mutation_support()
    _validate_basename(name)
    if name == PRIVATE_MUTATION_LOCK_NAME:
        raise SecurityError("private mutation lock name is reserved")
    if not isinstance(content, bytes):
        raise SecurityError("content must be bytes")
    if (
        isinstance(mode, bool)
        or not isinstance(mode, int)
        or mode < 0
        or mode > 0o777
        or mode & 0o077
    ):
        raise SecurityError("mode must grant permissions only to the owner")
    try:
        _validate_private_leaf(os.fstat(parent_fd))
    except OSError as error:
        raise SecurityError("could not inspect private creation parent") from error

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = -1
    created = False
    successful = False
    try:
        try:
            descriptor = os.open(name, flags, mode, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            raise
        except OSError as error:
            raise SecurityError("could not create private file safely") from error
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise SecurityError("private created object is not a single regular file")
        if opened.st_uid != os.geteuid():
            raise SecurityError("private created file has the wrong owner")
        os.fchmod(descriptor, mode)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.fsync(parent_fd)
        successful = True
    finally:
        try:
            if descriptor >= 0:
                os.close(descriptor)
        finally:
            if created and not successful:
                _unlink_regular_nofollow_at_if_present_locked(parent_fd, name)
                os.fsync(parent_fd)


def _unlink_regular_nofollow_at_if_present_locked(parent_fd: int, name: str) -> None:
    """Unlink an optional regular sibling while the private lock is held."""

    if name == PRIVATE_MUTATION_LOCK_NAME:
        raise SecurityError("private mutation lock must not be removed")
    metadata = validate_destination_at(parent_fd, name)
    if metadata is None:
        return
    try:
        os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    except OSError as error:
        raise SecurityError("could not remove private temporary file") from error


def unlink_regular_nofollow_at_if_present(parent_fd: int, name: str) -> None:
    """Lock and unlink an optional regular sibling without following a link."""

    _require_mutation_support()
    lock_fd = open_private_lock_at(parent_fd)
    try:
        _unlink_regular_nofollow_at_if_present_locked(parent_fd, name)
    finally:
        close_private_lock(lock_fd)


def _same_destination(
    before: Optional[os.stat_result], after: Optional[os.stat_result]
) -> bool:
    if before is None or after is None:
        return before is None and after is None
    return (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)


def atomic_private_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    """Atomically publish bytes under a held, validated private parent."""

    _require_mutation_support()
    if not isinstance(content, bytes):
        raise SecurityError("content must be bytes")
    if (
        isinstance(mode, bool)
        or not isinstance(mode, int)
        or mode < 0
        or mode > 0o777
        or mode & 0o077
    ):
        raise SecurityError("mode must grant permissions only to the owner")

    destination = Path(path)
    if destination.name == PRIVATE_MUTATION_LOCK_NAME:
        raise SecurityError("private mutation lock name is reserved")
    temporary_name = private_temporary_name(destination.name)
    parent_fd = open_parent_directory_nofollow(destination.parent)
    descriptor = -1
    lock_fd = -1
    temporary_created = False
    try:
        lock_fd = open_private_lock_at(parent_fd)
        inspected_destination = validate_destination_at(parent_fd, destination.name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(temporary_name, flags, mode, dir_fd=parent_fd)
        temporary_created = True
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise SecurityError("private temporary object is not a single regular file")
        if opened.st_uid != os.geteuid():
            raise SecurityError("private temporary file has the wrong owner")
        os.fchmod(descriptor, mode)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1

        current_destination = validate_destination_at(parent_fd, destination.name)
        if not _same_destination(inspected_destination, current_destination):
            raise SecurityError("destination changed before atomic replacement")
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_created = False
        os.fsync(parent_fd)
    finally:
        try:
            if descriptor >= 0:
                os.close(descriptor)
        finally:
            try:
                if temporary_created:
                    _unlink_regular_nofollow_at_if_present_locked(
                        parent_fd, temporary_name
                    )
            finally:
                try:
                    if lock_fd >= 0:
                        close_private_lock(lock_fd)
                finally:
                    os.close(parent_fd)


def read_regular_nofollow(path: Path, max_bytes: int) -> bytes:
    """Read one bounded regular file without following a symbolic link.

    The pre-open ``lstat`` and descriptor ``fstat`` must identify the same
    inode.  That rejects a replacement race between inspection and open while
    still reading from the held descriptor rather than the path name.
    """

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise SecurityError("max_bytes must be a non-negative integer")
    candidate = Path(path)
    try:
        before = os.lstat(candidate)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise SecurityError("could not inspect file") from error
    if stat.S_ISLNK(before.st_mode):
        raise SecurityError("symbolic links are not allowed")
    if not stat.S_ISREG(before.st_mode):
        raise SecurityError("path is not a regular file")

    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW
    except AttributeError as error:
        raise SecurityError("platform does not support no-follow reads") from error
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise SecurityError("could not open regular file without following links") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise SecurityError("opened path is not a regular file")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise SecurityError("file changed while opening")
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            descriptor = -1
            content = source.read(max_bytes + 1)
    except OSError as error:
        raise SecurityError("could not read regular file") from error
    finally:
        if descriptor != -1:
            os.close(descriptor)
    if len(content) > max_bytes:
        raise SecurityError("file exceeds maximum size")
    return content


def sha256_bytes(content: bytes) -> str:
    """Return the exact lowercase hexadecimal SHA-256 digest of bytes."""

    return hashlib.sha256(content).hexdigest()


def sha256_regular_file(path: Path, max_bytes: int) -> str:
    """Hash one bounded regular file using the no-follow read primitive."""

    return sha256_bytes(read_regular_nofollow(path, max_bytes))
