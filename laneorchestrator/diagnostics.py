"""Shared, dependency-free command result types and renderers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Sequence


class Level(str, Enum):
    """The outcome levels a diagnostic can report."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class Diagnostic:
    """A machine-readable observation emitted by a command."""

    code: str
    level: Level
    message: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    def to_dict(self) -> Dict[str, object]:
        return {
            "code": self.code,
            "level": self.level.value,
            "message": self.message,
            "evidence": _plain(self.evidence),
        }


@dataclass(frozen=True)
class CommandResult:
    """The canonical envelope returned by every public command."""

    command: str
    ok: bool
    data: Mapping[str, object] = field(default_factory=dict)
    diagnostics: Sequence[Diagnostic] = ()
    errors: Sequence[Mapping[str, str]] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze(self.data))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(
            self,
            "errors",
            tuple(_freeze(error) for error in self.errors),
        )

    def to_dict(self) -> Dict[str, object]:
        """Return the versioned result envelope in a stable key order."""

        return {
            "schema_version": 1,
            "command": self.command,
            "ok": self.ok,
            "data": _plain(self.data),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "errors": [_plain(error) for error in self.errors],
        }


def command_result(
    command: str,
    data: Optional[Mapping[str, object]] = None,
    diagnostics: Sequence[Diagnostic] = (),
    errors: Sequence[Mapping[str, str]] = (),
) -> CommandResult:
    """Create a result, deriving success from failures and structured errors."""

    diagnostic_items = tuple(diagnostics)
    error_items = tuple(errors)
    ok = not error_items and not any(item.level is Level.FAIL for item in diagnostic_items)
    return CommandResult(
        command=command,
        ok=ok,
        data={} if data is None else data,
        diagnostics=diagnostic_items,
        errors=error_items,
    )


def error_result(command: str, code: str, message: str) -> CommandResult:
    """Create one stable structured error result."""

    return command_result(command, errors=({"code": code, "message": message},))


def render_human(result: CommandResult) -> str:
    """Render a concise, uncoloured view of a command result."""

    lines = [
        "command: {0}".format(result.command),
        "status: {0}".format("ok" if result.ok else "failed"),
    ]
    if result.data:
        lines.append("data: {0}".format(json.dumps(_plain(result.data), sort_keys=True)))
    for diagnostic in result.diagnostics:
        lines.append(
            "[{0}] {1}: {2}".format(
                diagnostic.level.value,
                diagnostic.code,
                diagnostic.message,
            )
        )
    for error in result.errors:
        lines.append("[ERROR] {0}: {1}".format(error["code"], error["message"]))
    return "\n".join(lines)


def render_json(result: CommandResult) -> str:
    """Render the canonical JSON representation."""

    return json.dumps(result.to_dict(), sort_keys=True, indent=2)
