from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.private_static_analysis import main


class PrivateStaticAnalysisFailureTests(unittest.TestCase):
    """Regression coverage for interpreter-level AST failures.

    These tests exercise the command boundary so an analysis crash cannot turn
    into a successful-looking or missing CI artifact.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="laneorchestrator-analysis-failure-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, output: Path) -> tuple[int, str]:
        stderr = io.StringIO()
        with mock.patch("scripts.private_static_analysis._workspace_root", return_value=self.root):
            with contextlib.redirect_stderr(stderr):
                result = main(("--source", "source", "--output", str(output)))
        return result, stderr.getvalue()

    def _assert_closed_failure(self, first: Path, second: Path) -> None:
        first_code, first_stderr = self._run(first)
        second_code, second_stderr = self._run(second)

        self.assertEqual(first_code, 2)
        self.assertEqual(second_code, 2)
        self.assertNotIn("Traceback", first_stderr)
        self.assertNotIn("Traceback", second_stderr)
        self.assertGreater(first.stat().st_size, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())

        payload = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], "2.1.0")
        self.assertEqual(len(payload["runs"]), 1)
        results = payload["runs"][0]["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ruleId"], "python/analysis-failure")

    def test_deep_but_valid_expression_fails_closed_with_deterministic_sarif(self) -> None:
        # Around 4 KiB and syntactically valid, but intentionally deeper than
        # the recursive stdlib AST visitor can safely traverse on supported
        # CPython versions.
        expression = " + ".join("1" for _ in range(1000))
        self.assertGreaterEqual(len(expression), 3996)
        (self.source / "deep.py").write_text("value = {0}\n".format(expression), encoding="utf-8")

        self._assert_closed_failure(self.root / "first.sarif", self.root / "second.sarif")

    def test_parser_resource_failures_fail_closed_at_command_boundary(self) -> None:
        (self.source / "clean.py").write_text("value = 1\n", encoding="utf-8")

        for error_type in (SystemError, OverflowError):
            with self.subTest(error_type=error_type.__name__):
                with mock.patch(
                    "scripts.private_static_analysis.ast.parse",
                    side_effect=error_type("simulated parser limit"),
                ):
                    self._assert_closed_failure(
                        self.root / ("{0}-first.sarif".format(error_type.__name__)),
                        self.root / ("{0}-second.sarif".format(error_type.__name__)),
                    )

    def test_visitor_resource_failures_fail_closed_at_command_boundary(self) -> None:
        (self.source / "clean.py").write_text("value = 1\n", encoding="utf-8")

        for error_type in (SystemError, OverflowError):
            with self.subTest(error_type=error_type.__name__):
                with mock.patch(
                    "scripts.private_static_analysis.SecurityVisitor.visit",
                    side_effect=error_type("simulated visitor limit"),
                ):
                    self._assert_closed_failure(
                        self.root / ("visitor-{0}-first.sarif".format(error_type.__name__)),
                        self.root / ("visitor-{0}-second.sarif".format(error_type.__name__)),
                    )

    def test_ast_memory_error_writes_deterministic_failure_evidence(self) -> None:
        (self.source / "clean.py").write_text("value = 1\n", encoding="utf-8")
        with mock.patch("scripts.private_static_analysis.ast.walk", side_effect=MemoryError("simulated")):
            self._assert_closed_failure(self.root / "memory-first.sarif", self.root / "memory-second.sarif")


if __name__ == "__main__":
    unittest.main()
