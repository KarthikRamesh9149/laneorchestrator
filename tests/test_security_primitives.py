from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from laneorchestrator import security as security_module
from laneorchestrator.security import (
    PRIVATE_MUTATION_LOCK_NAME,
    SecurityError,
    atomic_private_write,
    close_private_lock,
    open_parent_directory_nofollow,
    open_private_lock_at,
    platform_mutation_supported,
    private_temporary_name,
    read_regular_nofollow,
    sha256_bytes,
    sha256_regular_file,
    unlink_regular_nofollow_at_if_present,
    validate_absolute_private_root,
    validate_destination_at,
    write_all,
)


POSIX_MUTATION = os.name == "posix" and all(
    hasattr(os, attribute) for attribute in ("O_DIRECTORY", "O_NOFOLLOW")
)


@unittest.skipUnless(POSIX_MUTATION, "descriptor-relative POSIX primitives unavailable")
class SecurityPrimitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def assert_lock_is_contended_by_child(self) -> None:
        code = """
import fcntl
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_NOFOLLOW)
try:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(73)
    fcntl.flock(descriptor, fcntl.LOCK_UN)
finally:
    os.close(descriptor)
"""
        result = subprocess.run(
            [sys.executable, "-c", code, os.fspath(self.private / PRIVATE_MUTATION_LOCK_NAME)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 73, msg=result.stderr)

    def test_validate_absolute_private_root_accepts_owned_mode_0700(self) -> None:
        validate_absolute_private_root(self.private)

    def test_validate_absolute_private_root_rejects_relative_and_wrong_mode(self) -> None:
        with self.assertRaises(SecurityError):
            validate_absolute_private_root(Path("relative"))
        self.private.chmod(0o750)
        with self.assertRaises(SecurityError):
            validate_absolute_private_root(self.private)

    def test_validate_absolute_private_root_rejects_wrong_owner(self) -> None:
        with mock.patch(
            "laneorchestrator.security.os.geteuid",
            return_value=os.geteuid() + 1,
        ):
            with self.assertRaises(SecurityError):
                validate_absolute_private_root(self.private)

    def test_validate_absolute_private_root_rejects_linked_and_file_components(self) -> None:
        actual = self.root / "actual"
        actual.mkdir(mode=0o700)
        actual.chmod(0o700)
        linked = self.root / "linked"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(SecurityError):
            validate_absolute_private_root(linked)

        file_component = self.root / "file"
        file_component.write_bytes(b"not a directory")
        with self.assertRaises(SecurityError):
            validate_absolute_private_root(file_component / "child")

    def test_validate_rejects_nonsticky_writable_ancestor_but_accepts_sticky(self) -> None:
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        unsafe_private = unsafe / "private"
        unsafe_private.mkdir(mode=0o700)
        unsafe_private.chmod(0o700)
        with self.assertRaises(SecurityError):
            validate_absolute_private_root(unsafe_private)

        sticky = self.root / "sticky"
        sticky.mkdir(mode=0o777)
        sticky.chmod(0o1777)
        sticky_private = sticky / "private"
        sticky_private.mkdir(mode=0o700)
        sticky_private.chmod(0o700)
        validate_absolute_private_root(sticky_private)

    def test_read_and_hash_regular_file_exactly(self) -> None:
        path = self.private / "content"
        path.write_bytes(b"abc")
        self.assertEqual(read_regular_nofollow(path, 3), b"abc")
        expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        self.assertEqual(sha256_bytes(b"abc"), expected)
        self.assertEqual(sha256_regular_file(path, 3), expected)
        self.assertRegex(expected, r"^[0-9a-f]{64}$")

    def test_read_rejects_live_and_dangling_links_directory_fifo_and_oversize(self) -> None:
        regular = self.private / "regular"
        regular.write_bytes(b"abcd")
        live = self.private / "live"
        live.symlink_to(regular)
        dangling = self.private / "dangling"
        dangling.symlink_to(self.private / "missing")
        fifo = self.private / "fifo"
        os.mkfifo(fifo)
        for candidate in (live, dangling, self.private, fifo):
            with self.subTest(candidate=candidate):
                with self.assertRaises(SecurityError):
                    read_regular_nofollow(candidate, 10)
        with self.assertRaises(SecurityError):
            read_regular_nofollow(regular, 3)

    def test_read_detects_replacement_between_inspection_and_open(self) -> None:
        destination = self.private / "content"
        destination.write_bytes(b"old")
        replacement = self.private / "replacement"
        replacement.write_bytes(b"new")
        real_open = os.open
        raced = False

        def replace_then_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal raced
            if not raced and os.fspath(path) == os.fspath(destination):
                raced = True
                os.replace(replacement, destination)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("laneorchestrator.security.os.open", side_effect=replace_then_open):
            with self.assertRaises(SecurityError):
                read_regular_nofollow(destination, 10)

    def test_atomic_write_never_follows_dangling_destination(self) -> None:
        outside = self.root / "outside"
        destination = self.private / "config.json"
        destination.symlink_to(outside)
        with self.assertRaises(SecurityError):
            atomic_private_write(destination, b"{}\n")
        self.assertFalse(outside.exists())

    def test_private_lock_rejects_symlink_nonregular_hardlink_and_unsafe_mode(self) -> None:
        lock_path = self.private / PRIVATE_MUTATION_LOCK_NAME
        outside = self.root / "outside-lock"
        outside.write_bytes(b"outside")
        lock_path.symlink_to(outside)
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new")
        self.assertEqual(outside.read_bytes(), b"outside")
        self.assertFalse((self.private / "config.json").exists())

        lock_path.unlink()
        lock_path.mkdir()
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new")
        lock_path.rmdir()

        os.mkfifo(lock_path)
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new")
        lock_path.unlink()

        os.link(outside, lock_path)
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new")
        lock_path.unlink()

        lock_path.write_bytes(b"")
        lock_path.chmod(0o644)
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new")
        self.assertFalse((self.private / "config.json").exists())

    def test_atomic_write_rejects_reserved_lock_destination(self) -> None:
        parent_fd = open_parent_directory_nofollow(self.private)
        lock_fd = open_private_lock_at(parent_fd)
        close_private_lock(lock_fd)
        os.close(parent_fd)
        lock_path = self.private / PRIVATE_MUTATION_LOCK_NAME
        before = lock_path.stat()
        with self.assertRaises(SecurityError):
            atomic_private_write(lock_path, b"replacement")
        after = lock_path.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(lock_path.read_bytes(), b"")

    def test_private_lock_is_exclusive_across_publication_and_cleanup(self) -> None:
        destination = self.private / "config.json"
        real_replace = os.replace
        real_validate = validate_destination_at

        def checked_validate(parent_fd: int, name: str) -> object:
            if name == destination.name:
                self.assert_lock_is_contended_by_child()
            return real_validate(parent_fd, name)

        def checked_replace(*args: object, **kwargs: object) -> None:
            self.assert_lock_is_contended_by_child()
            real_replace(*args, **kwargs)

        with mock.patch(
            "laneorchestrator.security.validate_destination_at",
            side_effect=checked_validate,
        ):
            with mock.patch(
                "laneorchestrator.security.os.replace", side_effect=checked_replace
            ):
                atomic_private_write(destination, b"published\n")
        self.assertEqual(destination.read_bytes(), b"published\n")

        real_cleanup = security_module._unlink_regular_nofollow_at_if_present_locked

        def checked_cleanup(parent_fd: int, name: str) -> None:
            self.assert_lock_is_contended_by_child()
            real_cleanup(parent_fd, name)

        with mock.patch("os.replace", side_effect=OSError("injected")):
            with mock.patch(
                "laneorchestrator.security._unlink_regular_nofollow_at_if_present_locked",
                side_effect=checked_cleanup,
            ):
                with self.assertRaises(OSError):
                    atomic_private_write(destination, b"not published\n")
        self.assertEqual(destination.read_bytes(), b"published\n")
        parent_fd = open_parent_directory_nofollow(self.private)
        try:
            lock_fd = open_private_lock_at(parent_fd)
            close_private_lock(lock_fd)
        finally:
            os.close(parent_fd)

    def test_cooperating_child_waits_for_lock_then_publishes(self) -> None:
        parent_fd = open_parent_directory_nofollow(self.private)
        lock_fd = open_private_lock_at(parent_fd)
        destination = self.private / "config.json"
        code = """
import sys
from pathlib import Path
from laneorchestrator import security

real_open_private_lock_at = security.open_private_lock_at
def announce_then_lock(parent_fd):
    print("waiting", flush=True)
    return real_open_private_lock_at(parent_fd)

security.open_private_lock_at = announce_then_lock
security.atomic_private_write(Path(sys.argv[1]), b"child published\\n")
print("done", flush=True)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", code, os.fspath(destination)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertIsNotNone(process.stdout)
            self.assertEqual(process.stdout.readline().strip(), "waiting")
            with self.assertRaises(subprocess.TimeoutExpired):
                process.wait(timeout=0.25)
            self.assertFalse(destination.exists())
            close_private_lock(lock_fd)
            lock_fd = -1
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, msg=stderr)
            self.assertEqual(stdout.strip(), "done")
            self.assertEqual(destination.read_bytes(), b"child published\n")
        finally:
            if lock_fd >= 0:
                close_private_lock(lock_fd)
            os.close(parent_fd)
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_atomic_write_rejects_live_link_directory_fifo_and_symlinked_ancestor(self) -> None:
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        linked = self.private / "linked"
        linked.symlink_to(outside)
        directory = self.private / "directory"
        directory.mkdir()
        fifo = self.private / "fifo-destination"
        os.mkfifo(fifo)
        for candidate in (linked, directory, fifo):
            with self.subTest(candidate=candidate):
                with self.assertRaises(SecurityError):
                    atomic_private_write(candidate, b"new")
        self.assertEqual(outside.read_bytes(), b"outside")

        actual = self.root / "actual-parent"
        actual.mkdir(mode=0o700)
        actual.chmod(0o700)
        alias = self.root / "alias-parent"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(SecurityError):
            atomic_private_write(alias / "config.json", b"new")
        self.assertFalse((actual / "config.json").exists())

    def test_atomic_write_rejects_multiply_linked_destination(self) -> None:
        destination = self.private / "config.json"
        destination.write_bytes(b"old")
        alias = self.private / "config.alias"
        os.link(destination, alias)
        with self.assertRaises(SecurityError):
            atomic_private_write(destination, b"new")
        self.assertEqual(destination.read_bytes(), b"old")
        self.assertEqual(alias.read_bytes(), b"old")

    def test_atomic_write_rejects_relative_path_and_unsafe_mode(self) -> None:
        with self.assertRaises(SecurityError):
            atomic_private_write(Path("relative/config.json"), b"new")
        with self.assertRaises(SecurityError):
            atomic_private_write(self.private / "config.json", b"new", mode=0o644)

    def test_injected_replace_failure_preserves_old_complete_file(self) -> None:
        destination = self.private / "config.json"
        destination.write_bytes(b"old\n")
        with mock.patch("os.replace", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                atomic_private_write(destination, b"new\n")
        self.assertEqual(destination.read_bytes(), b"old\n")
        self.assertEqual(
            {entry.name for entry in self.private.iterdir()},
            {destination.name, PRIVATE_MUTATION_LOCK_NAME},
        )

    def test_destination_replacement_race_is_rejected_before_publication(self) -> None:
        destination = self.private / "config.json"
        destination.write_bytes(b"old\n")
        raced_content = self.private / "raced"
        raced_content.write_bytes(b"raced\n")
        real_write_all = write_all

        def write_then_replace(descriptor: int, content: bytes) -> None:
            real_write_all(descriptor, content)
            os.replace(raced_content, destination)

        with mock.patch(
            "laneorchestrator.security.write_all", side_effect=write_then_replace
        ):
            with self.assertRaises(SecurityError):
                atomic_private_write(destination, b"new\n")
        self.assertEqual(destination.read_bytes(), b"raced\n")
        self.assertEqual(
            {entry.name for entry in self.private.iterdir()},
            {destination.name, PRIVATE_MUTATION_LOCK_NAME},
        )

    def test_atomic_write_publishes_complete_private_file(self) -> None:
        destination = self.private / "config.json"
        content = (b"new complete content\n" * 4096)
        atomic_private_write(destination, content)
        lock_metadata = (self.private / PRIVATE_MUTATION_LOCK_NAME).stat()
        self.assertTrue(stat.S_ISREG(lock_metadata.st_mode))
        self.assertEqual(lock_metadata.st_nlink, 1)
        self.assertEqual(lock_metadata.st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(lock_metadata.st_mode), 0o600)
        self.assertEqual(destination.read_bytes(), content)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        atomic_private_write(destination, b"replacement\n", mode=0o400)
        self.assertEqual(destination.read_bytes(), b"replacement\n")
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o400)

    def test_destination_and_temporary_name_helpers(self) -> None:
        parent_fd = open_parent_directory_nofollow(self.private)
        try:
            self.assertIsNone(validate_destination_at(parent_fd, "missing"))
            destination = self.private / "config.json"
            destination.write_bytes(b"content")
            inspected = validate_destination_at(parent_fd, destination.name)
            self.assertIsNotNone(inspected)
            for unsafe in ("", ".", "..", "a/b"):
                with self.subTest(unsafe=unsafe):
                    with self.assertRaises(SecurityError):
                        validate_destination_at(parent_fd, unsafe)
        finally:
            os.close(parent_fd)

        first = private_temporary_name("config.json")
        second = private_temporary_name("config.json")
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).name, first)
        self.assertTrue(first.startswith("."))

    def test_write_all_handles_short_writes_and_rejects_no_progress(self) -> None:
        with mock.patch("laneorchestrator.security.os.write", side_effect=(2, 3)) as writer:
            write_all(99, b"abcde")
        self.assertEqual(writer.call_count, 2)
        with mock.patch("laneorchestrator.security.os.write", return_value=0):
            with self.assertRaises(SecurityError):
                write_all(99, b"content")

    def test_unlink_regular_nofollow_at_if_present_never_follows_links(self) -> None:
        parent_fd = open_parent_directory_nofollow(self.private)
        try:
            unlink_regular_nofollow_at_if_present(parent_fd, "missing")
            regular = self.private / "temporary"
            regular.write_bytes(b"temporary")
            unlink_regular_nofollow_at_if_present(parent_fd, regular.name)
            self.assertFalse(regular.exists())

            outside = self.root / "outside"
            outside.write_bytes(b"outside")
            linked = self.private / "linked-temporary"
            linked.symlink_to(outside)
            with self.assertRaises(SecurityError):
                unlink_regular_nofollow_at_if_present(parent_fd, linked.name)
            self.assertEqual(outside.read_bytes(), b"outside")
            self.assertTrue(linked.is_symlink())
        finally:
            os.close(parent_fd)


class PlatformSupportTests(unittest.TestCase):
    def test_native_windows_reports_unsupported(self) -> None:
        with mock.patch("laneorchestrator.security.os.name", "nt"):
            supported, reason = platform_mutation_supported()
        self.assertFalse(supported)
        self.assertIn("Windows", reason)
        self.assertIn("v0.2.0", reason)

    def test_windows_atomic_mutation_refuses_before_opening_destination(self) -> None:
        destination = Path("C:/state/config.json")
        with mock.patch("laneorchestrator.security.os.name", "nt"):
            with mock.patch("laneorchestrator.security.os.open") as opener:
                with self.assertRaises(SecurityError):
                    atomic_private_write(destination, b"content")
        opener.assert_not_called()

    def test_windows_parent_open_and_unlink_refuse_before_filesystem_access(self) -> None:
        parent = Path("C:/state")
        with mock.patch("laneorchestrator.security.os.name", "nt"):
            with mock.patch("laneorchestrator.security.os.open") as opener:
                with self.assertRaises(SecurityError):
                    open_parent_directory_nofollow(parent)
            with mock.patch("laneorchestrator.security.os.stat") as inspector:
                with self.assertRaises(SecurityError):
                    unlink_regular_nofollow_at_if_present(10, "temporary")
        opener.assert_not_called()
        inspector.assert_not_called()

    def test_windows_lock_open_refuses_before_filesystem_access(self) -> None:
        with mock.patch("laneorchestrator.security.os.name", "nt"):
            with mock.patch("laneorchestrator.security.os.open") as opener:
                with self.assertRaises(SecurityError):
                    open_private_lock_at(10)
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
