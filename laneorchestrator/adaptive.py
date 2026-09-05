"""Task-specific execution decisions supplied by the host's Astra coordinator.

This module validates decisions; it does not call a model or infer that an
installed profile proves model entitlement. Host catalogs must come from the
active host, never from specialist descriptions or repository instructions.
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

from .models import is_valid_model_id, is_valid_reasoning_effort


ASTRA = "gpt-6-astra"
SMALL_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra")
ROUTINE_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra")
TASK_KINDS = ("investigation", "small", "routine", "demanding", "review")
PRESETS = ("astra-adaptive", "all-astra", "manual")
MAX_AUTOMATIC_RETRIES = 2


def policy() -> Dict[str, object]:
    """Return selection guidance without inventing a task-specific decision."""

    return {
        "schema_version": 2,
        "coordinator": {"model": ASTRA, "reasoning_effort": "high"},
        "preset": "astra-adaptive",
        "small": {"preferred_models": list(SMALL_MODELS), "reasoning_effort": "high"},
        "routine": {
            "preferred_models": list(ROUTINE_MODELS),
            "reasoning_effort": "chosen_by_astra",
        },
        "demanding": {"preferred_models": [ASTRA], "reasoning_effort": "chosen_by_astra"},
        "review": {"preferred_models": ["gpt-5.6-sol", ASTRA], "reasoning_effort": "chosen_by_astra"},
        "user_override_precedence": True,
        "max_automatic_retries": MAX_AUTOMATIC_RETRIES,
        "runtime_observed": False,
    }


def validate_host_models(models: object) -> Mapping[str, Sequence[str]]:
    """Validate the shape of a host-supplied model/effort snapshot."""

    if not isinstance(models, Mapping) or not 1 <= len(models) <= 128:
        raise ValueError("host models must contain 1 to 128 model entries")
    for model, efforts in models.items():
        if not is_valid_model_id(model):
            raise ValueError("host catalog contains an invalid model identifier")
        if not isinstance(efforts, (list, tuple)) or not efforts or len(efforts) > 6:
            raise ValueError("host model must declare its supported thinking levels")
        if any(not is_valid_reasoning_effort(effort) for effort in efforts):
            raise ValueError("host catalog contains an invalid thinking level")
        if len(set(efforts)) != len(efforts):
            raise ValueError("host catalog contains duplicate thinking levels")
    return {model: tuple(efforts) for model, efforts in models.items()}


def validate_selection(
    selection: Mapping[str, object],
    host_models: Mapping[str, Sequence[str]],
    *,
    task_kind: str,
    preset: str = "astra-adaptive",
    user_override: bool = False,
) -> Dict[str, str]:
    """Validate Astra's choice against the host and explicit product policy.

    Expertise never restricts a model. Small/routine preferences are the user's
    default policy, with explicit overrides and presets handled separately.
    """

    supported = validate_host_models(host_models)
    if task_kind not in TASK_KINDS or preset not in PRESETS:
        raise ValueError("unknown task kind or preset")
    if type(user_override) is not bool:
        raise ValueError("user_override must be a boolean supplied by the host")
    if not isinstance(selection, Mapping) or set(selection) != {"model", "reasoning_effort", "reason"}:
        raise ValueError("selection requires model, reasoning_effort, and reason")
    model, effort, reason = (selection[key] for key in ("model", "reasoning_effort", "reason"))
    if not is_valid_model_id(model) or model not in supported:
        raise ValueError("selected model is not in the active host catalog")
    if not is_valid_reasoning_effort(effort) or effort not in supported[model]:
        raise ValueError("selected thinking level is unsupported for this model")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError("selection requires a bounded explanation")
    if any(ord(char) < 32 or ord(char) == 127 for char in reason):
        raise ValueError("selection explanation contains a control character")
    if not user_override and preset == "all-astra" and model != ASTRA:
        raise ValueError("all-astra requires Astra for every selected agent")
    if not user_override and preset == "astra-adaptive":
        if task_kind == "small" and (model not in SMALL_MODELS or effort != "high"):
            raise ValueError("small changes use Luna/high or Terra/high under the adaptive preset")
        if task_kind == "routine" and model not in ROUTINE_MODELS:
            raise ValueError("routine implementation uses Sol or Terra; Astra chooses thinking")
    return {"model": model, "reasoning_effort": effort, "reason": reason.strip()}


def spawn_settings(selection: Mapping[str, str]) -> Dict[str, str]:
    """Produce explicit native launch settings, never an execution claim."""

    if not is_valid_model_id(selection.get("model")) or not is_valid_reasoning_effort(selection.get("reasoning_effort")):
        raise ValueError("invalid launch selection")
    return {
        "model": selection["model"],
        "reasoning_effort": selection["reasoning_effort"],
        "fork_turns": "none",
    }
