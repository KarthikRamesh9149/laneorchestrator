from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts import benchmark_workflows as workflow


class WorkflowFixtureTests(unittest.TestCase):
    def test_success_requires_every_arm_and_review_approval(self):
        tasks = [{'id': 'task', 'expected_routing': {'independent_review': True}}]
        report = {'executions': [dict(task_id='task', arm=arm,
                    verification={'task_passed': True}, call={'exit_code': 0, 'timed_out': False})
                    for arm in ('adaptive', 'fixed')],
                  'independent_review': {'call': {'exit_code': 0}, 'review_workspace_unchanged': True,
                    'payload': {'reviews': [{'task_id': 'task', 'arm_a': {'verdict': 'approve', 'findings': []},
                                             'arm_b': {'verdict': 'approve', 'findings': []}}]}}}
        self.assertTrue(workflow._successful_comparison(tasks, report, True))
        report['executions'][1]['verification']['task_passed'] = False
        self.assertFalse(workflow._successful_comparison(tasks, report, True))
        report['executions'][1]['verification']['task_passed'] = True
        report['independent_review']['payload']['reviews'][0]['arm_b']['verdict'] = 'changes-requested'
        self.assertFalse(workflow._successful_comparison(tasks, report, True))

    @classmethod
    def setUpClass(cls):
        cls.tasks = workflow.load_tasks()
        cls.calibration = workflow.load_calibration()

    def test_corpus_is_three_distinct_repository_provenance_fixtures(self):
        self.assertEqual([task["category"] for task in self.tasks], ["bug", "feature", "refactor"])
        commits = {task["provenance"]["commit"] for task in self.tasks}
        self.assertEqual(len(commits), 1)
        commit = next(iter(commits))
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertTrue(all(task["provenance"]["repository"].startswith("https://github.com/")
                            and task["provenance"]["source_paths"] for task in self.tasks))
        if (workflow.ROOT / ".git").exists():
            resolved = subprocess.run(
                ["git", "cat-file", "-e", commit + "^{commit}"], cwd=workflow.ROOT,
                capture_output=True,
            )
            self.assertEqual(resolved.returncode, 0)
        self.assertTrue(all(any(marker in task["provenance"]["adaptation"].casefold()
                                for marker in ("fixture", "benchmark")) for task in self.tasks))

    def test_router_prompt_withholds_authored_rubrics_and_external_tests(self):
        prompt = workflow.routing_prompt(self.tasks, self.calibration)
        self.assertNotIn("expected_routing", prompt)
        self.assertNotIn("test_hashes", prompt)
        self.assertNotIn("test_json_guard.py", prompt)
        self.assertNotIn("Findings cite exact changed files and triggers", prompt)
        self.assertIn('"id": "U006"', prompt)

    def test_validated_route_accepts_small_mechanical_refactor_and_u006_review(self):
        payload = {
            "decisions": [
                {"id": "bug-json-duplicates", "task_kind": "routine", "model": "gpt-5.6-terra",
                 "reasoning_effort": "medium", "independent_review": True, "reason": "Trust boundary."},
                {"id": "feature-capability-ranking", "task_kind": "routine", "model": "gpt-5.6-sol",
                 "reasoning_effort": "low", "independent_review": False, "reason": "Bounded feature."},
                {"id": "refactor-route-summary", "task_kind": "small", "model": "gpt-5.6-luna",
                 "reasoning_effort": "high", "independent_review": False, "reason": "Mechanical extraction."},
            ],
            "calibration": {
                "id": "U006", "task_kind": "review", "model": "gpt-5.6-sol",
                "reasoning_effort": "high", "independent_review": False, "action": "review",
                "reason": "Read-only regression review.",
                "output_checks": ["Cite changed files", "Assess responsive state"],
            },
        }
        rows = workflow.validate_decisions(payload, self.tasks)
        self.assertEqual(len(rows), 3)
        self.assertEqual(workflow.validate_calibration(payload["calibration"], self.calibration)["action"], "review")

    def test_policy_valid_route_preserves_authored_rubric_mismatch(self):
        payload = {
            "decisions": [
                {"id": "bug-json-duplicates", "task_kind": "small", "model": "gpt-5.6-terra",
                 "reasoning_effort": "high", "independent_review": False, "reason": "Fixture appears small."},
                {"id": "feature-capability-ranking", "task_kind": "routine", "model": "gpt-5.6-terra",
                 "reasoning_effort": "medium", "independent_review": False, "reason": "Routine feature."},
                {"id": "refactor-route-summary", "task_kind": "small", "model": "gpt-5.6-luna",
                 "reasoning_effort": "high", "independent_review": False, "reason": "Small refactor."},
            ], "calibration": {},
        }
        rows = workflow.validate_decisions(payload, self.tasks)
        bug = next(row for row in rows if row["id"] == "bug-json-duplicates")
        self.assertFalse(bug["authored_rubric"]["passed"])
        self.assertEqual(len(bug["authored_rubric"]["failures"]), 2)

    def test_router_review_semantics_and_policy_violations_fail_closed(self):
        row = {
            "id": "U006", "task_kind": "review", "model": "gpt-5.6-sol",
            "reasoning_effort": "high", "independent_review": True, "action": "review",
            "reason": "Wrong review flag.", "output_checks": ["One", "Two"],
        }
        with self.assertRaisesRegex(workflow.BenchmarkError, "review semantics"):
            workflow.validate_calibration(row, self.calibration)
        payload = {"decisions": [
            {"id": task["id"], "task_kind": "small", "model": "gpt-5.6-sol",
             "reasoning_effort": "medium", "independent_review": task["expected_routing"]["independent_review"],
             "reason": "Invalid small selection."} for task in self.tasks
        ], "calibration": row}
        payload["decisions"][0]["task_kind"] = "routine"
        payload["decisions"][1]["task_kind"] = "routine"
        with self.assertRaises(ValueError):
            workflow.validate_decisions(payload, self.tasks)

    def test_external_verifier_passes_only_after_real_source_change(self):
        task = next(task for task in self.tasks if task["category"] == "bug")
        original_hashes = dict(task["test_hashes"])
        fixed = '''import json
class DuplicateJSONKeyError(ValueError):
    pass
def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError("duplicate JSON key")
        result[key] = value
    return result
def parse_json_object(data):
    value = json.loads(data, object_pairs_hook=_unique)
    if not isinstance(value, dict):
        raise ValueError("JSON value must be an object")
    return value
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, artifact = root / "work", root / "artifact"
            baseline = workflow._prepare_workspace(task, workspace)
            (workspace / "json_guard.py").write_text(fixed, encoding="utf-8")
            result = workflow._verify_task(task, workspace, artifact, baseline)
            self.assertTrue(result["task_passed"])
            self.assertTrue(result["external_tests_unchanged"])
            self.assertTrue((artifact / "changes.diff").read_text(encoding="utf-8"))
        self.assertEqual(task["test_hashes"], original_hashes)


class WorkflowExecutionSafetyTests(unittest.TestCase):
    def test_event_usage_requires_a_complete_runtime_usage_record(self):
        good = json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 10, "output_tokens": 3, "cached_input_tokens": 4,
        }})
        usage, turns, model, effort = workflow._event_usage(good)
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 3, "cached_input_tokens": 4})
        self.assertEqual((turns, model, effort), (1, None, None))
        self.assertIsNone(workflow._event_usage('{"type":"turn.completed"}')[0])
        for values in (
            {"input_tokens": -1, "output_tokens": 0, "cached_input_tokens": 0},
            {"input_tokens": 1, "output_tokens": 0, "cached_input_tokens": 2},
        ):
            event = json.dumps({"type": "turn.completed", "usage": values})
            self.assertIsNone(workflow._event_usage(event)[0])

    def test_runtime_setting_mismatch_invalidates_call(self):
        self.assertIsNone(workflow._runtime_settings_match("m", "high", None, None))
        self.assertTrue(workflow._runtime_settings_match("m", "high", "m", "high"))
        self.assertFalse(workflow._valid_call({
            "exit_code": 0, "timed_out": False, "runtime_settings_match": False,
        }))

    def test_workspace_inventory_rejects_empty_directories_and_dangling_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.py").write_text("pass\n", encoding="utf-8")
            (root / "empty").mkdir()
            (root / "dangling").symlink_to(root / "missing")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "source.pyc").write_bytes(b"cache")
            unexpected = workflow._workspace_inventory(root, {"source.py"})
        self.assertEqual(unexpected, ["dangling", "empty/"])

    def test_unknown_usage_stops_the_next_launch(self):
        ledger = {"schema_version": 1, "calls": [{
            "id": "call-1", "packet": "one", "agent": "one", "status": "completed", "usage": None,
        }]}
        assessment = workflow.assess_usage(
            ledger, "two", max_calls=workflow.MAX_CALLS, max_retries=0, max_tokens=250_000,
        )
        self.assertFalse(assessment["allowed"])
        self.assertIn("token_usage_unknown", assessment["stop_reasons"])

    def test_budget_resume_keeps_two_calls_and_starts_with_fixed_bug_arm(self):
        tasks = workflow.load_tasks()
        executions = [{"task_id": "bug-json-duplicates", "arm": "adaptive"}]
        self.assertEqual(
            workflow._remaining_execution_sequence(tasks, executions)[0],
            ("bug-json-duplicates", "fixed"),
        )
        ledger = {"schema_version": 1, "calls": [
            {"id": "call-01-router", "packet": "router", "agent": "call-01-router",
             "status": "completed", "usage": {"input_tokens": 41818, "output_tokens": 608,
                                                  "cached_input_tokens": 0}},
            {"id": "call-02-bug-json-duplicates-adaptive", "packet": "bug-json-duplicates-adaptive",
             "agent": "call-02-bug-json-duplicates-adaptive", "status": "completed",
             "usage": {"input_tokens": 286868, "output_tokens": 2531,
                       "cached_input_tokens": 246016}},
        ]}
        assessment = workflow.assess_usage(
            ledger, "bug-json-duplicates-fixed", max_calls=8, max_retries=0, max_tokens=2_000_000,
        )
        self.assertTrue(assessment["allowed"])
        self.assertEqual(assessment["calls"], 2)
        self.assertEqual(assessment["observed_tokens"], 331825)

    def test_call_disables_agent_fanout_and_host_skill_discovery(self):
        captured = {}

        def fake_communicate(command, prompt, timeout, cwd):
            captured["command"] = command
            return 0, json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 5, "output_tokens": 2, "cached_input_tokens": 0,
            }}), "", False

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                workflow, "_communicate", side_effect=fake_communicate):
            root = Path(directory)
            result = workflow._run_call(
                Path(sys.executable), root, "call-1", "packet", root, "gpt-5.6-terra", "medium",
                "prompt", 30, {"schema_version": 1, "calls": []}, 250_000,
            )
        command = captured["command"]
        self.assertIn("multi_agent", command)
        self.assertIn("multi_agent_v2", command)
        self.assertIn("skip_host_skill_discovery", command)
        self.assertEqual(result["usage"]["input_tokens"], 5)

    def test_hard_timeout_terminates_process_group(self):
        started = time.monotonic()
        code, _, _, timed_out = workflow._communicate(
            [sys.executable, "-c", "import time; time.sleep(60)"], "", 0.05, Path.cwd(),
        )
        self.assertTrue(timed_out)
        self.assertIsNone(code)
        self.assertLess(time.monotonic() - started, 3)


if __name__ == "__main__":
    unittest.main()
