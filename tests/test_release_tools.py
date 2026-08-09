from __future__ import annotations

import gzip
import hashlib
import io
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath

from scripts.build_release import (
    RELEASE_FILES,
    RELEASE_TREES,
    ReleaseError,
    archive_members,
    build_release,
    validate_release_members,
)
from scripts.check_docs import check_docs
from scripts.check_manifests import check_manifests
from scripts.verify_release import ReleaseVerificationError, _parse_sums, verify_release


ROOT = Path(__file__).resolve().parents[1]


class ReleaseToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name)
        self.root = self.work / "source"
        self.output_one = self.work / "one"
        self.output_two = self.work / "two"
        self.root.mkdir()
        for relative in RELEASE_FILES:
            source = ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for tree in RELEASE_TREES:
            source = ROOT / tree
            destination = self.root / tree
            shutil.copytree(source, destination)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_release_archives_are_reproducible_and_path_safe(self) -> None:
        first = build_release(self.root, self.output_one)
        second = build_release(self.root, self.output_two)
        self.assertEqual(first.sha256, second.sha256)
        verify_release(self.output_one, root=self.root)
        with tarfile.open(first.tar_path) as archive:
            for member in archive.getmembers():
                self.assertFalse(member.name.startswith("/"))
                self.assertNotIn("..", PurePosixPath(member.name).parts)
                self.assertFalse(member.issym() or member.islnk())
                self.assertTrue(member.isfile())
                self.assertEqual(member.mode, 0o644)

    def test_source_validation_rejects_links_duplicates_missing_and_escapes(self) -> None:
        valid = self.root / "README.md"
        with self.assertRaisesRegex(ReleaseError, "duplicate"):
            validate_release_members(self.root, (valid, valid))
        with self.assertRaisesRegex(ReleaseError, "missing"):
            validate_release_members(self.root, (self.root / "missing",))
        with self.assertRaisesRegex(ReleaseError, "outside"):
            validate_release_members(self.root, (self.work / "outside",))
        if os.name == "posix":
            link = self.root / "linked-readme"
            link.symlink_to(valid)
            with self.assertRaisesRegex(ReleaseError, "link"):
                validate_release_members(self.root, (link,))

    def test_verifier_rejects_checksum_mismatch_extra_files_secrets_and_versions(self) -> None:
        release = build_release(self.root, self.output_one)
        sums = release.sums_path.read_text(encoding="ascii")
        release.sums_path.write_text("0" * 64 + sums[64:], encoding="ascii")
        with self.assertRaisesRegex(ReleaseVerificationError, "checksum"):
            verify_release(self.output_one, root=self.root)

        release = build_release(self.root, self.output_two)
        (self.output_two / "extra.txt").write_text("unexpected\n", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseVerificationError, "unexpected"):
            verify_release(self.output_two, root=self.root)
        (self.output_two / "extra.txt").unlink()

        self._replace_tar_member(release.tar_path, "laneorchestrator-0.2.0/README.md", b"Bearer abcdefghijklmnopqrstuvwxyz\n")
        self._rewrite_sums(self.output_two)
        with self.assertRaisesRegex(ReleaseVerificationError, "content"):
            verify_release(self.output_two, root=self.root)

    def test_verifier_rejects_hostile_tar_and_zip_member_names(self) -> None:
        for name in ("../escape", "/absolute", "C:/drive", "a\\backslash"):
            with self.subTest(name=name):
                directory = self.work / hashlib.sha256(name.encode()).hexdigest()
                directory.mkdir()
                self._write_hostile_dist(directory, name)
                with self.assertRaises(ReleaseVerificationError):
                    verify_release(directory, root=self.root)

    def test_verifier_inspects_zip_independently_and_requires_identical_content(self) -> None:
        release = build_release(self.root, self.output_one)
        self._replace_zip_member(release.zip_path, "laneorchestrator-0.2.0/README.md", b"changed zip only\n")
        self._rewrite_sums(self.output_one)
        with self.assertRaisesRegex(ReleaseVerificationError, "differs"):
            verify_release(self.output_one, root=self.root)

    def test_checksum_parser_rejects_order_duplicates_and_garbage(self) -> None:
        names = ("laneorchestrator-0.2.0.tar.gz", "laneorchestrator-0.2.0.zip")
        digest = "a" * 64
        for content in (
            "{0}  {2}\n{0}  {1}\n".format(digest, names[0], names[1]),
            "{0}  {1}\n{0}  {1}\n".format(digest, names[0]),
            "{0} {1}\n{0}  {2}\n".format(digest, names[0], names[1]),
            "{0}  {1}\n{0}  {2}\nextra\n".format(digest, names[0], names[1]),
        ):
            with self.subTest(content=content):
                with self.assertRaises(ReleaseVerificationError):
                    _parse_sums(content.encode("ascii"), names)

    def test_output_inside_source_and_source_hardlinks_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReleaseError, "outside"):
            build_release(self.root, self.root / "docs" / "dist")
        if os.name == "posix":
            source = self.root / "README.md"
            copy = self.root / "README-copy.md"
            os.link(source, copy)
            with self.assertRaisesRegex(ReleaseError, "multiple links"):
                validate_release_members(self.root, (source,))

    def test_archived_markdown_links_resolve_inside_the_archive(self) -> None:
        release = build_release(self.root, self.output_one)
        with tarfile.open(release.tar_path) as archive:
            payloads = {
                member.name: archive.extractfile(member).read()
                for member in archive.getmembers()
            }
            names = set(payloads)
            benchmark = "laneorchestrator-0.2.0/benchmarks/README.md"
            self.assertIn(benchmark, names)
            self.assertIn("laneorchestrator-0.2.0/docs/benchmarks.md", names)
            prefix = "laneorchestrator-0.2.0/"
            for name, content in payloads.items():
                if not name.endswith(".md"):
                    continue
                for target in re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", content.decode("utf-8")):
                    target = target.strip().split("#", 1)[0]
                    if not target or "://" in target or target.startswith("mailto:"):
                        continue
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                    self.assertTrue(resolved.startswith(prefix), "{0} -> {1}".format(name, target))
                    self.assertIn(resolved, names, "{0} -> {1}".format(name, target))

    def test_document_and_manifest_checks_report_deterministic_failures(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n[broken](missing.md)\n", encoding="utf-8")
        self.assertEqual(check_docs(self.root), ["README.md: broken relative link (missing.md)"])
        readme.write_text(readme.read_text(encoding="utf-8").replace("[broken](missing.md)\n", ""), encoding="utf-8")
        manifest = self.root / "plugin.json"
        manifest.write_text("{", encoding="utf-8")
        self.assertEqual(check_manifests(self.root), ["plugin.json: invalid JSON"])

    def test_check_scripts_return_one_for_invalid_public_roots(self) -> None:
        (self.root / "README.md").write_text("Bearer abcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, "scripts/check_docs.py", "--root", str(self.root)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(checked.stderr, "README.md: credential-like content\n")

    def test_verifier_rejects_duplicate_link_and_extra_archive_members(self) -> None:
        release = build_release(self.root, self.output_one)
        self._append_tar_member(release.tar_path, "laneorchestrator-0.2.0/README.md", b"duplicate")
        self._rewrite_sums(self.output_one)
        with self.assertRaisesRegex(ReleaseVerificationError, "duplicate"):
            verify_release(self.output_one, root=self.root)

    def test_archive_members_are_only_allowlisted_regular_files(self) -> None:
        members = archive_members(self.root)
        self.assertTrue(members)
        root = self.root.resolve()
        self.assertEqual(members, sorted(members, key=lambda item: item.relative_to(root).as_posix()))
        self.assertTrue(all(member.is_file() and not member.is_symlink() for member in members))

    def _rewrite_sums(self, directory: Path) -> None:
        rows = []
        for name in ("laneorchestrator-0.2.0.tar.gz", "laneorchestrator-0.2.0.zip"):
            rows.append("{0}  {1}".format(hashlib.sha256((directory / name).read_bytes()).hexdigest(), name))
        (directory / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="ascii")

    def _replace_tar_member(self, path: Path, target: str, content: bytes) -> None:
        members = []
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                payload = archive.extractfile(member).read()  # type: ignore[union-attr]
                members.append((member.name, payload))
        with path.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(mode="w", fileobj=compressed, format=tarfile.PAX_FORMAT) as archive:
                    for name, payload in members:
                        info = tarfile.TarInfo(name)
                        info.size = len(content if name == target else payload)
                        info.mtime = 0
                        info.mode = 0o644
                        archive.addfile(info, io.BytesIO(content if name == target else payload))

    def _append_tar_member(self, path: Path, name: str, content: bytes) -> None:
        self._replace_tar_member(path, "not-present", b"")
        with tarfile.open(path, "r:gz") as archive:
            members = [(item.name, archive.extractfile(item).read()) for item in archive.getmembers()]  # type: ignore[union-attr]
        with path.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(mode="w", fileobj=compressed) as archive:
                    for member_name, payload in members + [(name, content)]:
                        info = tarfile.TarInfo(member_name)
                        info.size = len(payload)
                        info.mode = 0o644
                        archive.addfile(info, io.BytesIO(payload))

    def _replace_zip_member(self, path: Path, target: str, content: bytes) -> None:
        with zipfile.ZipFile(path, "r") as archive:
            members = [(item.filename, archive.read(item)) for item in archive.infolist()]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content if name == target else payload)

    def _write_hostile_dist(self, directory: Path, name: str) -> None:
        version = "0.2.0"
        tar_path = directory / "laneorchestrator-{0}.tar.gz".format(version)
        zip_path = directory / "laneorchestrator-{0}.zip".format(version)
        with tar_path.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(mode="w", fileobj=compressed) as archive:
                    info = tarfile.TarInfo(name)
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b"x"))
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(name, b"x")
        self._rewrite_sums(directory)


if __name__ == "__main__":
    unittest.main()
