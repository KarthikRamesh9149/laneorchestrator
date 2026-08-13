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
import contextlib
from unittest import mock
from pathlib import Path, PurePosixPath

from scripts.build_release import (
    MAX_MEMBERS,
    RELEASE_BINARY_FILES,
    RELEASE_FILES,
    RELEASE_EXECUTABLES,
    RELEASE_TREES,
    ReleaseError,
    archive_members,
    build_release,
    validate_release_members,
    _validate_canonical_name,
)
from scripts.check_docs import check_docs
from scripts.check_manifests import check_manifests
from scripts import healthcheck
from scripts.verify_release import (
    MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    ReleaseVerificationError,
    _parse_sums,
    _check_content,
    _validate_name,
    _zip_entry_count,
    _tar_members,
    main as verify_main,
    verify_release,
)


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
                relative = member.name.split("/", 1)[1]
                self.assertEqual(member.mode, 0o755 if relative in RELEASE_EXECUTABLES else 0o644)
        with zipfile.ZipFile(first.zip_path) as archive:
            for member in archive.infolist():
                relative = member.filename.split("/", 1)[1]
                mode = (member.external_attr >> 16) & 0o777777
                expected = 0o100000 | (0o755 if relative in RELEASE_EXECUTABLES else 0o644)
                self.assertEqual(mode, expected)

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

        credential = b"Bearer " + b"abcdefghijklmnopqrstuvwxyz"
        self._replace_tar_member(release.tar_path, "laneorchestrator-0.2.3/README.md", credential + b"\n")
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

    def test_windows_unsafe_names_and_canonical_collisions_are_rejected(self) -> None:
        prefix = "laneorchestrator-0.2.3"
        for relative in ("docs/CON.txt", "docs/name.", "docs/name ", "docs/colon:name.md", "docs/LPT9.log", "docs/COM¹.txt", "docs/LPT².txt"):
            with self.subTest(relative=relative):
                with self.assertRaises(ReleaseError):
                    _validate_canonical_name(relative)
                with self.assertRaises(ReleaseVerificationError):
                    _validate_name(prefix + "/" + relative, prefix)
        first = self.root / "docs" / "case.txt"
        second = self.root / "docs" / "CASE.txt"
        first.write_text("a\n", encoding="utf-8")
        second.write_text("b\n", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseError, "duplicate"):
            validate_release_members(self.root, (first, second))

    def test_verifier_requires_exact_gzip_header_and_rejects_runtime_secrets_paths(self) -> None:
        release = build_release(self.root, self.output_one)
        original = bytearray(release.tar_path.read_bytes())
        self.assertEqual(bytes(original[:10]), b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff")
        for position, value in ((8, 0), (9, 3)):
            with self.subTest(position=position):
                mutated = bytearray(original)
                mutated[position] = value
                release.tar_path.write_bytes(mutated)
                self._rewrite_sums(self.output_one)
                with self.assertRaisesRegex(ReleaseVerificationError, "gzip header"):
                    verify_release(self.output_one, root=self.root)
        detector_fixture = b"sk" + b"-proj-" + b"a" * 24
        (self.root / "README.md").write_bytes(detector_fixture + b"\n")
        release = build_release(self.root, self.output_two)
        with self.assertRaisesRegex(ReleaseVerificationError, "credential-like"):
            verify_release(self.output_two, root=self.root)
        local_path = "/private" + "/var/folders/example-user/cache"
        (self.root / "README.md").write_text(local_path + "\n", encoding="utf-8")
        local_output = self.work / "local"
        release = build_release(self.root, local_output)
        with self.assertRaisesRegex(ReleaseVerificationError, "local path"):
            verify_release(local_output, root=self.root)

    def test_verifier_rejects_trailing_gzip_and_tar_payload_data(self) -> None:
        """Checksums alone must not bless bytes hidden after the source archive."""

        release = build_release(self.root, self.output_one)
        original = release.tar_path.read_bytes()
        for suffix in (
            b"untrusted-trailing-data",
            b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        ):
            with self.subTest(suffix=suffix[:4]):
                release.tar_path.write_bytes(original + suffix)
                self._rewrite_sums(self.output_one)
                with self.assertRaisesRegex(ReleaseVerificationError, "trailing"):
                    verify_release(self.output_one, root=self.root)

        tar_payload = bytearray(gzip.decompress(original))
        tar_payload[-1024:-1000] = b"hidden-after-end-of-archive"
        with release.tar_path.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                compressed.write(tar_payload)
        self._rewrite_sums(self.output_one)
        with self.assertRaisesRegex(ReleaseVerificationError, "trailing"):
            verify_release(self.output_one, root=self.root)

    def test_secret_scanner_has_bounded_high_confidence_patterns(self) -> None:
        values = (
            "github_pat_" + "a" * 24,
            "sk-ant-" + "a" * 24,
            "glpat-" + "a" * 24,
            "sk_live_" + "a" * 24,
            "xoxb-" + "a" * 24,
        )
        for value in values:
            with self.subTest(value=value[:8]):
                with self.assertRaisesRegex(ReleaseVerificationError, "credential-like"):
                    _check_content("README.md", value.encode("ascii"))

    def test_verifier_accepts_only_the_declared_bounded_demo_gif(self) -> None:
        name = next(iter(RELEASE_BINARY_FILES))
        content = (ROOT / name).read_bytes()
        _check_content(name, content)
        with self.assertRaisesRegex(ReleaseVerificationError, "not UTF-8"):
            _check_content("docs/assets/undeclared.gif", content)
        mutations = (
            b"BAD89a" + content[6:],
            content[:6] + (1).to_bytes(2, "little") + content[8:],
            content.replace(b"NETSCAPE2.0", b"NOT-A-LOOP!", 1),
        )
        for mutation in mutations:
            with self.subTest(prefix=mutation[:12]):
                with self.assertRaisesRegex(ReleaseVerificationError, "GIF"):
                    _check_content(name, mutation)

    def test_fresh_trusted_archive_extracts_and_runs_the_complete_validator(self) -> None:
        if os.environ.get("LANEORCHESTRATOR_EXTRACTED_VALIDATION") == "1":
            self.skipTest("nested extracted validation is intentionally single-depth")
        release = build_release(self.root, self.output_one)
        verify_release(self.output_one, root=self.root)
        extracted = self.work / "extracted"
        extracted.mkdir()
        with tarfile.open(release.tar_path) as archive:
            # The archive was freshly built and verified above; do not use this
            # extraction pattern for an arbitrary user-supplied archive.
            archive.extractall(extracted)
        root = extracted / "laneorchestrator-0.2.3"
        result = subprocess.run(
            ["sh", "scripts/validate.sh"], cwd=root, text=True,
            capture_output=True, check=False,
            env=dict(os.environ, LANEORCHESTRATOR_EXTRACTED_VALIDATION="1"),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        child_output = result.stdout + result.stderr
        self.assertIn("test_fresh_trusted_archive_extracts_and_runs_the_complete_validator", child_output)
        self.assertIn("skipped", child_output)

    def test_zip_preflight_and_cli_errors_are_bounded_and_structured(self) -> None:
        eocd = b"PK\x05\x06" + b"\0\0\0\0" + (513).to_bytes(2, "little") * 2 + b"\0" * 10
        with self.assertRaisesRegex(ReleaseVerificationError, "entry limit"):
            _zip_entry_count(eocd)
        with mock.patch("scripts.build_release.build_release", side_effect=OSError("read-only")):
            from scripts.build_release import main as build_main
            self.assertEqual(build_main(["--output", str(self.output_one)]), 2)
        self.assertEqual(verify_main([str(self.work / "missing"), "--root", str(self.root)]), 1)

    def test_archive_walk_and_archive_preflights_fail_before_unbounded_work(self) -> None:
        """Catch removal of the traversal, gzip, or central-directory bounds."""

        for index in range(MAX_MEMBERS + 1):
            (self.root / "docs" / "fanout-{0}".format(index)).mkdir()
        with self.assertRaisesRegex(ReleaseError, "traversal"):
            archive_members(self.root)

        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            for index in range(13):
                info = tarfile.TarInfo("laneorchestrator-0.2.3/file-{0}".format(index))
                info.size = 1024 * 1024
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(b"\0" * info.size))
        compressed = gzip.compress(payload.getvalue(), mtime=0)
        with self.assertRaisesRegex(ReleaseVerificationError, "decompression"):
            _tar_members(compressed, "laneorchestrator-0.2.3")

        central_directory = b"x" * (MAX_ZIP_CENTRAL_DIRECTORY_BYTES + 1)
        eocd = (
            b"PK\x05\x06" + b"\0\0\0\0" + (1).to_bytes(2, "little") * 2
            + len(central_directory).to_bytes(4, "little") + b"\0\0\0\0" + b"\0\0"
        )
        with self.assertRaisesRegex(ReleaseVerificationError, "central directory"):
            _zip_entry_count(central_directory + eocd)

    def test_distribution_entry_limit_is_enforced_without_archive_parsing(self) -> None:
        release = build_release(self.root, self.output_one)
        for index in range(3):
            (self.output_one / "extra-{0}".format(index)).write_text("x", encoding="ascii")
        with self.assertRaisesRegex(ReleaseVerificationError, "unexpected"):
            verify_release(self.output_one, root=self.root)

    def test_verifier_inspects_zip_independently_and_requires_identical_content(self) -> None:
        release = build_release(self.root, self.output_one)
        self._replace_zip_member(release.zip_path, "laneorchestrator-0.2.3/README.md", b"changed zip only\n")
        self._rewrite_sums(self.output_one)
        with self.assertRaisesRegex(ReleaseVerificationError, "differs"):
            verify_release(self.output_one, root=self.root)

    def test_verifier_binds_zip_local_headers_to_central_directory(self) -> None:
        release = build_release(self.root, self.output_one)
        payload = bytearray(release.zip_path.read_bytes())
        local_header = payload.index(b"PK\x03\x04")
        flags_offset = local_header + 6
        flags = int.from_bytes(payload[flags_offset:flags_offset + 2], "little")
        payload[flags_offset:flags_offset + 2] = (flags | 0x800).to_bytes(2, "little")
        release.zip_path.write_bytes(payload)
        self._rewrite_sums(self.output_one)
        with self.assertRaisesRegex(ReleaseVerificationError, "local header differs"):
            verify_release(self.output_one, root=self.root)

    def test_checksum_parser_rejects_order_duplicates_and_garbage(self) -> None:
        names = ("laneorchestrator-0.2.3.tar.gz", "laneorchestrator-0.2.3.zip")
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
            benchmark = "laneorchestrator-0.2.3/benchmarks/README.md"
            self.assertIn(benchmark, names)
            self.assertIn("laneorchestrator-0.2.3/docs/benchmarks.md", names)
            self.assertIn("laneorchestrator-0.2.3/scripts/validate.sh", names)
            self.assertIn("laneorchestrator-0.2.3/scripts/private_static_analysis.py", names)
            self.assertIn("laneorchestrator-0.2.3/skills/laneorchestrator/scripts/catalog.py", names)
            self.assertIn("laneorchestrator-0.2.3/skills/laneorchestrator/scripts/route.py", names)
            self.assertIn("laneorchestrator-0.2.3/.github/workflows/security.yml", names)
            self.assertIn("laneorchestrator-0.2.3/tests/test_release_tools.py", names)
            self.assertIn("laneorchestrator-0.2.3/.github/workflows/ci.yml", names)
            prefix = "laneorchestrator-0.2.3/"
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
            commands = ("scripts/healthcheck.py", "scripts/validate.sh", "scripts/install-agents.sh")
            for command in commands:
                self.assertIn(prefix + command, names)

    def test_document_and_manifest_checks_report_deterministic_failures(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n[broken](missing.md)\n", encoding="utf-8")
        self.assertEqual(check_docs(self.root), ["README.md: broken relative link (missing.md)"])
        readme.write_text(readme.read_text(encoding="utf-8").replace("[broken](missing.md)\n", ""), encoding="utf-8")
        manifest = self.root / "plugin.json"
        manifest.write_text("{", encoding="utf-8")
        self.assertEqual(check_manifests(self.root), ["plugin.json: invalid JSON"])

    def test_manifest_and_release_identity_reject_duplicate_json_keys(self) -> None:
        manifest = self.root / "plugin.json"
        original = manifest.read_text(encoding="utf-8")
        manifest.write_text(original.replace('"version": "0.2.3",', '"version": "0.0.1",\n  "version": "0.2.3",', 1), encoding="utf-8")
        self.assertEqual(check_manifests(self.root), ["plugin.json: duplicate JSON key (version)"])
        with self.assertRaisesRegex(ReleaseError, "duplicate JSON key"):
            build_release(self.root, self.output_one)

    def test_healthcheck_rejects_duplicate_json_keys(self) -> None:
        manifest = self.root / ".codex-plugin" / "plugin.json"
        original = manifest.read_text(encoding="utf-8")
        manifest.write_text(original.replace('"version": "0.2.3",', '"version": "0.0.1",\n  "version": "0.2.3",', 1), encoding="utf-8")
        output = io.StringIO()
        with mock.patch.object(healthcheck, "ROOT", self.root), \
                mock.patch.object(healthcheck, "REQUIRED", (manifest,)), \
                mock.patch.object(healthcheck, "EXPECTED_MODELS", {}), \
                contextlib.redirect_stdout(output):
            self.assertEqual(healthcheck.main(), 1)
        self.assertIn("duplicate JSON key (version)", output.getvalue())

    @unittest.skipUnless(os.name == "posix", "symbolic links are POSIX-specific")
    def test_document_validator_rejects_symlinked_content_without_reading_it(self) -> None:
        outside = self.work / "outside.md"
        outside.write_text("safe\n", encoding="utf-8")
        (self.root / "docs" / "linked.md").symlink_to(outside)
        self.assertEqual(check_docs(self.root), ["docs/linked.md: symbolic links are not allowed"])

    def test_check_scripts_return_one_for_invalid_public_roots(self) -> None:
        credential = "Bearer " + "abcdefghijklmnopqrstuvwxyz"
        (self.root / "README.md").write_text(credential + "\n", encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, "scripts/check_docs.py", "--root", str(self.root)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(checked.stderr, "README.md: credential-like content\n")

    def test_verifier_rejects_duplicate_link_and_extra_archive_members(self) -> None:
        release = build_release(self.root, self.output_one)
        self._append_tar_member(release.tar_path, "laneorchestrator-0.2.3/README.md", b"duplicate")
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
        for name in ("laneorchestrator-0.2.3.tar.gz", "laneorchestrator-0.2.3.zip"):
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
                        info.mode = self._archive_mode(name)
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
                        info.mode = self._archive_mode(member_name)
                        archive.addfile(info, io.BytesIO(payload))

    def _replace_zip_member(self, path: Path, target: str, content: bytes) -> None:
        with zipfile.ZipFile(path, "r") as archive:
            members = [(item.filename, archive.read(item)) for item in archive.infolist()]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100000 | self._archive_mode(name)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content if name == target else payload)

    def _archive_mode(self, name: str) -> int:
        relative = name.split("/", 1)[1]
        return 0o755 if relative in RELEASE_EXECUTABLES else 0o644

    def _write_hostile_dist(self, directory: Path, name: str) -> None:
        version = "0.2.3"
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
