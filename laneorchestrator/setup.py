"""One-confirmation setup for the bundled LaneOrchestrator profiles."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, TextIO, Tuple

from .config import ensure_private_directory, load_config
from .diagnostics import CommandResult, command_result
from .doctor import run_doctor, run_status
from .profiles import (
    PROFILE_NAMES,
    ProfileConflict,
    apply_profiles,
    ensure_agents_root,
    preview_profiles,
)
from .voltagent import (
    PACK_AGENT_COUNT,
    PACK_PREFIX,
    UPSTREAM_COMMIT,
    PackError,
    apply_install as apply_voltagent_install,
    pack_status,
    preview_install as preview_voltagent_install,
)


INTERACTIVE_COMMAND = "python3 -m laneorchestrator setup"
_MANDATORY_DOCTOR_CODES = frozenset(
    ("INSTALLED_PROFILES", "ROLE_ROUTER", "ROLE_MAIN", "ROLE_REVIEWER")
)


@dataclass(frozen=True)
class SetupPreview:
    """The two exact plans represented by one combined human preview."""

    profile_token: str
    profile_approval_digest: str
    specialist_token: str
    specialist_approval_digest: str
    profile_changes: int
    specialist_changes: int
    expires_in_seconds: int
    fingerprint: str

    @property
    def total_changes(self) -> int:
        return self.profile_changes + self.specialist_changes


def _error(code: str, message: str, **data: object) -> CommandResult:
    return command_result(
        "setup",
        data=data,
        errors=({"code": code, "message": message},),
    )


def _pack_exact(status: CommandResult) -> bool:
    return (
        status.data.get("agent_count") == PACK_AGENT_COUNT
        and status.data.get("installed") == PACK_AGENT_COUNT
        and status.data.get("missing") == 0
        and status.data.get("drifted") == 0
    )


def _profiles_exact(status: CommandResult) -> bool:
    values = status.data.get("managed_profile_state")
    return isinstance(values, Mapping) and set(values) == set(PROFILE_NAMES) and all(
        values.get(name) == "managed" for name in PROFILE_NAMES
    )


def readiness(repo_root: Path, state_root: Path, agents_root: Path) -> Mapping[str, object]:
    """Return a bounded read-only setup snapshot without creating plan state."""

    profile_status = run_status(state_root, agents_root)
    specialist_status = pack_status(agents_root)
    core_exact = _profiles_exact(profile_status)
    specialists_exact = _pack_exact(specialist_status)
    return {
        "already_configured": core_exact and specialists_exact,
        "control_profiles": {
            "count": len(PROFILE_NAMES),
            "exact": core_exact,
            "state": dict(profile_status.data.get("managed_profile_state", {})),
        },
        "destination": os.fspath(agents_root),
        "specialists": {
            "count": PACK_AGENT_COUNT,
            "drifted": specialist_status.data.get("drifted", 0),
            "exact": specialists_exact,
            "installed": specialist_status.data.get("installed", 0),
            "missing": specialist_status.data.get("missing", PACK_AGENT_COUNT),
            "prefix": PACK_PREFIX,
            "upstream_commit": UPSTREAM_COMMIT,
        },
    }


def json_status(repo_root: Path, state_root: Path, agents_root: Path) -> CommandResult:
    """Explain that setup needs a terminal, without creating or mutating state."""

    try:
        snapshot = dict(readiness(repo_root, state_root, agents_root))
    except PackError as error:
        snapshot = {
            "already_configured": False,
            "destination": os.fspath(agents_root),
            "readiness_error": str(error),
        }
    snapshot.update(
        {
            "interactive_command": INTERACTIVE_COMMAND,
            "platform_supported": os.name == "posix",
        }
    )
    return _error(
        "SETUP_INTERACTIVE_REQUIRED",
        "setup requires an interactive terminal; rerun the displayed command without --json",
        **snapshot,
    )


def _combined_fingerprint(
    profile_digest: str,
    specialist_digest: str,
    agents_root: Path,
    profile_changes: int,
    specialist_changes: int,
) -> str:
    payload = {
        "control_approval_digest": profile_digest,
        "control_changes": profile_changes,
        "destination": os.fspath(agents_root),
        "specialist_approval_digest": specialist_digest,
        "specialist_changes": specialist_changes,
        "upstream_commit": UPSTREAM_COMMIT,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_preview(
    state_root: Path,
    agents_root: Path,
    now: Optional[int] = None,
) -> SetupPreview:
    """Create both exact plans before asking for the single confirmation."""

    ensure_private_directory(state_root)
    ensure_agents_root(agents_root)
    config = load_config(state_root)
    profile_token, profile_preview = preview_profiles(
        "install", config, agents_root, state_root, now=now
    )
    specialist_token, specialist_preview = preview_voltagent_install(
        agents_root, state_root, now=now
    )
    profile_digest = str(profile_preview.data["approval_digest"])
    specialist_digest = str(specialist_preview.data["approval_digest"])
    profile_changes = int(profile_preview.data["change_count"])
    specialist_changes = int(specialist_preview.data["change_count"])
    expiry = min(
        int(profile_preview.data["expires_in_seconds"]),
        int(specialist_preview.data["expires_in_seconds"]),
    )
    return SetupPreview(
        profile_token=profile_token,
        profile_approval_digest=profile_digest,
        specialist_token=specialist_token,
        specialist_approval_digest=specialist_digest,
        profile_changes=profile_changes,
        specialist_changes=specialist_changes,
        expires_in_seconds=expiry,
        fingerprint=_combined_fingerprint(
            profile_digest,
            specialist_digest,
            agents_root,
            profile_changes,
            specialist_changes,
        ),
    )


def render_preview(preview: SetupPreview, agents_root: Path) -> str:
    """Render the exact combined preview without authorization secrets."""

    return "\n".join(
        (
            "LaneOrchestrator setup preview",
            "Destination: {0}".format(agents_root),
            "Control profiles (4): {0}".format(", ".join(PROFILE_NAMES)),
            "Bundled specialists: {0} profiles ({1}*)".format(
                PACK_AGENT_COUNT, PACK_PREFIX
            ),
            "Pinned upstream commit: {0}".format(UPSTREAM_COMMIT),
            "Changes: {0} control + {1} specialists = {2}".format(
                preview.profile_changes,
                preview.specialist_changes,
                preview.total_changes,
            ),
            "Preview expires in: {0} seconds".format(preview.expires_in_seconds),
            "Combined preview fingerprint: {0}".format(preview.fingerprint),
        )
    )


def _accepted_confirmation(value: str) -> bool:
    return (
        isinstance(value, str)
        and value.endswith("\n")
        and value.strip().casefold() in ("y", "yes")
    )


def _verification(
    repo_root: Path,
    state_root: Path,
    agents_root: Path,
) -> Tuple[bool, Mapping[str, object]]:
    doctor = run_doctor(repo_root, state_root, agents_root)
    specialists = pack_status(agents_root)
    mandatory = {
        item.code: item.level.value
        for item in doctor.diagnostics
        if item.code in _MANDATORY_DOCTOR_CODES
    }
    core_ready = set(mandatory) == set(_MANDATORY_DOCTOR_CODES) and all(
        value == "PASS" for value in mandatory.values()
    )
    specialists_ready = _pack_exact(specialists)
    return core_ready and specialists_ready, {
        "doctor_ok": doctor.ok,
        "mandatory_checks": mandatory,
        "specialist_status": dict(specialists.data),
    }


def run_interactive(
    repo_root: Path,
    state_root: Path,
    agents_root: Path,
    stdin: TextIO,
    stdout: TextIO,
    now: Optional[int] = None,
) -> CommandResult:
    """Run setup through one TTY-bound confirmation and existing exact plans."""

    if os.name != "posix":
        return _error(
            "SETUP_UNSUPPORTED_PLATFORM",
            "native Windows setup is unsupported; run this command inside WSL",
            interactive_command=INTERACTIVE_COMMAND,
        )
    if not stdin.isatty() or not stdout.isatty():
        return _error(
            "SETUP_INTERACTIVE_REQUIRED",
            "setup requires both interactive terminal input and output; pipes and redirects are refused",
            interactive_command=INTERACTIVE_COMMAND,
        )

    try:
        before = readiness(repo_root, state_root, agents_root)
    except PackError as error:
        return _error(
            "SETUP_REFUSED",
            "specialist state could not be inspected safely: {0}".format(error),
            recovery="python3 -m laneorchestrator voltagent status",
        )
    if before["already_configured"]:
        verified, evidence = _verification(repo_root, state_root, agents_root)
        if not verified:
            return _error(
                "SETUP_VERIFICATION_FAILED",
                "installed profiles are exact but mandatory readiness verification failed",
                **evidence,
            )
        return command_result(
            "setup",
            data={
                "already_configured": True,
                "applied": False,
                "control_profiles": len(PROFILE_NAMES),
                "specialists": PACK_AGENT_COUNT,
                "verification": evidence,
            },
        )

    try:
        preview = build_preview(state_root, agents_root, now=now)
    except ProfileConflict as error:
        return _error(
            "SETUP_REFUSED",
            "control profile state requires an explicit profiles update or adopt workflow: {0}".format(
                error
            ),
            recovery="python3 -m laneorchestrator profiles --help",
        )
    except PackError as error:
        return _error(
            "SETUP_REFUSED",
            "specialist state requires explicit recovery before setup can continue: {0}".format(
                error
            ),
            recovery="python3 -m laneorchestrator voltagent status",
        )

    stdout.write(render_preview(preview, agents_root) + "\n\n")
    stdout.write(
        "Install these {0} profiles? [y/N] ".format(
            len(PROFILE_NAMES) + PACK_AGENT_COUNT
        )
    )
    stdout.flush()
    try:
        response = stdin.readline(16)
    except KeyboardInterrupt:
        response = ""
    if not _accepted_confirmation(response):
        return command_result(
            "setup",
            data={
                "applied": False,
                "cancelled": True,
                "combined_preview_fingerprint": preview.fingerprint,
            },
        )

    try:
        core = apply_profiles(
            "install",
            preview.profile_token,
            agents_root,
            state_root,
            approval="approve:" + preview.profile_approval_digest,
            now=now,
        )
    except ProfileConflict as error:
        return _error(
            "SETUP_CORE_FAILED",
            "control profile installation failed safely; specialists were not attempted: {0}".format(
                error
            ),
            combined_preview_fingerprint=preview.fingerprint,
            recovery="rerun setup after resolving the reported control-profile state",
        )

    try:
        specialists = apply_voltagent_install(
            preview.specialist_token,
            agents_root,
            state_root,
            approval="approve:" + preview.specialist_approval_digest,
            now=now,
        )
    except PackError as error:
        return _error(
            "SETUP_PARTIAL",
            "control profiles are installed, but specialist installation failed safely: {0}".format(
                error
            ),
            control_profiles_applied=True,
            recovery="resolve the specialist state, then rerun python3 -m laneorchestrator setup",
        )

    verified, evidence = _verification(repo_root, state_root, agents_root)
    if not verified:
        return _error(
            "SETUP_VERIFICATION_FAILED",
            "installation completed, but mandatory profile verification did not pass",
            **evidence,
        )
    return command_result(
        "setup",
        data={
            "already_configured": False,
            "applied": True,
            "combined_preview_fingerprint": preview.fingerprint,
            "control_changes": core.data.get("change_count", 0),
            "control_profiles": len(PROFILE_NAMES),
            "specialist_changes": specialists.data.get("change_count", 0),
            "specialists": PACK_AGENT_COUNT,
            "verification": evidence,
        },
    )


def render_result(result: CommandResult) -> str:
    """Render a concise setup outcome without leaking plan authorization values."""

    if result.ok:
        if result.data.get("cancelled"):
            return "Setup cancelled. No profiles were installed."
        if result.data.get("already_configured"):
            return "LaneOrchestrator is already set up: 4 control profiles and 172 specialists verified."
        return "LaneOrchestrator setup complete: 4 control profiles and 172 specialists verified."
    error = result.errors[0] if result.errors else {"code": "SETUP_FAILED", "message": "setup failed"}
    lines = ["Setup stopped [{0}]: {1}".format(error["code"], error["message"])]
    recovery = result.data.get("recovery") or result.data.get("interactive_command")
    if recovery:
        lines.append("Next: {0}".format(recovery))
    return "\n".join(lines)
