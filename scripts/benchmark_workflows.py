#!/usr/bin/env python3
"""Opt-in, bounded adaptive-vs-fixed execution on three repository fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from laneorchestrator.adaptive import validate_selection
from laneorchestrator.usage import assess_usage
from scripts.evaluate_astra import HOST


TASK_ROOT = ROOT / "benchmarks" / "workflow-tasks"
CALIBRATION_PATH = ROOT / "benchmarks" / "astra-use-cases-v1.json"
MAX_CALLS = 8
DEFAULT_TOKEN_CEILING = 250_000
FIXED_MODEL = "gpt-5.6-terra"
FIXED_EFFORT = "medium"
ROUTER_MODEL = "gpt-6-astra"
ROUTER_EFFORT = "high"
REVIEW_MODEL = "gpt-5.6-sol"
REVIEW_EFFORT = "high"
MANIFEST_FIELDS = {
    "schema_version", "id", "category", "title", "prompt", "editable_files",
    "test_command", "provenance", "expected_routing",
}


class BenchmarkError(ValueError):
    """Raised when local inputs or live outputs do not satisfy the contract."""


class BudgetStop(RuntimeError):
    """Raised before a call when the observed-use admission policy says stop."""

    def __init__(self, assessment):
        super().__init__(", ".join(assessment["stop_reasons"]))
        self.assessment = assessment


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise BenchmarkError("unsafe relative path: " + str(value))
    return path


def load_tasks(task_root=TASK_ROOT):
    """Load the exact three versioned fixtures and hash their external tests."""

    tasks = []
    for manifest_path in sorted(task_root.glob("*/task.json")):
        try:
            task = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BenchmarkError("invalid task manifest: " + str(manifest_path)) from error
        if not isinstance(task, dict) or set(task) != MANIFEST_FIELDS or task["schema_version"] != 1:
            raise BenchmarkError("task manifest has invalid schema: " + str(manifest_path))
        if task["category"] not in ("bug", "feature", "refactor"):
            raise BenchmarkError("invalid task category: " + str(task["category"]))
        if not isinstance(task["id"], str) or task["id"] != manifest_path.parent.name:
            raise BenchmarkError("task id must match its directory")
        if not isinstance(task["prompt"], str) or not task["prompt"].strip() or len(task["prompt"]) > 5000:
            raise BenchmarkError("task prompt must be bounded and nonempty")
        editable = task["editable_files"]
        if not isinstance(editable, list) or not editable or len(set(editable)) != len(editable):
            raise BenchmarkError("editable_files must be a nonempty unique list")
        for relative in editable:
            source = manifest_path.parent / "starter" / _safe_relative(relative)
            if not source.is_file() or source.is_symlink():
                raise BenchmarkError("missing regular starter file: " + str(source))
        command = task["test_command"]
        if not isinstance(command, list) or command[:3] != ["python", "-m", "unittest"] or any(
                not isinstance(part, str) or not part for part in command):
            raise BenchmarkError("test command must be a bounded unittest command")
        expected = task["expected_routing"]
        if not isinstance(expected, dict) or set(expected) != {"task_kinds", "independent_review"}:
            raise BenchmarkError("invalid expected routing rubric")
        if not isinstance(expected["task_kinds"], list) or not expected["task_kinds"]:
            raise BenchmarkError("expected task kinds must be nonempty")
        if type(expected["independent_review"]) is not bool:
            raise BenchmarkError("review rubric must be boolean")
        test_paths = sorted(path for path in (manifest_path.parent / "tests").rglob("*") if path.is_file()
                            and "__pycache__" not in path.relative_to(manifest_path.parent).parts)
        if not test_paths or any(path.is_symlink() for path in test_paths):
            raise BenchmarkError("each task requires regular external verifier files")
        task = dict(task)
        task["directory"] = manifest_path.parent
        task["test_hashes"] = {
            path.relative_to(manifest_path.parent).as_posix(): _sha256(path) for path in test_paths
        }
        tasks.append(task)
    if len(tasks) != 3 or {task["category"] for task in tasks} != {"bug", "feature", "refactor"}:
        raise BenchmarkError("workflow benchmark requires exactly one bug, feature, and refactor fixture")
    return tasks


def _public_task(task):
    """Return routing evidence with authored expectations and test paths withheld."""

    public = {key: task[key] for key in ("id", "category", "title", "prompt", "editable_files", "provenance")}
    public["starter_sources"] = {
        relative: (task["directory"] / "starter" / relative).read_text(encoding="utf-8")
        for relative in task["editable_files"]
    }
    if sum(len(value) for value in public["starter_sources"].values()) > 20_000:
        raise BenchmarkError("router starter-source evidence exceeds bound")
    return public


def load_calibration():
    document = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    case = next((row for row in document.get("cases", []) if row.get("id") == "U006"), None)
    if not isinstance(case, dict) or not isinstance(case.get("expected"), dict):
        raise BenchmarkError("missing frozen U006 calibration case")
    return case


def _fixture_evidence(tasks):
    return [{key: task[key] for key in ("id", "category", "title", "provenance", "test_hashes")}
            for task in tasks]


def _load_resume_evidence(output, tasks):
    """Validate and reuse the one completed router call from a stopped run."""

    report_path = output / "report.json"
    final_path = output / "calls" / "call-01-router-final.json"
    events_path = output / "calls" / "call-01-router-events.jsonl"
    for path in (report_path, final_path, events_path):
        if not path.is_file() or path.is_symlink():
            raise BenchmarkError("resume requires regular prior evidence file: " + str(path))
    prior_bytes = report_path.read_bytes()
    prior = json.loads(prior_bytes)
    if prior.get("fixtures") != _fixture_evidence(tasks):
        raise BenchmarkError("resume fixture hashes or provenance differ from the prior report")
    ledger = prior.get("usage_ledger")
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "calls"}:
        raise BenchmarkError("resume report has no valid usage ledger")
    if len(ledger.get("calls", [])) != 1:
        raise BenchmarkError("resume requires exactly one prior call")
    record = ledger["calls"][0]
    if (not isinstance(record, dict) or record.get("id") != "call-01-router"
            or record.get("packet") != "router" or record.get("status") != "completed"
            or not isinstance(record.get("usage"), dict)):
        raise BenchmarkError("resume prior call is not one completed router launch with usage")
    usage, turns, observed_model, observed_effort = _event_usage(
        events_path.read_text(encoding="utf-8", errors="replace")
    )
    if usage != record["usage"]:
        raise BenchmarkError("resume router event usage differs from the prior ledger")
    payload = _json_from_final(final_path)
    call = {
        "call_id": "call-01-router", "packet": "router", "requested_model": ROUTER_MODEL,
        "requested_reasoning_effort": ROUTER_EFFORT, "runtime_observed_model": observed_model,
        "runtime_observed_reasoning_effort": observed_effort,
        "runtime_settings_match": _runtime_settings_match(
            ROUTER_MODEL, ROUTER_EFFORT, observed_model, observed_effort),
        "exit_code": None, "prior_ledger_status": record["status"], "timed_out": False,
        "elapsed_seconds": None, "usage": usage, "completed_turns_observed": turns,
        "automatic_retries": 0, "reused_prior_call": True,
    }
    return prior, ledger, payload, call, hashlib.sha256(prior_bytes).hexdigest()


def _execution_sequence(tasks):
    return [(task["id"], arm) for task in tasks for arm in ("adaptive", "fixed")]


def _remaining_execution_sequence(tasks, executions):
    sequence = _execution_sequence(tasks)
    completed = [(row.get("task_id"), row.get("arm")) for row in executions
                 if isinstance(row, dict)]
    if completed != sequence[:len(completed)]:
        raise BenchmarkError("saved executions are not an exact workflow prefix")
    return sequence[len(completed):]


def _reverify_saved_execution(task, row, output, ledger_record):
    expected_artifact = (output / "artifacts" / task["id"] / row["arm"]).resolve()
    artifact = Path(row.get("artifact_directory", "")).resolve()
    if artifact != expected_artifact or not artifact.is_dir() or artifact.is_symlink():
        raise BenchmarkError("saved execution artifact directory is invalid")
    allowed = set(task["editable_files"]) | {"changes.diff", "verification.txt", "final-response.txt"}
    if _workspace_inventory(artifact, allowed):
        raise BenchmarkError("saved execution artifact contains unexpected nodes")
    call = row.get("call")
    if not isinstance(call, dict) or call.get("call_id") != ledger_record.get("id"):
        raise BenchmarkError("saved execution call does not match ledger order")
    if (ledger_record.get("agent") != call["call_id"] or ledger_record.get("packet") != call.get("packet")
            or ledger_record.get("status") != "completed"
            or call.get("usage") != ledger_record.get("usage") or not _valid_call(call)):
        raise BenchmarkError("saved execution call evidence is invalid")
    events = output / "calls" / (call["call_id"] + "-events.jsonl")
    final = output / "calls" / (call["call_id"] + "-final.json")
    if any(not path.is_file() or path.is_symlink() for path in (events, final)):
        raise BenchmarkError("saved execution call files are missing or linked")
    usage, _, _, _ = _event_usage(events.read_text(encoding="utf-8", errors="replace"))
    if usage != ledger_record.get("usage"):
        raise BenchmarkError("saved execution event usage differs from ledger")
    if (artifact / "final-response.txt").read_text(encoding="utf-8", errors="replace") != final.read_text(
            encoding="utf-8", errors="replace")[:20_000]:
        raise BenchmarkError("saved execution final response differs from call evidence")
    if not row.get("verification", {}).get("task_passed"):
        raise BenchmarkError("saved execution was not previously verified as passing")
    with tempfile.TemporaryDirectory(prefix="laneorchestrator-workflow-resume-check-") as temporary:
        root = Path(temporary)
        workspace = root / "work"
        baseline = _prepare_workspace(task, workspace)
        for relative in task["editable_files"]:
            source = artifact / relative
            if not _is_regular_workspace_source(artifact, relative):
                raise BenchmarkError("saved execution source is missing, linked, or non-regular")
            shutil.copy2(source, workspace / relative)
        fresh = _verify_task(task, workspace, root / "verification", baseline)
    if not fresh["task_passed"]:
        raise BenchmarkError("saved execution no longer passes the external verifier")
    return {relative: _sha256(artifact / relative) for relative in task["editable_files"]}


def _load_run_resume_evidence(output, tasks):
    report_path = output / "report.json"
    if not report_path.is_file() or report_path.is_symlink():
        raise BenchmarkError("run resume requires a regular prior report")
    prior_bytes = report_path.read_bytes()
    prior = json.loads(prior_bytes)
    if prior.get("status") != "budget_stopped":
        raise BenchmarkError("run resume requires a budget_stopped report")
    if prior.get("fixtures") != _fixture_evidence(tasks):
        raise BenchmarkError("run resume fixture hashes or provenance differ from the prior report")
    ledger = prior.get("usage_ledger")
    executions = prior.get("executions")
    if (not isinstance(ledger, dict) or set(ledger) != {"schema_version", "calls"}
            or not isinstance(executions, list) or not 2 <= len(ledger.get("calls", [])) < MAX_CALLS
            or len(ledger["calls"]) != 1 + len(executions)):
        raise BenchmarkError("run resume requires one router plus a verified execution prefix")
    _, _, payload, router_call, _ = _load_resume_evidence_from_ledger(
        output, tasks, ledger["calls"][0], prior_bytes,
    )
    decisions = validate_decisions(payload, tasks)
    if prior.get("routing", {}).get("decisions") != decisions:
        raise BenchmarkError("saved routing decisions differ from original router output")
    remaining = _remaining_execution_sequence(tasks, executions)
    task_by_id = {task["id"]: task for task in tasks}
    artifact_hashes = {}
    for index, row in enumerate(executions, start=1):
        task = task_by_id[row["task_id"]]
        artifact_hashes[row["task_id"] + "/" + row["arm"]] = _reverify_saved_execution(
            task, row, output, ledger["calls"][index],
        )
    return prior, ledger, payload, router_call, hashlib.sha256(prior_bytes).hexdigest(), remaining, artifact_hashes


def _load_resume_evidence_from_ledger(output, tasks, record, prior_bytes):
    """Shared router evidence validation for both recovery modes."""
    report_path = output / "report.json"
    final_path = output / "calls" / "call-01-router-final.json"
    events_path = output / "calls" / "call-01-router-events.jsonl"
    for path in (report_path, final_path, events_path):
        if not path.is_file() or path.is_symlink():
            raise BenchmarkError("resume requires regular prior evidence file: " + str(path))
    if (not isinstance(record, dict) or record.get("id") != "call-01-router"
            or record.get("packet") != "router" or record.get("status") != "completed"
            or not isinstance(record.get("usage"), dict)):
        raise BenchmarkError("resume prior call is not one completed router launch with usage")
    usage, turns, observed_model, observed_effort = _event_usage(
        events_path.read_text(encoding="utf-8", errors="replace"))
    if usage != record["usage"]:
        raise BenchmarkError("resume router event usage differs from the prior ledger")
    payload = _json_from_final(final_path)
    call = {
        "call_id": "call-01-router", "packet": "router", "requested_model": ROUTER_MODEL,
        "requested_reasoning_effort": ROUTER_EFFORT, "runtime_observed_model": observed_model,
        "runtime_observed_reasoning_effort": observed_effort,
        "runtime_settings_match": _runtime_settings_match(
            ROUTER_MODEL, ROUTER_EFFORT, observed_model, observed_effort),
        "exit_code": None, "prior_ledger_status": record["status"], "timed_out": False,
        "elapsed_seconds": None, "usage": usage, "completed_turns_observed": turns,
        "automatic_retries": 0, "reused_prior_call": True,
    }
    return json.loads(prior_bytes), None, payload, call, hashlib.sha256(prior_bytes).hexdigest()


def routing_prompt(tasks, calibration):
    public_calibration = {key: calibration[key] for key in ("id", "category", "objective", "context", "facts")}
    return (
        "Choose execution settings independently for these three small Python repository fixtures. "
        "Also decide the separate frozen read-only calibration packet; do not execute it. "
        "Do not use tools, execute tasks, delegate, or infer hidden expectations. Return only the requested JSON. "
        "Classify each as small, routine, or demanding. Under astra-adaptive, small work requires Luna/high "
        "or Terra/high; routine work uses Sol or Terra with a supported effort; demanding work may use any "
        "supported model when justified. Mark independent_review only when consequences warrant a fresh review. "
        "For a read-only code review, task_kind must be review, action must be review, and Sol or Astra is preferred. "
        "Keep every reason under 60 words and give two or three concrete calibration output checks. Active host catalog: "
        + json.dumps(HOST, sort_keys=True) + ". Tasks: "
        + json.dumps([_public_task(task) for task in tasks], sort_keys=True)
        + ". Calibration: " + json.dumps(public_calibration, sort_keys=True)
    )


ROUTING_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["decisions", "calibration"],
    "properties": {"decisions": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "task_kind", "model", "reasoning_effort", "independent_review", "reason"],
        "properties": {
            "id": {"type": "string"}, "task_kind": {"enum": ["small", "routine", "demanding"]},
            "model": {"type": "string"}, "reasoning_effort": {"type": "string"},
            "independent_review": {"type": "boolean"}, "reason": {"type": "string"},
        },
    }}, "calibration": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "task_kind", "model", "reasoning_effort", "independent_review", "action", "reason", "output_checks"],
        "properties": {
            "id": {"type": "string"}, "task_kind": {"enum": ["review"]}, "model": {"type": "string"},
            "reasoning_effort": {"type": "string"}, "independent_review": {"type": "boolean"},
            "action": {"enum": ["review"]}, "reason": {"type": "string"},
            "output_checks": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
        },
    }},
}


REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["reviews"],
    "properties": {"reviews": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["task_id", "arm_a", "arm_b", "comparison", "reason"],
        "properties": {
            "task_id": {"type": "string"},
            "arm_a": {"$ref": "#/$defs/verdict"}, "arm_b": {"$ref": "#/$defs/verdict"},
            "comparison": {"enum": ["equivalent", "a-stronger", "b-stronger"]},
            "reason": {"type": "string"},
        },
    }}},
    "$defs": {"verdict": {
        "type": "object", "additionalProperties": False, "required": ["verdict", "findings"],
        "properties": {
            "verdict": {"enum": ["approve", "changes-requested"]},
            "findings": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        },
    }},
}


def validate_decisions(payload, tasks):
    if not isinstance(payload, dict) or set(payload) != {"decisions", "calibration"} or not isinstance(payload["decisions"], list):
        raise BenchmarkError("router output must contain decisions and calibration")
    rows = payload["decisions"]
    ids = {task["id"] for task in tasks}
    if len(rows) != len(tasks) or any(not isinstance(row, dict) for row in rows) or {
            row.get("id") for row in rows} != ids:
        raise BenchmarkError("router returned missing, duplicate, or unknown task ids")
    validated = []
    for task in tasks:
        row = next(item for item in rows if item.get("id") == task["id"])
        fields = {"id", "task_kind", "model", "reasoning_effort", "independent_review", "reason"}
        if not isinstance(row, dict) or set(row) != fields or type(row["independent_review"]) is not bool:
            raise BenchmarkError("router decision has invalid fields: " + task["id"])
        selection = validate_selection(
            {key: row[key] for key in ("model", "reasoning_effort", "reason")},
            HOST, task_kind=row["task_kind"], preset="astra-adaptive",
        )
        rubric_failures = []
        if row["task_kind"] not in task["expected_routing"]["task_kinds"]:
            rubric_failures.append("task_kind differs from withheld authored rubric")
        if row["independent_review"] != task["expected_routing"]["independent_review"]:
            rubric_failures.append("independent_review differs from withheld authored rubric")
        validated.append(dict(row, **selection, authored_rubric={
            "passed": not rubric_failures, "failures": rubric_failures,
            "expected": task["expected_routing"],
        }))
    return validated


def validate_calibration(row, calibration):
    fields = {"id", "task_kind", "model", "reasoning_effort", "independent_review", "action", "reason", "output_checks"}
    if not isinstance(row, dict) or set(row) != fields or row["id"] != calibration["id"]:
        raise BenchmarkError("invalid U006 calibration result")
    expected = calibration["expected"]
    for field, expected_key in (("task_kind", "task_kinds"), ("model", "models"),
                                ("reasoning_effort", "efforts")):
        if row[field] not in expected[expected_key]:
            raise BenchmarkError("U006 calibration " + field + " differs from frozen rubric")
    if row["independent_review"] != expected["independent_review"] or row["action"] != expected["action"]:
        raise BenchmarkError("U006 calibration review semantics differ from frozen rubric")
    if not isinstance(row["output_checks"], list) or not 2 <= len(row["output_checks"]) <= 3 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in row["output_checks"]):
        raise BenchmarkError("U006 calibration output checks are invalid")
    validate_selection(
        {key: row[key] for key in ("model", "reasoning_effort", "reason")},
        HOST, task_kind="review", preset="astra-adaptive",
    )
    return row


def _json_from_final(path):
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise BenchmarkError("model final response was not a JSON object")
    return value


def _event_usage(stdout):
    usage = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    completed = 0
    observed_model = None
    observed_effort = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "turn.completed":
            completed += 1
            values = event.get("usage")
            if (not isinstance(values, dict)
                    or any(type(values.get(key)) is not int or not 0 <= values[key] <= 10**12
                           for key in usage)
                    or values.get("cached_input_tokens", 0) > values.get("input_tokens", -1)):
                usage = None
            elif usage is not None:
                for key in usage:
                    usage[key] += values[key]
        if event.get("type") in ("thread.started", "turn.started", "turn.completed"):
            if isinstance(event.get("model"), str):
                observed_model = event["model"]
            if isinstance(event.get("reasoning_effort"), str):
                observed_effort = event["reasoning_effort"]
    if completed == 0:
        usage = None
    return usage, completed, observed_model, observed_effort


def _runtime_settings_match(requested_model, requested_effort, observed_model, observed_effort):
    if observed_model is None and observed_effort is None:
        return None
    return ((observed_model is None or observed_model == requested_model)
            and (observed_effort is None or observed_effort == requested_effort))


def _valid_call(call):
    if call.get("timed_out") or call.get("runtime_settings_match") is False:
        return False
    if call.get("reused_prior_call"):
        return call.get("prior_ledger_status") == "completed"
    return call.get("exit_code") == 0


def _communicate(command, prompt, timeout, cwd):
    """Run one call and terminate its process group on the hard timeout."""

    process = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return None, stdout, stderr, True


def _run_call(codex, call_dir, call_id, packet, cwd, model, effort, prompt, timeout, ledger,
              token_ceiling, schema=None, sandbox="workspace-write"):
    assessment = assess_usage(ledger, packet, max_calls=MAX_CALLS, max_retries=0,
                              max_tokens=token_ceiling)
    if not assessment["allowed"]:
        raise BudgetStop(assessment)
    record = {"id": call_id, "packet": packet, "agent": call_id, "status": "pending", "usage": None}
    ledger["calls"].append(record)
    final = call_dir / (call_id + "-final.json")
    events = call_dir / (call_id + "-events.jsonl")
    stderr_path = call_dir / (call_id + "-stderr.txt")
    command = [
        str(codex), "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
        "--disable", "multi_agent", "--disable", "multi_agent_v2", "--enable", "skip_host_skill_discovery",
        "--sandbox", sandbox, "--model", model, "--config",
        "model_reasoning_effort=" + json.dumps(effort), "--config",
        "developer_instructions=\"Stay inside the assigned benchmark directory. Do not delegate, install dependencies, or access unrelated repositories.\"",
        "--cd", str(cwd), "--json", "--output-last-message", str(final),
    ]
    if schema is not None:
        schema_path = call_dir / (call_id + "-schema.json")
        schema_path.write_text(json.dumps(schema, sort_keys=True), encoding="utf-8")
        command.extend(["--output-schema", str(schema_path)])
    command.append("-")
    started = time.monotonic()
    returncode, stdout, stderr, timed_out = _communicate(command, prompt, timeout, cwd)
    elapsed = round(time.monotonic() - started, 3)
    events.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    usage, turns, observed_model, observed_effort = _event_usage(stdout)
    settings_match = _runtime_settings_match(model, effort, observed_model, observed_effort)
    record.update(status="failed" if timed_out or returncode != 0 or settings_match is False else "completed",
                  usage=usage)
    return {
        "call_id": call_id, "packet": packet, "requested_model": model,
        "requested_reasoning_effort": effort, "runtime_observed_model": observed_model,
        "runtime_observed_reasoning_effort": observed_effort, "runtime_settings_match": settings_match,
        "exit_code": returncode,
        "timed_out": timed_out, "elapsed_seconds": elapsed, "usage": usage,
        "completed_turns_observed": turns, "automatic_retries": 0,
        "final_path": final,
    }


def _prepare_workspace(task, destination):
    destination.mkdir(parents=True)
    for relative in task["editable_files"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(task["directory"] / "starter" / relative, target)
    subprocess.run(["git", "init", "-q"], cwd=destination, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "LaneOrchestrator Benchmark"], cwd=destination, check=True)
    subprocess.run(["git", "config", "user.email", "benchmark@invalid.local"], cwd=destination, check=True)
    subprocess.run(["git", "add", "--"] + task["editable_files"], cwd=destination, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture baseline"], cwd=destination, check=True)
    return {relative: _sha256(destination / relative) for relative in task["editable_files"]}


def _workspace_inventory(workspace, allowed):
    """List unexpected nodes without following links or grading cache output."""

    allowed_dirs = set()
    for relative in allowed:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            allowed_dirs.add(parent.as_posix())
            parent = parent.parent
    unexpected = []
    for directory, dirnames, filenames in os.walk(str(workspace), followlinks=False):
        root = Path(directory)
        retained = []
        for name in dirnames:
            path = root / name
            relative = path.relative_to(workspace).as_posix()
            if path.is_symlink():
                unexpected.append(relative)
            elif name == ".git" and root == workspace:
                continue
            elif name == "__pycache__":
                continue
            else:
                if relative not in allowed_dirs:
                    unexpected.append(relative + "/")
                retained.append(name)
        dirnames[:] = retained
        for name in filenames:
            path = root / name
            relative = path.relative_to(workspace).as_posix()
            if relative not in allowed or path.is_symlink():
                unexpected.append(relative)
    return sorted(set(unexpected))


def _is_regular_workspace_source(workspace, relative):
    path = workspace / relative
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return False
        parent = path.parent
        while parent != workspace:
            if parent.is_symlink() or not stat.S_ISDIR(parent.lstat().st_mode):
                return False
            parent = parent.parent
    except OSError:
        return False
    return True


def _verify_task(task, workspace, artifact_dir, baseline):
    artifact_dir.mkdir(parents=True)
    allowed = set(task["editable_files"])
    unexpected = _workspace_inventory(workspace, allowed)
    invalid_sources = sorted(relative for relative in allowed if
                             not _is_regular_workspace_source(workspace, relative))
    modified = not invalid_sources and any(
        _sha256(workspace / relative) != baseline[relative] for relative in allowed
    )
    for relative in allowed - set(invalid_sources):
        target = artifact_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workspace / relative, target)
    diff = subprocess.run(["git", "diff", "--binary", "--"], cwd=workspace,
                          text=True, capture_output=True, timeout=20)
    (artifact_dir / "changes.diff").write_text(diff.stdout, encoding="utf-8")
    started = time.monotonic()
    check_returncode = None
    check_output = "verification skipped: missing or symbolic-link edited source\n" if invalid_sources else ""
    tests_unchanged = True
    with tempfile.TemporaryDirectory(prefix="laneorchestrator-workflow-verify-") as temporary:
        verifier = Path(temporary)
        if not invalid_sources:
            for relative in allowed:
                target = verifier / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(workspace / relative, target)
            shutil.copytree(task["directory"] / "tests", verifier / "tests")
            verifier_test_hashes = {
                path.relative_to(verifier).as_posix(): _sha256(path)
                for path in (verifier / "tests").rglob("*") if path.is_file()
                and "__pycache__" not in path.relative_to(verifier).parts
            }
            for path in (verifier / "tests").rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
            command = [sys.executable if part == "python" and index == 0 else part
                       for index, part in enumerate(task["test_command"])]
            check_env = dict(os.environ)
            check_env["PYTHONDONTWRITEBYTECODE"] = "1"
            check = subprocess.run(command, cwd=verifier, text=True, capture_output=True,
                                   timeout=60, env=check_env)
            check_returncode = check.returncode
            check_output = check.stdout + check.stderr
            tests_unchanged = verifier_test_hashes == {
                path.relative_to(verifier).as_posix(): _sha256(path)
                for path in (verifier / "tests").rglob("*") if path.is_file()
                and "__pycache__" not in path.relative_to(verifier).parts
            }
    (artifact_dir / "verification.txt").write_text(check_output, encoding="utf-8")
    return {
        "task_passed": check_returncode == 0 and modified and not unexpected and tests_unchanged,
        "test_exit_code": check_returncode, "source_modified": modified,
        "unexpected_workspace_files": unexpected, "external_tests_unchanged": tests_unchanged,
        "invalid_edited_sources": invalid_sources,
        "verification_elapsed_seconds": round(time.monotonic() - started, 3),
    }


def _blind_mapping(task_id):
    # Stable alternating labels prevent one execution strategy always appearing first.
    if int(hashlib.sha256(task_id.encode("utf-8")).hexdigest(), 16) % 2:
        return {"A": "adaptive", "B": "fixed"}
    return {"A": "fixed", "B": "adaptive"}


def _prepare_review(tasks, executions, destination):
    mappings = {}
    prompts = []
    by_key = {(row["task_id"], row["arm"]): row for row in executions}
    for task in tasks:
        if not task["expected_routing"]["independent_review"]:
            continue
        mapping = _blind_mapping(task["id"])
        mappings[task["id"]] = mapping
        prompts.append({"task_id": task["id"], "requirements": task["prompt"]})
        for label, arm in mapping.items():
            source_dir = Path(by_key[(task["id"], arm)]["artifact_directory"])
            target = destination / task["id"] / ("arm-" + label.lower())
            target.mkdir(parents=True)
            for relative in task["editable_files"]:
                source = source_dir / relative
                copied = target / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, copied)
    (destination / "requirements.json").write_text(json.dumps(prompts, indent=2), encoding="utf-8")
    return mappings


def _comparison(tasks, executions, complete):
    rows = []
    by_key = {(row["task_id"], row["arm"]): row for row in executions}
    for task in tasks:
        adaptive = by_key.get((task["id"], "adaptive"))
        fixed = by_key.get((task["id"], "fixed"))
        if not adaptive or not fixed:
            rows.append({"task_id": task["id"], "complete": False})
            continue
        def tokens(row):
            usage = row["call"]["usage"]
            return None if usage is None else usage["input_tokens"] + usage["output_tokens"]
        adaptive_tokens, fixed_tokens = tokens(adaptive), tokens(fixed)
        rows.append({
            "task_id": task["id"], "complete": complete,
            "adaptive_task_passed": adaptive["verification"]["task_passed"],
            "fixed_task_passed": fixed["verification"]["task_passed"],
            "adaptive_elapsed_seconds": adaptive["call"]["elapsed_seconds"],
            "fixed_elapsed_seconds": fixed["call"]["elapsed_seconds"],
            "adaptive_observed_tokens": adaptive_tokens, "fixed_observed_tokens": fixed_tokens,
            "observed_token_delta_adaptive_minus_fixed": (
                None if adaptive_tokens is None or fixed_tokens is None else adaptive_tokens - fixed_tokens
            ),
        })
    return rows


def _write_report(path, report):
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _successful_comparison(tasks, report, tests_unchanged):
    expected = {(task['id'], arm) for task in tasks for arm in ('adaptive', 'fixed')}
    executions = report['executions']
    if (not tests_unchanged or len(executions) != len(expected)
            or {(row['task_id'], row['arm']) for row in executions} != expected):
        return False
    if not all(row['verification']['task_passed'] is True and _valid_call(row['call'])
               for row in executions):
        return False
    required = {task['id'] for task in tasks if task['expected_routing']['independent_review']}
    if not required:
        return True
    review = report.get('independent_review')
    if not review or not _valid_call(review['call']) or not review['review_workspace_unchanged']:
        return False
    payload = review.get('payload')
    rows = payload.get('reviews') if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != len(required):
        return False
    if any(not isinstance(row, dict) for row in rows) or {row.get('task_id') for row in rows} != required:
        return False
    return all(isinstance(row.get(arm), dict) and row[arm].get('verdict') == 'approve'
               and isinstance(row[arm].get('findings'), list)
               and all(isinstance(finding, str) for finding in row[arm]['findings'])
               for row in rows for arm in ('arm_a', 'arm_b'))


def execute(args, tasks, calibration):
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise BenchmarkError("live output must be outside the source repository")
    resuming_routing = args.resume_routing is not None
    resuming_run = args.resume_run is not None
    resuming = resuming_routing or resuming_run
    if not resuming and output.exists() and any(output.iterdir()):
        raise BenchmarkError("live output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=resuming)
    calls_dir = output / "calls"
    artifacts_dir = output / "artifacts"
    calls_dir.mkdir(exist_ok=resuming)
    artifacts_dir.mkdir(exist_ok=resuming)
    prior = None
    routing_payload = None
    routing_call = None
    prior_report_sha256 = None
    remaining_sequence = _execution_sequence(tasks)
    saved_artifact_hashes = {}
    if resuming_run:
        prior, ledger, routing_payload, routing_call, prior_report_sha256, remaining_sequence, saved_artifact_hashes = (
            _load_run_resume_evidence(output, tasks)
        )
    elif resuming_routing:
        prior, ledger, routing_payload, routing_call, prior_report_sha256 = _load_resume_evidence(output, tasks)
    else:
        ledger = {"schema_version": 1, "calls": []}
    report = dict(prior) if resuming_run else {
        "schema_version": 1,
        "scope": "Three repository-derived executable fixtures; not a benchmark of broad user-repository work.",
        "status": "running", "live_calls": len(ledger["calls"]), "automatic_retries": 0,
        "limits": {"max_calls": MAX_CALLS, "max_observed_tokens": args.max_observed_tokens,
                   "per_call_timeout_seconds": args.timeout,
                   "token_limit_kind": "stop before next call after observed usage reaches the ceiling; one call may overshoot"},
        "runtime_observation": "Requested settings are CLI arguments. Observed model/effort remain null unless emitted by runtime events.",
        "host_discovery_boundary": "Benchmark subprocesses request disabled multi-agent features and skipped host skill discovery, but runtime evidence may still show host metadata loading. This does not test installed named profiles or automatic specialist discovery.",
        "test_boundary": "Authoritative tests stay outside task workspaces and are write-protected in verifier copies. The host sandbox may still allow read access; this is not an inaccessible holdout claim.",
        "fixtures": _fixture_evidence(tasks),
        "routing": None, "executions": [], "independent_review": None, "comparison": [],
    }
    if resuming_run:
        for key in ("stop_reason", "final_usage_assessment", "error"):
            report.pop(key, None)
        report["status"] = "running"
        report["limits"] = {
            "max_calls": MAX_CALLS, "max_observed_tokens": args.max_observed_tokens,
            "per_call_timeout_seconds": args.timeout,
            "token_limit_kind": "stop before next call after observed usage reaches the ceiling; one call may overshoot",
        }
        report["resume_run"] = {
            "prior_report_sha256": prior_report_sha256, "prior_calls_preserved": len(ledger["calls"]),
            "prior_executions_preserved": len(report["executions"]),
            "saved_artifacts_reverified": saved_artifact_hashes,
            "next_execution": list(remaining_sequence[0]) if remaining_sequence else None,
        }
    elif resuming_routing:
        report["resume"] = {
            "reused_router_call": True, "prior_report_sha256": prior_report_sha256,
            "prior_status": prior.get("status"), "prior_error": prior.get("error"),
            "available_fixture_hashes_and_provenance_matched": True,
        }
    report_path = output / "report.json"
    _write_report(report_path, report)
    try:
        with tempfile.TemporaryDirectory(prefix="laneorchestrator-workflow-run-") as temporary:
            scratch = Path(temporary)
            if not resuming:
                routing_call = _run_call(
                    args.codex, calls_dir, "call-01-router", "router", scratch, ROUTER_MODEL, ROUTER_EFFORT,
                    routing_prompt(tasks, calibration), args.timeout, ledger, args.max_observed_tokens,
                    schema=ROUTING_SCHEMA, sandbox="read-only",
                )
                report["live_calls"] = len(ledger["calls"])
                routing_payload = _json_from_final(routing_call.pop("final_path"))
            if not _valid_call(routing_call):
                raise BenchmarkError("routing call failed or observed settings differed")
            decisions = validate_decisions(routing_payload, tasks)
            try:
                calibration_result = {"passed": True, "decision": validate_calibration(routing_payload["calibration"], calibration)}
            except (BenchmarkError, ValueError, KeyError, TypeError) as error:
                calibration_result = {"passed": False, "decision": routing_payload.get("calibration"), "error": str(error)}
            report["routing"] = {"call": routing_call, "decisions": decisions,
                                 "expected_rubric_withheld_from_router": True,
                                 "authored_rubric_passed": all(
                                     row["authored_rubric"]["passed"] for row in decisions),
                                 "calibration": calibration_result,
                                 "calibration_source": "benchmarks/astra-use-cases-v1.json#U006",
                                 "calibration_corpus_sha256": _sha256(CALIBRATION_PATH)}
            _write_report(report_path, report)
            decision_by_id = {row["id"]: row for row in decisions}
            call_number = len(ledger["calls"]) + 1
            completed = {(row["task_id"], row["arm"]) for row in report["executions"]}
            for task in tasks:
                for arm in ("adaptive", "fixed"):
                    if (task["id"], arm) in completed:
                        continue
                    decision = decision_by_id[task["id"]]
                    model = decision["model"] if arm == "adaptive" else FIXED_MODEL
                    effort = decision["reasoning_effort"] if arm == "adaptive" else FIXED_EFFORT
                    workspace = scratch / task["id"] / arm
                    baseline = _prepare_workspace(task, workspace)
                    call = _run_call(
                        args.codex, calls_dir, "call-{0:02d}-{1}-{2}".format(call_number, task["id"], arm),
                        task["id"] + "-" + arm, workspace, model, effort, task["prompt"], args.timeout,
                        ledger, args.max_observed_tokens,
                    )
                    call_number += 1
                    final_path = call.pop("final_path")
                    artifact = artifacts_dir / task["id"] / arm
                    verification = _verify_task(task, workspace, artifact, baseline)
                    verification["task_passed"] = (
                        verification["task_passed"] and _valid_call(call)
                    )
                    final_text = ""
                    if final_path.exists():
                        final_text = final_path.read_text(encoding="utf-8", errors="replace")[:20_000]
                    (artifact / "final-response.txt").write_text(final_text, encoding="utf-8")
                    report["executions"].append({
                        "task_id": task["id"], "category": task["category"], "arm": arm,
                        "call": call, "verification": verification,
                        "artifact_directory": str(artifact),
                    })
                    report["live_calls"] = len(ledger["calls"])
                    _write_report(report_path, report)
            review_tasks = [task for task in tasks if task["expected_routing"]["independent_review"]]
            if review_tasks:
                review_workspace = scratch / "independent-review"
                review_workspace.mkdir()
                mappings = _prepare_review(review_tasks, report["executions"], review_workspace)
                before = {path.relative_to(review_workspace).as_posix(): _sha256(path)
                          for path in review_workspace.rglob("*") if path.is_file()}
                prompt = (
                    "Independently review each listed task's two anonymized implementations against requirements. "
                    "Do not edit, execute, seek external tests, delegate, or guess which model/strategy produced an arm. "
                    "Report only concrete correctness or maintainability findings in the requested JSON. Requirements "
                    "are in requirements.json and sources are under each task's arm-a and arm-b directories."
                )
                review_call = _run_call(
                    args.codex, calls_dir, "call-{0:02d}-review".format(call_number), "combined-review",
                    review_workspace, REVIEW_MODEL, REVIEW_EFFORT, prompt, args.timeout, ledger,
                    args.max_observed_tokens, schema=REVIEW_SCHEMA, sandbox="read-only",
                )
                review_final = review_call.pop("final_path")
                after = {path.relative_to(review_workspace).as_posix(): _sha256(path)
                         for path in review_workspace.rglob("*") if path.is_file()}
                review_payload = _json_from_final(review_final) if _valid_call(review_call) else None
                report["independent_review"] = {
                    "call": review_call, "blind_arm_mapping": mappings, "payload": review_payload,
                    "review_workspace_unchanged": before == after, "single_fresh_combined_review": True,
                }
                report["live_calls"] = len(ledger["calls"])
            fixture_hashes_unchanged = all(task["test_hashes"] == {
                path.relative_to(task["directory"]).as_posix(): _sha256(path)
                for path in (task["directory"] / "tests").rglob("*") if path.is_file()
                and "__pycache__" not in path.relative_to(task["directory"]).parts
            } for task in tasks)
            complete = _successful_comparison(tasks, report, fixture_hashes_unchanged)
            report["status"] = "completed" if complete else "failed"
            report["fixture_tests_unchanged"] = fixture_hashes_unchanged
            report["comparison"] = _comparison(tasks, report["executions"], complete)
    except BudgetStop as error:
        report["status"] = "budget_stopped"
        report["stop_reason"] = error.assessment
        report["live_calls"] = len(ledger["calls"])
        report["comparison"] = _comparison(tasks, report["executions"], False)
    except (BenchmarkError, OSError, subprocess.SubprocessError, ValueError) as error:
        report["status"] = "failed"
        report["error"] = str(error)
        report["live_calls"] = len(ledger["calls"])
        report["comparison"] = _comparison(tasks, report["executions"], False)
    report["usage_ledger"] = ledger
    report["final_usage_assessment"] = assess_usage(
        ledger, "post-run", max_calls=MAX_CALLS, max_retries=0, max_tokens=args.max_observed_tokens,
    )
    _write_report(report_path, report)
    print(json.dumps({key: report[key] for key in ("status", "live_calls", "limits")}, sort_keys=True))
    return 0 if report["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Make live model calls")
    parser.add_argument("--codex", type=Path, help="Exact Codex CLI executable")
    parser.add_argument("--output", type=Path, help="New/empty external evidence directory")
    parser.add_argument("--resume-routing", type=Path,
                        help="Reuse the single completed router call in this prior report directory")
    parser.add_argument("--resume-run", type=Path,
                        help="Continue a validated budget-stopped run without repeating completed calls")
    parser.add_argument("--timeout", type=int, default=240, help="Hard seconds per call")
    parser.add_argument("--max-observed-tokens", type=int, default=DEFAULT_TOKEN_CEILING)
    args = parser.parse_args()
    tasks = load_tasks()
    calibration = load_calibration()
    plan = {
        "status": "validated_plan", "fixtures": [task["id"] for task in tasks],
        "planned_calls": {"router": 1, "implementations": 6, "combined_review_max": 1,
                          "hard_total": MAX_CALLS},
        "automatic_retries": 0, "max_observed_tokens": args.max_observed_tokens,
    }
    if not args.run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.codex is None or not args.codex.is_file() or not os.access(args.codex, os.X_OK):
        parser.error("--run requires an executable --codex path")
    if args.resume_routing is not None and args.resume_run is not None:
        parser.error("choose only one resume mode")
    resume_path = args.resume_run if args.resume_run is not None else args.resume_routing
    if resume_path is not None:
        if args.output is not None and args.output.resolve() != resume_path.resolve():
            parser.error("--output and the resume directory must identify the same directory")
        args.output = resume_path
    if args.output is None:
        parser.error("--run requires --output")
    if type(args.timeout) is not int or not 30 <= args.timeout <= 900:
        parser.error("--timeout must be 30 to 900 seconds")
    if type(args.max_observed_tokens) is not int or not 1 <= args.max_observed_tokens <= 10**9:
        parser.error("--max-observed-tokens must be 1 to 1000000000")
    return execute(args, tasks, calibration)


if __name__ == "__main__":
    raise SystemExit(main())
