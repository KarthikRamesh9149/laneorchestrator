"""Command-line interface for LaneOrchestrator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .diagnostics import CommandResult, command_result, error_result, render_human, render_json
from .doctor import run_doctor, run_status
from .models import codex_home


class _ArgumentError(ValueError):
    """An argument error that can be represented in the canonical envelope."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="laneorchestrator")
    parser.add_argument("command", nargs="?", help="command to run (doctor, status, or version)")
    parser.add_argument("--json", action="store_true", help="emit the canonical JSON result")
    return parser


def dispatch(args: argparse.Namespace) -> CommandResult:
    if args.command == "version":
        return command_result("version", data={"version": __version__})
    home = codex_home()
    if args.command == "doctor":
        return run_doctor(
            Path(__file__).absolute().parents[1],
            home / "laneorchestrator",
            home / "agents",
        )
    if args.command == "status":
        return run_status(home / "laneorchestrator", home / "agents")
    if args.command is None:
        return error_result("unknown", "invalid_arguments", "a command is required")
    return error_result("unknown", "invalid_arguments", "unknown command: {0}".format(args.command))


def _json_requested(argv: Optional[Sequence[str]]) -> bool:
    return "--json" in (() if argv is None else argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Execute one command and return its process exit status."""

    parser = build_parser()
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(arguments)
    except _ArgumentError as exc:
        result = error_result("unknown", "invalid_arguments", str(exc))
        print(render_json(result) if _json_requested(arguments) else render_human(result))
        return 2

    result = dispatch(args)
    print(render_json(result) if args.json else render_human(result))
    if result.errors and result.errors[0].get("code") == "invalid_arguments":
        return 2
    return 0 if result.ok else 1
