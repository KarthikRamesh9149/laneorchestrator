"""Immutable logical-role models and local configuration validation helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional


LOGICAL_ROLES = (
    "router",
    "small_task_executor",
    "main_implementer",
    "independent_reviewer",
)
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def is_valid_model_id(value: object) -> bool:
    """Return whether *value* is a bounded canonical model identifier."""

    return isinstance(value, str) and MODEL_ID_RE.fullmatch(value) is not None


def is_valid_reasoning_effort(value: object) -> bool:
    """Return whether *value* names one of the supported effort levels."""

    return isinstance(value, str) and value in REASONING_EFFORTS


@dataclass(frozen=True)
class RoleConfig:
    """The model and effort preference for one logical role."""

    model: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        if not is_valid_model_id(self.model):
            raise ValueError("invalid model identifier")
        if not is_valid_reasoning_effort(self.reasoning_effort):
            raise ValueError("invalid reasoning effort")


@dataclass(frozen=True)
class EffectiveConfig:
    """The validated, complete role mapping used by the control plane."""

    schema_version: int
    roles: Mapping[str, RoleConfig]
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", MappingProxyType(dict(self.roles)))


class Availability(str, Enum):
    """The authoritative availability state for a configured role."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RoleEvidence:
    """Observed profile evidence for a configured logical role."""

    role: str
    configured_model: str
    profile_path: Optional[str]
    availability: Availability


def codex_home(
    env: Optional[Mapping[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    """Return the effective Codex home without accepting relative overrides."""

    environment = os.environ if env is None else env
    base_home = Path.home() if home is None else Path(home)
    configured = environment.get("CODEX_HOME")
    if configured:
        candidate = Path(configured)
        if candidate.is_absolute():
            return candidate
    return base_home / ".codex"
