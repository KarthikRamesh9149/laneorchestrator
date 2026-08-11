"""Reproducible, bounded regression benchmarks for routing and discovery.

The committed corpora contain reviewed labels.  This module deliberately keeps
those labels out of the router and ranker inputs so a passing score is an
evaluation result, never a replay of the expected answer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

from .diagnostics import CommandResult, Diagnostic, Level, command_result
from .discovery import DEFAULT_LIMITS, Capability, collect, rank
from .routing import RouteFacts, VALID_RISKS, recommend_route, validate_route_facts


THRESHOLDS = {
    "overall_lane_agreement": 0.98,
    "high_risk_recall": 1.0,
    "top3_specialist_recall": 0.90,
    "deterministic_repeatability": 1.0,
    "adversarial_pass_rate": 1.0,
    "max_catalog_seconds": 10.0,
}
_ROUTE_CATEGORIES = {
    "bounded-low": "luna",
    "normal": "terra",
    "high-risk": "sol-plan-terra-sol-review",
    "high-risk-evasion": "sol-plan-terra-sol-review",
    "conservative-unknown": "sol-plan-terra-sol-review",
}
_ROUTE_FIELDS = {
    "id", "category", "objective", "known_area", "acceptance_criteria", "files", "risk", "expected_lane",
}
_CAPABILITY_FIELDS = {"query", "capabilities", "expected_top3", "expected_sources", "applicable_specialist", "adversarial"}
_MAX_CORPUS_BYTES = 512 * 1024
_MAX_CAPABILITIES_PER_CASE = 8
_CATALOG_SEED = 20260809
_MIN_ADVERSARIAL_CASES = 8
_MIN_SOURCE_PRECEDENCE_ADVERSARIAL_CASES = 1
_MIN_MEANINGFUL_HIGH_RISK_CASES = 20
# Authentication value for the reviewed routing corpus.  This digest covers
# every field, including the gold lane/category/risk labels, so corpus edits
# cannot silently redefine the benchmark contract.
_ROUTE_CORPUS_DIGEST = "df6d7ddc7ba22b7f349b3337a211070481cf68695f51538249ff64f89aeec509"


class BenchmarkError(ValueError):
    """Raised when a committed benchmark corpus is malformed or unsafe."""


def _read_json(path: Path) -> object:
    try:
        with path.open("rb") as source:
            raw = source.read(_MAX_CORPUS_BYTES + 1)
    except OSError as error:
        raise BenchmarkError("could not read benchmark corpus: {0}".format(path)) from error
    if len(raw) > _MAX_CORPUS_BYTES:
        raise BenchmarkError("benchmark corpus exceeds {0} bytes".format(_MAX_CORPUS_BYTES))
    try:
        def no_duplicate_keys(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
            value: Dict[str, object] = {}
            for key, item in pairs:
                if key in value:
                    raise BenchmarkError("benchmark JSON contains a duplicate object key")
                value[key] = item
            return value
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BenchmarkError("benchmark corpus is not valid UTF-8 JSON: {0}".format(path)) from error


def _nonblank_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError("benchmark field {0} must be a nonblank string".format(field))
    return value


def load_route_corpus(repo_root: Path) -> List[Dict[str, object]]:
    """Load and validate the bounded, reviewed routing corpus."""
    payload = _read_json(repo_root / "benchmarks" / "routing-corpus-v1.json")
    if not isinstance(payload, list):
        raise BenchmarkError("routing corpus must be a JSON array")
    counts = {category: 0 for category in _ROUTE_CATEGORIES}
    seen_ids, seen_objectives = set(), set()
    cases: List[Dict[str, object]] = []
    for index, case in enumerate(payload):
        if not isinstance(case, dict) or set(case) != _ROUTE_FIELDS:
            raise BenchmarkError("routing case {0} has an invalid schema".format(index))
        identifier = _nonblank_string(case["id"], "id")
        objective = _nonblank_string(case["objective"], "objective")
        category = case["category"]
        expected_lane = case["expected_lane"]
        if category not in _ROUTE_CATEGORIES or expected_lane != _ROUTE_CATEGORIES[category]:
            raise BenchmarkError("routing case {0} has an invalid reviewed label".format(identifier))
        if identifier in seen_ids or objective.casefold().strip() in seen_objectives:
            raise BenchmarkError("routing corpus contains a duplicate id or objective")
        if type(case["known_area"]) is not bool or type(case["acceptance_criteria"]) is not bool:
            raise BenchmarkError("routing case {0} has invalid boolean facts".format(identifier))
        if not isinstance(case["files"], int) or isinstance(case["files"], bool) or case["files"] < 1:
            raise BenchmarkError("routing case {0} has invalid file count".format(identifier))
        if case["risk"] not in VALID_RISKS:
            raise BenchmarkError("routing case {0} has invalid risk".format(identifier))
        try:
            validate_route_facts(RouteFacts(objective, case["known_area"], case["acceptance_criteria"], case["files"], case["risk"]))
        except ValueError as error:
            raise BenchmarkError("routing case {0} exceeds route input bounds".format(identifier)) from error
        seen_ids.add(identifier)
        seen_objectives.add(objective.casefold().strip())
        counts[category] += 1
        cases.append(dict(case))
    expected_counts = {"bounded-low": 40, "normal": 60, "high-risk": 70, "high-risk-evasion": 15, "conservative-unknown": 15}
    if counts != expected_counts:
        raise BenchmarkError("routing corpus category counts do not match the reviewed contract")
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, _ROUTE_CORPUS_DIGEST):
        raise BenchmarkError("routing corpus does not match the independently authenticated reviewed labels")
    meaningful_high_risk = sum(
        case["expected_lane"] == "sol-plan-terra-sol-review" and case["risk"] != "high"
        for case in cases
    )
    if meaningful_high_risk < _MIN_MEANINGFUL_HIGH_RISK_CASES:
        raise BenchmarkError("routing corpus lacks meaningful non-explicit high-risk cases")
    return cases


def load_capability_corpus(repo_root: Path) -> List[Dict[str, object]]:
    """Load synthetic, bounded capability metadata and reviewed relevance labels."""
    payload = _read_json(repo_root / "benchmarks" / "capability-corpus-v1.json")
    if not isinstance(payload, list) or not payload:
        raise BenchmarkError("capability corpus must be a nonempty JSON array")
    cases: List[Dict[str, object]] = []
    adversarial_count = 0
    source_precedence_adversarial_count = 0
    for index, case in enumerate(payload):
        if not isinstance(case, dict) or set(case) != _CAPABILITY_FIELDS:
            raise BenchmarkError("capability case {0} has an invalid schema".format(index))
        query = _nonblank_string(case["query"], "query")
        if len(query) > DEFAULT_LIMITS.max_query_chars:
            raise BenchmarkError("capability case {0} exceeds query bounds".format(index))
        capabilities = case["capabilities"]
        expected = case["expected_top3"]
        expected_sources = case["expected_sources"]
        if not isinstance(capabilities, list) or not capabilities or len(capabilities) > _MAX_CAPABILITIES_PER_CASE:
            raise BenchmarkError("capability case {0} has an invalid catalog size".format(index))
        if not isinstance(expected, list) or len(expected) > 3 or len(set(expected)) != len(expected) or any(not isinstance(item, str) or not item for item in expected):
            raise BenchmarkError("capability case {0} has invalid expected_top3".format(index))
        if not isinstance(expected_sources, dict) or set(expected_sources) != set(expected) or any(not isinstance(value, str) or not value for value in expected_sources.values()):
            raise BenchmarkError("capability case {0} has invalid expected_sources".format(index))
        if type(case["applicable_specialist"]) is not bool or type(case["adversarial"]) is not bool:
            raise BenchmarkError("capability case {0} has invalid flags".format(index))
        if not case["applicable_specialist"] and expected:
            raise BenchmarkError("non-applicable capability cases must have no expected specialist")
        names, records = set(), set()
        for item in capabilities:
            if not isinstance(item, dict) or set(item) != {"kind", "name", "description", "source"}:
                raise BenchmarkError("capability case {0} has invalid metadata".format(index))
            for key in ("kind", "name", "description", "source"):
                _nonblank_string(item[key], key)
            if len(item["name"]) > DEFAULT_LIMITS.max_capability_name_chars or len(item["description"]) > DEFAULT_LIMITS.max_capability_description_chars:
                raise BenchmarkError("capability case {0} exceeds metadata bounds".format(index))
            record = (item["kind"], item["name"], item["description"], item["source"])
            if record in records:
                raise BenchmarkError("capability case {0} has an exact duplicate record".format(index))
            records.add(record)
            names.add(item["name"])
        if not set(expected).issubset(names):
            raise BenchmarkError("capability case {0} labels a missing specialist".format(index))
        sources_by_name = {}
        for item in capabilities:
            sources_by_name.setdefault(item["name"], set()).add(item["source"])
        if any(source not in sources_by_name[name] for name, source in expected_sources.items()):
            raise BenchmarkError("capability case {0} labels a missing specialist source".format(index))
        if case["adversarial"]:
            adversarial_count += 1
            if case["applicable_specialist"] and any(
                len(sources_by_name.get(name, set())) >= 2
                for name in expected_sources
            ):
                source_precedence_adversarial_count += 1
        cases.append(dict(case))
    if adversarial_count < _MIN_ADVERSARIAL_CASES:
        raise BenchmarkError("capability corpus lacks mandatory adversarial coverage")
    if source_precedence_adversarial_count < _MIN_SOURCE_PRECEDENCE_ADVERSARIAL_CASES:
        raise BenchmarkError("capability corpus lacks mandatory source-precedence coverage")
    return cases


def _route_decisions(cases: Sequence[Mapping[str, object]]) -> List[str]:
    decisions = []
    for case in cases:
        facts = RouteFacts(
            str(case["objective"]), bool(case["known_area"]), bool(case["acceptance_criteria"]), int(case["files"]), str(case["risk"]),
        )
        decisions.append(str(recommend_route(facts)["lane"]))
    return decisions


def evaluate_routes(cases: Sequence[Mapping[str, object]], repeat: int = 3) -> Dict[str, float]:
    """Evaluate route agreement without supplying reviewed labels to the router."""
    if repeat < 2:
        raise BenchmarkError("benchmark repeat must be at least 2")
    snapshots = [_route_decisions(cases) for _ in range(repeat)]
    actual = snapshots[0]
    expected = [str(case["expected_lane"]) for case in cases]
    # Measure semantic/high-risk backstop coverage separately from rows whose
    # explicit ``risk=high`` input already forces the Sol lane.
    high_indices = [
        index for index, (lane, case) in enumerate(zip(expected, cases))
        if lane == "sol-plan-terra-sol-review" and case["risk"] != "high"
    ]
    non_high_indices = [index for index, lane in enumerate(expected) if lane != "sol-plan-terra-sol-review"]
    adversarial_indices = [index for index, case in enumerate(cases) if case["category"] == "high-risk-evasion"]
    explicit_high_indices = [index for index, case in enumerate(cases) if case["risk"] == "high"]
    unknown_indices = [index for index, case in enumerate(cases) if case["risk"] == "unknown"]
    agreement = sum(found == wanted for found, wanted in zip(actual, expected)) / float(len(cases))
    # An evaluation with no non-explicit high-risk cases is not a passing
    # security result; represent it as a zero recall so the release threshold
    # fails closed instead of dividing by zero or reporting a vacuous 1.0.
    high_recall = (
        sum(actual[index] == expected[index] for index in high_indices) / float(len(high_indices))
        if high_indices else 0.0
    )
    false_positives = sum(actual[index] == "sol-plan-terra-sol-review" for index in non_high_indices)
    adversarial = (sum(actual[index] == expected[index] for index in adversarial_indices) / float(len(adversarial_indices))) if adversarial_indices else 1.0
    return {
        "overall_lane_agreement": agreement,
        "high_risk_recall": high_recall,
        "false_positive_rate": false_positives / float(len(non_high_indices)),
        "explicit_high_risk_recall": sum(actual[index] == expected[index] for index in explicit_high_indices) / float(len(explicit_high_indices)) if explicit_high_indices else 1.0,
        "unknown_risk_escalation_recall": sum(actual[index] == expected[index] for index in unknown_indices) / float(len(unknown_indices)) if unknown_indices else 1.0,
        "lexical_high_risk_evasion_recall": adversarial,
        "deterministic_repeatability": 1.0 if all(snapshot == snapshots[0] for snapshot in snapshots[1:]) else 0.0,
        "route_adversarial_pass_rate": adversarial,
        "route_cases": float(len(cases)),
        "high_risk_cases": float(len(high_indices)),
        "non_high_risk_cases": float(len(non_high_indices)),
        "explicit_high_risk_cases": float(len(explicit_high_indices)),
        "unknown_risk_cases": float(len(unknown_indices)),
        "lexical_high_risk_evasion_cases": float(len(adversarial_indices)),
    }


def _ranked_capabilities(case: Mapping[str, object], reverse: bool = False) -> List[Tuple[str, str]]:
    """Return a source-aware ranking; stable paths prevent input-order leakage."""
    metadata = list(case["capabilities"])  # type: ignore[arg-type]
    if reverse:
        metadata.reverse()
    capabilities = [
        Capability(
            str(item["kind"]), str(item["name"]), str(item["description"]),
            "synthetic/{0}/{1}/{2}".format(item["source"], item["kind"], item["name"]), str(item["source"]),
        )
        for item in metadata
    ]
    return [(item.name, item.source) for item in rank(str(case["query"]), capabilities, ())]


def evaluate_capabilities(cases: Sequence[Mapping[str, object]], repeat: int = 3) -> Dict[str, float]:
    """Measure top-k specialist relevance against bounded synthetic catalogs."""
    if repeat < 2:
        raise BenchmarkError("benchmark repeat must be at least 2")
    snapshots = [
        ([_ranked_capabilities(case) for case in cases], [_ranked_capabilities(case, reverse=True) for case in cases])
        for _ in range(repeat)
    ]
    rankings = snapshots[0][0]
    applicable = [(case, ranking) for case, ranking in zip(cases, rankings) if bool(case["applicable_specialist"])]
    if not applicable:
        raise BenchmarkError("capability corpus has no applicable specialist cases")
    top1 = sum(bool({name for name, _source in ranking[:1]} & set(case["expected_top3"])) for case, ranking in applicable)
    top3 = sum(bool({name for name, _source in ranking[:3]} & set(case["expected_top3"])) for case, ranking in applicable)
    source_hits = sum(
        all(dict(ranking).get(name) == source for name, source in case["expected_sources"].items())
        for case, ranking in applicable
    )
    non_applicable = [(case, ranking) for case, ranking in zip(cases, rankings) if not bool(case["applicable_specialist"])]
    adversarial = [(case, ranking) for case, ranking in zip(cases, rankings) if bool(case["adversarial"])]
    adversarial_passes = sum(
        (
            bool({name for name, _source in ranking[:3]} & set(case["expected_top3"]))
            and all(dict(ranking).get(name) == source for name, source in case["expected_sources"].items())
        ) if case["applicable_specialist"] else not ranking
        for case, ranking in adversarial
    )
    return {
        "top1_specialist_recall": top1 / float(len(applicable)),
        "top3_specialist_recall": top3 / float(len(applicable)),
        "source_precedence_recall": source_hits / float(len(applicable)),
        "non_applicable_abstention_rate": sum(not ranking for _case, ranking in non_applicable) / float(len(non_applicable)) if non_applicable else 1.0,
        "capability_adversarial_pass_rate": adversarial_passes / float(len(adversarial)) if adversarial else 1.0,
        "capability_cases": float(len(cases)),
        "applicable_specialist_cases": float(len(applicable)),
        "capability_repeatability": 1.0 if all(original == reversed_ for original, reversed_ in snapshots) and all(snapshot == snapshots[0] for snapshot in snapshots[1:]) else 0.0,
    }


def merge_metrics(route_metrics: Mapping[str, float], capability_metrics: Mapping[str, float]) -> Dict[str, float]:
    """Merge metric families and require every tagged adversarial case to pass."""
    metrics = dict(route_metrics)
    metrics.update(capability_metrics)
    metrics["deterministic_repeatability"] = min(route_metrics["deterministic_repeatability"], capability_metrics["capability_repeatability"])
    metrics["adversarial_pass_rate"] = min(route_metrics["route_adversarial_pass_rate"], capability_metrics["capability_adversarial_pass_rate"])
    return metrics


def _catalog_file_text(kind: str, index: int, bytes_required: int) -> str:
    if kind == "skill":
        prefix = "---\nname: benchmark-skill-{0}\ndescription: Deterministic benchmark capability {0}.\n---\n".format(index)
    else:
        prefix = 'name = "benchmark-agent-{0}"\ndescription = "Deterministic benchmark agent {0}"\nmodel = "gpt-5.6-terra"\n'.format(index)
    return prefix + ("#" * (bytes_required - len(prefix)))


def _write_max_catalog(root: Path) -> Tuple[Path, Path]:
    """Create the default file/byte-bound catalog from a fixed seed, not Git."""
    randomizer = random.Random(_CATALOG_SEED)
    skill_root, agent_root = root / "skills", root / "agents"
    skill_root.mkdir()
    agent_root.mkdir()
    skill_indices = list(range(DEFAULT_LIMITS.max_skill_files))
    agent_indices = list(range(DEFAULT_LIMITS.max_agent_files))
    randomizer.shuffle(skill_indices)
    randomizer.shuffle(agent_indices)
    for index in skill_indices:
        directory = skill_root / "skill-{0:04d}".format(index)
        directory.mkdir()
        (directory / "SKILL.md").write_text(_catalog_file_text("skill", index, DEFAULT_LIMITS.max_skill_file_bytes), encoding="utf-8")
    agent_bytes = DEFAULT_LIMITS.max_total_agent_bytes // DEFAULT_LIMITS.max_agent_files
    for index in agent_indices:
        (agent_root / "agent-{0:04d}.toml".format(index)).write_text(_catalog_file_text("agent", index, agent_bytes), encoding="utf-8")
    return skill_root, agent_root


def evaluate_max_catalog(workspace: Path) -> Tuple[float, Dict[str, int], Dict[str, int]]:
    """Measure only bounded discovery over default file and total-byte limits."""
    skill_root, agent_root = _write_max_catalog(workspace)
    started = time.monotonic()
    _capabilities, warnings, counters = collect((skill_root, agent_root), DEFAULT_LIMITS)
    elapsed = time.monotonic() - started
    limits = asdict(DEFAULT_LIMITS)
    if warnings or counters["skill_files"] != limits["max_skill_files"] or counters["skill_bytes"] != limits["max_total_skill_bytes"] or counters["agent_files"] != limits["max_agent_files"] or counters["agent_bytes"] != limits["max_total_agent_bytes"]:
        raise BenchmarkError("maximum catalog did not exercise the expected discovery bounds")
    return elapsed, dict(counters), limits


def compare_thresholds(metrics: Mapping[str, float], thresholds: Mapping[str, float]) -> Tuple[Diagnostic, ...]:
    """Return one diagnostic per release threshold; every miss is a failure."""
    diagnostics = []
    for name, threshold in thresholds.items():
        value = metrics.get(name)
        passed = isinstance(value, (int, float)) and (value < threshold if name == "max_catalog_seconds" else value >= threshold)
        diagnostics.append(Diagnostic(
            "BENCHMARK_{0}".format(name.upper()), Level.PASS if passed else Level.FAIL,
            "{0} {1} release threshold".format(name, "meets" if passed else "misses"),
            {"metric": value, "threshold": threshold, "comparison": "<" if name == "max_catalog_seconds" else ">="},
        ))
    return tuple(diagnostics)


def run_benchmark(repo_root: Path, repeat: int = 3) -> CommandResult:
    """Run the reviewed corpora and a temporary maximum-size discovery fixture."""
    started = time.monotonic()
    route_metrics = evaluate_routes(load_route_corpus(repo_root), repeat)
    capability_metrics = evaluate_capabilities(load_capability_corpus(repo_root), repeat)
    with tempfile.TemporaryDirectory(prefix="laneorchestrator-benchmark-") as directory:
        catalog_seconds, counters, limits = evaluate_max_catalog(Path(directory))
    metrics = merge_metrics(route_metrics, capability_metrics)
    metrics["max_catalog_seconds"] = catalog_seconds
    metrics["elapsed_seconds"] = time.monotonic() - started
    diagnostics = compare_thresholds(metrics, THRESHOLDS)
    return command_result("benchmark", data={"metrics": metrics, "limits": limits, "max_catalog_counters": counters, "measurement_scope": "max_catalog_seconds measures discovery only; elapsed_seconds measures the full benchmark"}, diagnostics=diagnostics)
