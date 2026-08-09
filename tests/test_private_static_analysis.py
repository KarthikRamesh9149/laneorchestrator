from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.private_static_analysis import ScannerError, analyze, main, sarif


class PrivateStaticAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-private-static-analysis-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_detects_high_confidence_alias_aware_patterns(self) -> None:
        (self.source / "unsafe.py").write_text(
            "import pickle\nimport ssl\nimport subprocess as sp\n\n"
            "def unsafe(payload):\n"
            "    eval(payload)\n"
            "    sp.run('echo unsafe', shell=True)\n"
            "    pickle.loads(payload)\n"
            "    return ssl._create_unverified_context()\n",
            encoding="utf-8",
        )

        findings, scanned = analyze(("source",), workspace=self.root)

        self.assertEqual(scanned, ("source/unsafe.py",))
        self.assertEqual(
            {finding.rule_id for finding in findings},
            {
                "python/dynamic-code-execution",
                "python/subprocess-shell-true",
                "python/unsafe-deserialization",
                "python/tls-verification-disabled",
            },
        )

    def test_clean_source_produces_deterministic_nonempty_sarif_and_success(self) -> None:
        (self.source / "clean.py").write_text(
            "def greeting(name: str) -> str:\n    return 'hello ' + name\n",
            encoding="utf-8",
        )
        first = self.root / "first.sarif"
        second = self.root / "second.sarif"

        with mock.patch("scripts.private_static_analysis._workspace_root", return_value=self.root):
            self.assertEqual(main(("--source", "source", "--output", str(first))), 0)
            self.assertEqual(main(("--source", "source", "--output", str(second))), 0)

        payload = json.loads(first.read_text(encoding="utf-8"))
        self.assertGreater(first.stat().st_size, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(payload["version"], "2.1.0")
        self.assertEqual(payload["runs"][0]["results"], [])
        self.assertEqual(payload["runs"][0]["artifacts"], [{"location": {"uri": "source/clean.py"}}])

    def test_findings_make_the_gate_fail_after_writing_sarif(self) -> None:
        (self.source / "unsafe.py").write_text("eval('1 + 1')\n", encoding="utf-8")
        output = self.root / "result.sarif"

        with mock.patch("scripts.private_static_analysis._workspace_root", return_value=self.root):
            self.assertEqual(main(("--source", "source", "--output", str(output))), 1)

        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["runs"][0]["results"][0]["ruleId"], "python/dynamic-code-execution")

    def test_sarif_keeps_sorted_rules_when_no_findings_exist(self) -> None:
        payload = sarif((), ())
        rules = payload["runs"][0]["tool"]["driver"]["rules"]
        self.assertEqual([rule["id"] for rule in rules], sorted(rule["id"] for rule in rules))

    @unittest.skipUnless(os.name == "posix", "symbolic-link source boundary is POSIX-specific")
    def test_rejects_a_symbolic_link_source_root(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "source.py").write_text("pass\n", encoding="utf-8")
        (self.root / "linked-source").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ScannerError, "contains symbolic link"):
            analyze(("linked-source",), workspace=self.root)

    @unittest.skipUnless(os.name == "posix", "symbolic-link source boundary is POSIX-specific")
    def test_rejects_symbolic_links_anywhere_in_the_tree(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "outside.py").write_text("pass\n", encoding="utf-8")
        nested = self.source / "nested"
        nested.mkdir()
        (nested / "clean.py").write_text("pass\n", encoding="utf-8")
        (nested / "linked-file.txt").symlink_to(outside / "outside.py")

        with self.assertRaisesRegex(ScannerError, "contains symbolic link"):
            analyze(("source",), workspace=self.root)

        (nested / "linked-file.txt").unlink()
        (nested / "linked-directory").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ScannerError, "contains symbolic link"):
            analyze(("source",), workspace=self.root)

    def test_fails_closed_for_entry_and_depth_limits(self) -> None:
        for name in ("one.py", "two.py", "three.py"):
            (self.source / name).write_text("pass\n", encoding="utf-8")

        with mock.patch("scripts.private_static_analysis.MAX_TREE_ENTRIES", 2):
            with self.assertRaisesRegex(ScannerError, "entry limit"):
                analyze(("source",), workspace=self.root)

        for name in ("one.py", "two.py", "three.py"):
            (self.source / name).unlink()
        deep = self.source / "one" / "two"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("pass\n", encoding="utf-8")
        with mock.patch("scripts.private_static_analysis.MAX_DIRECTORY_DEPTH", 1):
            with self.assertRaisesRegex(ScannerError, "directory depth"):
                analyze(("source",), workspace=self.root)

    def test_empty_source_writes_deterministic_failure_sarif(self) -> None:
        first = self.root / "first.sarif"
        second = self.root / "second.sarif"

        with mock.patch("scripts.private_static_analysis._workspace_root", return_value=self.root):
            self.assertEqual(main(("--source", "source", "--output", str(first))), 2)
            self.assertEqual(main(("--source", "source", "--output", str(second))), 2)

        self.assertEqual(first.read_bytes(), second.read_bytes())
        payload = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], "2.1.0")
        self.assertEqual(payload["runs"][0]["results"][0]["ruleId"], "python/analysis-failure")

    def test_unreadable_source_fails_closed_and_writes_failure_sarif(self) -> None:
        (self.source / "blocked.py").write_text("pass\n", encoding="utf-8")
        output = self.root / "failure.sarif"

        with mock.patch("scripts.private_static_analysis._workspace_root", return_value=self.root):
            with mock.patch("scripts.private_static_analysis.os.open", side_effect=PermissionError("blocked")):
                self.assertEqual(main(("--source", "source", "--output", str(output))), 2)

        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["runs"][0]["results"][0]["ruleId"], "python/analysis-failure")


if __name__ == "__main__":
    unittest.main()
