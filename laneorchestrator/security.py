"""Small no-follow filesystem primitives used by the control plane.

This module intentionally starts with the read primitive.  Mutation helpers are
added separately so configuration loading has no implicit write capability.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


class SecurityError(ValueError):
    """Raised when an untrusted filesystem object fails a safety check."""


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

    flags = os.O_RDONLY
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags |= nofollow
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
