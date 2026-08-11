"""Unified command-line interface for LaneOrchestrator."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

from . import __version__
from .benchmark import run_benchmark
from .config import (
    ConfigError,
    apply_config,
    ensure_private_directory,
    load_config,
    preview_config,
)
from .diagnostics import CommandResult, command_result, error_result, render_human, render_json
from .discovery import (
    DEFAULT_LIMITS,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_ITEMS,
    MAX_EXPLICIT_ROOTS,
    MAX_QUERY_CHARS,
    _collect_agents,
    _collect_skills,
    _legacy_payload,
    result_limit,
    roots_for,
)
from .doctor import inspect_role_evidence, run_doctor, run_status
from .models import Availability, EffectiveConfig, LOGICAL_ROLES, RoleEvidence, codex_home
from .plans import PlanError
from .profiles import ProfileConflict, apply_profiles, ensure_agents_root, preview_profiles
from .routing import RouteFacts, VALID_RISKS, positive_file_count, recommend_route
from .security import SecurityError
from .voltagent import PackError, apply_install as apply_voltagent_install, pack_inventory, pack_status, preview_install as preview_voltagent_install


COMMANDS = ("doctor", "status", "configure", "route", "catalog", "profiles", "voltagent", "benchmark", "version")
PROFILE_ACTIONS = ("install", "update", "adopt", "uninstall")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class DomainError(ValueError):
    """Stable expected command failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _ArgumentError(ValueError):
    """An argparse usage error represented in the common envelope."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit the canonical JSON result",
    )


def _subparser(parent: argparse._SubParsersAction, name: str) -> _Parser:
    parser = parent.add_parser(name)  # type: ignore[assignment]
    _add_json_option(parser)
    return parser  # type: ignore[return-value]


def benchmark_repeat(value: str) -> int:
    """Limit deterministic benchmark repetitions to an auditable local range."""
    if len(value) > 3:
        raise argparse.ArgumentTypeError("must be between 2 and 10")
    try:
        repeat = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer between 2 and 10") from error
    if not 2 <= repeat <= 10:
        raise argparse.ArgumentTypeError("must be between 2 and 10")
    return repeat


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="laneorchestrator")
    _add_json_option(parser)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    _subparser(commands, "doctor")
    _subparser(commands, "status")
    _subparser(commands, "version")

    configure = _subparser(commands, "configure")
    configure_phases = configure.add_subparsers(dest="phase", required=True, parser_class=_Parser)
    configure_preview = _subparser(configure_phases, "preview")
    configure_preview.add_argument("--set", dest="settings", action="append", required=True)
    configure_apply = _subparser(configure_phases, "apply")
    configure_apply.add_argument("--token", required=True)
    configure_apply.add_argument("--approval", required=True)

    route = _subparser(commands, "route")
    route.add_argument("--objective", required=True)
    route.add_argument("--known-area", action="store_true")
    route.add_argument("--acceptance-criteria", action="store_true")
    route.add_argument("--files", type=positive_file_count, default=2)
    route.add_argument("--risk-assessment", choices=VALID_RISKS, default="unknown")

    catalog = _subparser(commands, "catalog")
    catalog.add_argument("--query", required=True)
    catalog.add_argument("--cwd", default=os.getcwd())
    catalog.add_argument("--context", action="append", default=[])
    catalog.add_argument("--skills-root", action="append", default=[])
    catalog.add_argument("--agents-root", action="append", default=[])
    catalog.add_argument("--no-default-roots", action="store_true")
    catalog.add_argument("--top-skills", type=result_limit, default=6)
    catalog.add_argument("--top-agents", type=result_limit, default=6)
    catalog.add_argument("--unscoped-high-risk", action="store_true")

    benchmark = _subparser(commands, "benchmark")
    benchmark.add_argument("--repeat", type=benchmark_repeat, default=3)

    profiles = _subparser(commands, "profiles")
    profile_actions = profiles.add_subparsers(dest="action", required=True, parser_class=_Parser)
    for action in PROFILE_ACTIONS:
        action_parser = _subparser(profile_actions, action)
        phases = action_parser.add_subparsers(dest="phase", required=True, parser_class=_Parser)
        _subparser(phases, "preview")
        apply_parser = _subparser(phases, "apply")
        apply_parser.add_argument("--token", required=True)
        apply_parser.add_argument("--approval", required=True)

    voltagent = _subparser(commands, "voltagent")
    volt_actions = voltagent.add_subparsers(dest="voltagent_action", required=True, parser_class=_Parser)
    _subparser(volt_actions, "inventory")
    _subparser(volt_actions, "status")
    install = _subparser(volt_actions, "install")
    install_phases = install.add_subparsers(dest="phase", required=True, parser_class=_Parser)
    _subparser(install_phases, "preview")
    install_apply = _subparser(install_phases, "apply")
    install_apply.add_argument("--token", required=True)
    install_apply.add_argument("--approval", required=True)
    return parser


def _runtime_paths() -> Tuple[Path, Path, Path]:
    configured = os.environ.get("CODEX_HOME")
    if configured and not Path(configured).is_absolute():
        raise DomainError("UNSAFE_CODEX_HOME", "CODEX_HOME must be an absolute path")
    home = codex_home()
    return home, home / "laneorchestrator", home / "agents"


def _settings(values: Sequence[str]) -> Mapping[str, str]:
    updates: Dict[str, str] = {}
    for raw in values:
        if not isinstance(raw, str) or raw.count("=") != 1:
            raise DomainError("CONFIG_SET_INVALID", "--set must use ROLE.FIELD=VALUE")
        key, value = raw.split("=", 1)
        if not key or not value:
            raise DomainError("CONFIG_SET_INVALID", "--set must use ROLE.FIELD=VALUE")
        if key in updates:
            raise DomainError("CONFIG_SET_DUPLICATE", "duplicate --set destination")
        updates[key] = value
    return updates


def handle_doctor(args: argparse.Namespace) -> CommandResult:
    _home, state, agents = _runtime_paths()
    return run_doctor(Path(__file__).absolute().parents[1], state, agents)


def handle_status(args: argparse.Namespace) -> CommandResult:
    _home, state, agents = _runtime_paths()
    return run_status(state, agents)


def handle_configure(args: argparse.Namespace) -> CommandResult:
    _home, state, _agents = _runtime_paths()
    if args.phase == "preview":
        _token, result = preview_config(_settings(args.settings), state)
        return result
    return apply_config(args.token, state, approval=args.approval)


def _role_payload(evidence: Mapping[str, RoleEvidence]) -> Mapping[str, object]:
    return {
        role: {
            "availability": evidence[role].availability.value,
            "configured_model": evidence[role].configured_model,
            "profile_path": evidence[role].profile_path,
        }
        for role in LOGICAL_ROLES
    }


def resolve_route(
    decision: Mapping[str, object],
    config: EffectiveConfig,
    evidence: Mapping[str, RoleEvidence],
) -> CommandResult:
    """Apply only the approved role fallbacks to one canonical route decision."""

    if set(evidence) != set(LOGICAL_ROLES):
        raise DomainError("ROLE_EVIDENCE_INVALID", "route evidence must cover every logical role")
    lane = decision.get("lane")
    if lane not in ("luna", "terra", "sol-plan-terra-sol-review"):
        raise DomainError("ROUTE_INVALID", "route decision lane is invalid")
    requested_role = "small_task_executor" if lane == "luna" else "main_implementer"
    effective_lane = lane
    effective_role = requested_role
    fallback: Optional[str] = None
    data: Dict[str, object] = {
        "route": dict(decision),
        "requested_lane": lane,
        "requested_role": requested_role,
        "role_evidence": _role_payload(evidence),
        "optional_specialist": {
            "availability": Availability.UNKNOWN.value,
            "fallback": "continue_without_specialist",
        },
    }

    def failed(code: str, message: str) -> CommandResult:
        data.update(
            {
                "effective_lane": effective_lane,
                "effective_model": config.roles[effective_role].model,
                "effective_role": effective_role,
                "fallback": fallback,
            }
        )
        return command_result("route", data=data, errors=({"code": code, "message": message},))

    if evidence["router"].availability is Availability.MISSING:
        return failed("ROUTER_MISSING", "required router profile is missing")
    if evidence["router"].availability is Availability.UNKNOWN:
        return failed("ROUTER_UNKNOWN", "required router profile availability is unknown")
    if lane == "luna" and evidence["small_task_executor"].availability is not Availability.AVAILABLE:
        effective_lane = "terra"
        effective_role = "main_implementer"
        fallback = "small_task_executor->main_implementer"
    if evidence["main_implementer"].availability is Availability.MISSING:
        return failed("MAIN_IMPLEMENTER_MISSING", "required main implementer profile is missing")
    if evidence["main_implementer"].availability is Availability.UNKNOWN:
        return failed(
            "MAIN_IMPLEMENTER_UNKNOWN",
            "required main implementer profile availability is unknown",
        )
    if (
        lane == "sol-plan-terra-sol-review"
        and evidence["independent_reviewer"].availability is Availability.MISSING
    ):
        return failed("REVIEWER_MISSING", "required high-risk reviewer profile is missing")
    if (
        lane == "sol-plan-terra-sol-review"
        and evidence["independent_reviewer"].availability is Availability.UNKNOWN
    ):
        return failed(
            "REVIEWER_UNKNOWN",
            "required high-risk reviewer profile availability is unknown",
        )
    data.update(
        {
            "effective_lane": effective_lane,
            "effective_model": config.roles[effective_role].model,
            "effective_role": effective_role,
            "fallback": fallback,
        }
    )
    return command_result("route", data=data)


def handle_route(args: argparse.Namespace) -> CommandResult:
    _home, state, agents = _runtime_paths()
    config = load_config(state)
    decision = recommend_route(
        RouteFacts(
            args.objective.strip(),
            args.known_area,
            args.acceptance_criteria,
            args.files,
            args.risk_assessment,
        )
    )
    evidence = inspect_role_evidence(config, agents)
    return resolve_route(decision, config, evidence)


def handle_catalog(args: argparse.Namespace) -> CommandResult:
    if len(args.skills_root) > MAX_EXPLICIT_ROOTS or len(args.agents_root) > MAX_EXPLICIT_ROOTS:
        raise DomainError(
            "INVALID_ARGUMENTS",
            "explicit roots must not exceed {0} per capability type".format(MAX_EXPLICIT_ROOTS),
        )
    if not args.query.strip():
        raise DomainError("INVALID_ARGUMENTS", "--query must not be blank")
    if len(args.query) > MAX_QUERY_CHARS:
        raise DomainError(
            "INVALID_ARGUMENTS", "--query must not exceed {0} characters".format(MAX_QUERY_CHARS)
        )
    if len(args.context) > MAX_CONTEXT_ITEMS:
        raise DomainError(
            "INVALID_ARGUMENTS", "--context may be repeated at most {0} times".format(MAX_CONTEXT_ITEMS)
        )
    if sum(len(item) for item in args.context) > MAX_CONTEXT_CHARS:
        raise DomainError(
            "INVALID_ARGUMENTS", "combined --context must not exceed {0} characters".format(MAX_CONTEXT_CHARS)
        )
    _home, _state, managed_agents_root = _runtime_paths()
    cwd = Path(args.cwd).resolve()
    skill_roots = roots_for(cwd, args.skills_root, args.no_default_roots)
    agent_roots = list(dict.fromkeys(Path(item).expanduser() for item in args.agents_root)) or [managed_agents_root]
    skills, skill_warnings, _skill_counters = _collect_skills(skill_roots, DEFAULT_LIMITS)
    agents, agent_warnings, _agent_counters = _collect_agents(agent_roots, DEFAULT_LIMITS)
    payload = _legacy_payload(
        args.query,
        args.context,
        cwd,
        skills + agents,
        skill_warnings + agent_warnings,
        args.top_skills,
        args.top_agents,
        args.unscoped_high_risk,
        managed_agents_root,
    )
    return command_result("catalog", data={"catalog": payload})


def handle_benchmark(args: argparse.Namespace) -> CommandResult:
    return run_benchmark(Path(__file__).absolute().parents[1], args.repeat)


def handle_profiles(args: argparse.Namespace) -> CommandResult:
    _home, state, agents = _runtime_paths()
    if args.phase == "preview":
        ensure_private_directory(state)
        ensure_agents_root(agents)
        config = load_config(state)
        _token, result = preview_profiles(args.action, config, agents, state)
        return result
    if _TOKEN_RE.fullmatch(args.token) is None:
        raise DomainError("PLAN_INVALID", "plan token has invalid syntax")
    return apply_profiles(args.action, args.token, agents, state, approval=args.approval)


def handle_voltagent(args: argparse.Namespace) -> CommandResult:
    _home, state, agents = _runtime_paths()
    if args.voltagent_action == "inventory":
        return pack_inventory()
    if args.voltagent_action == "status":
        return pack_status(agents)
    if args.phase == "preview":
        ensure_private_directory(state)
        ensure_agents_root(agents)
        _token, result = preview_voltagent_install(agents, state)
        return result
    if _TOKEN_RE.fullmatch(args.token) is None:
        raise DomainError("PLAN_INVALID", "plan token has invalid syntax")
    return apply_voltagent_install(args.token, agents, state, approval=args.approval)


def _manifest_version() -> str:
    path = Path(__file__).absolute().parents[1] / ".codex-plugin" / "plugin.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = payload["version"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DomainError("MANIFEST_INVALID", "plugin manifest version could not be read") from error
    if not isinstance(version, str) or not version:
        raise DomainError("MANIFEST_INVALID", "plugin manifest version is invalid")
    return version


def handle_version(args: argparse.Namespace) -> CommandResult:
    return command_result(
        "version",
        data={
            "manifest_version": _manifest_version(),
            "package_version": __version__,
            "schema_version": 1,
            "version": __version__,
        },
    )


def _plan_error(error: BaseException) -> DomainError:
    message = str(error).casefold()
    if "already used" in message:
        return DomainError("PLAN_CONSUMED", "plan token was already used")
    if "expired" in message:
        return DomainError("PLAN_EXPIRED", "plan has expired")
    if "not found" in message:
        return DomainError("PLAN_NOT_FOUND", "plan was not found")
    return DomainError("PLAN_INVALID", "plan could not be validated")


def dispatch(args: argparse.Namespace) -> CommandResult:
    handlers = {
        "doctor": handle_doctor,
        "status": handle_status,
        "configure": handle_configure,
        "route": handle_route,
        "catalog": handle_catalog,
        "benchmark": handle_benchmark,
        "profiles": handle_profiles,
        "voltagent": handle_voltagent,
        "version": handle_version,
    }
    try:
        return handlers[args.command](args)
    except DomainError as error:
        return error_result(args.command, error.code, str(error))
    except PlanError as error:
        mapped = _plan_error(error)
        return error_result(args.command, mapped.code, str(mapped))
    except ProfileConflict as error:
        mapped = _plan_error(error)
        if mapped.code != "PLAN_INVALID" or "plan" in str(error).casefold():
            return error_result(args.command, mapped.code, str(mapped))
        return error_result(args.command, "PROFILE_CONFLICT", str(error))
    except PackError as error:
        mapped = _plan_error(error)
        if mapped.code != "PLAN_INVALID" or "plan" in str(error).casefold():
            return error_result(args.command, mapped.code, str(mapped))
        return error_result(args.command, "VOLT_PACK_CONFLICT", str(error))
    except ConfigError as error:
        return error_result(args.command, "CONFIG_INVALID", str(error))
    except SecurityError as error:
        return error_result(args.command, "SECURITY_REFUSED", str(error))
    except ValueError as error:
        return error_result(args.command, "INVALID_ARGUMENTS", str(error))
    except OSError:
        return error_result(args.command, "FILESYSTEM_ERROR", "filesystem operation failed safely")


def _json_requested(argv: Sequence[str]) -> bool:
    return "--json" in argv


def _command_for_error(argv: Sequence[str]) -> str:
    for value in argv:
        if value in COMMANDS:
            return value
    return "unknown"


def _render(result: CommandResult, as_json: bool) -> None:
    print(render_json(result) if as_json else render_human(result))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Execute one command and return its process exit status."""

    raw_arguments = tuple(sys.argv[1:] if argv is None else argv)
    as_json = _json_requested(raw_arguments)
    parser = build_parser()
    try:
        args = parser.parse_args(raw_arguments)
        as_json = bool(getattr(args, "json", False))
    except _ArgumentError as error:
        result = error_result(_command_for_error(raw_arguments), "INVALID_ARGUMENTS", str(error))
        _render(result, as_json)
        return 2

    try:
        result = dispatch(args)
    except Exception:
        result = error_result(args.command, "INTERNAL_ERROR", "unexpected internal error")
        _render(result, as_json)
        if os.environ.get("LANEORCHESTRATOR_DEBUG") == "1":
            rendered = traceback.format_exc()
            token = getattr(args, "token", None)
            if isinstance(token, str) and token:
                rendered = rendered.replace(token, "[REDACTED]")
            sys.stderr.write(rendered)
        return 3
    _render(result, as_json)
    if result.errors and result.errors[0].get("code") == "INVALID_ARGUMENTS":
        return 2
    return 0 if result.ok else 1
