"""One auditable route-card contract composed from routing and discovery.

This module deliberately consumes discovery records as data.  It never treats a
specialist description as configuration or parses a model identifier from it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Mapping, Optional, Sequence

from .discovery import Capability, TRUSTED_SOURCES, rank
from .models import (
    Availability,
    EffectiveConfig,
    RoleEvidence,
    is_valid_model_id,
    is_valid_reasoning_effort,
)


ROUTING_ROLE = "router"
LUNA_ROLE = "small_task_executor"
TERRA_ROLE = "main_implementer"
REVIEW_ROLE = "independent_reviewer"


def _role_payload(evidence: Mapping[str, RoleEvidence]) -> Dict[str, Dict[str, Optional[str]]]:
    return {
        role: {
            "availability": value.availability.value,
            "configured_model": value.configured_model,
            "profile_path": value.profile_path,
        }
        for role, value in evidence.items()
    }


def _stage(role: str, config: EffectiveConfig, evidence: Mapping[str, RoleEvidence]) -> Dict[str, object]:
    observed = evidence[role]
    return {
        "role": role,
        "model": config.roles[role].model,
        "reasoning_effort": config.roles[role].reasoning_effort,
        "availability": observed.availability.value,
    }


def _specialist_payload(candidate: Capability) -> Optional[Dict[str, object]]:
    """Return structured optional-specialist evidence when it is complete.

    A transitional ``getattr`` keeps this module compatible with discovery
    records created before structured fields were added, while deliberately
    refusing any description-only model information.
    """

    model = getattr(candidate, "model", None)
    effort = getattr(candidate, "reasoning_effort", None)
    if (
        candidate.source not in TRUSTED_SOURCES
        or not is_valid_model_id(model)
        or not is_valid_reasoning_effort(effort)
    ):
        return None
    return {
        "name": candidate.name,
        "kind": candidate.kind,
        "path": candidate.path,
        "source": candidate.source,
        "score": candidate.score,
        "matched_terms": list(candidate.matched_terms),
        "model": model,
        "reasoning_effort": effort,
        "availability": Availability.AVAILABLE.value,
    }


def build_route_card(
    route: Mapping[str, object],
    config: EffectiveConfig,
    evidence: Mapping[str, RoleEvidence],
    candidates: Sequence[Capability],
    objective: str,
    context: Sequence[str],
    force_suppress: bool = False,
) -> Dict[str, object]:
    """Build the stable v1 route card without changing route/catalog outputs.

    High-risk work has no optional-specialist selection without non-empty,
    caller-supplied context.  This policy lives here so callers cannot bypass it
    by forgetting a catalog-only flag.
    """

    lane = route.get("lane")
    if lane not in ("luna", "terra", "sol-plan-terra-sol-review"):
        raise ValueError("route decision lane is invalid")
    if set(evidence) != set(config.roles):
        raise ValueError("route evidence must cover every logical role")
    high_risk = lane == "sol-plan-terra-sol-review"
    scoped_context = tuple(item for item in context if isinstance(item, str) and item.strip())
    suppressed = force_suppress or (high_risk and not scoped_context)
    selected: Optional[Dict[str, object]] = None
    selection_reason = "no_trusted_match"
    if suppressed:
        selection_reason = "unscoped_high_risk" if high_risk else "caller_suppressed"
    else:
        ranked = rank(objective, candidates, scoped_context)
        for candidate in ranked:
            selected = _specialist_payload(candidate)
            if selected is not None:
                selection_reason = "trusted_ranked_match"
                break

    implementation_role = LUNA_ROLE if lane == "luna" else TERRA_ROLE
    workflow: Dict[str, object] = {
        "routing": _stage(ROUTING_ROLE, config, evidence),
        "planning": _stage(ROUTING_ROLE, config, evidence) if high_risk else None,
        "implementation": _stage(implementation_role, config, evidence),
        "independent_review": _stage(REVIEW_ROLE, config, evidence) if high_risk else None,
    }
    verification = {
        "required": ["focused_tests", "regression_tests"],
        "independent_review_required": high_risk,
        "required_roles": [ROUTING_ROLE, implementation_role, *([REVIEW_ROLE] if high_risk else [])],
    }
    return {
        "schema_version": 1,
        "route": dict(route),
        "workflow": workflow,
        "selected_specialist": selected,
        "specialist_selection": {
            "suppressed": suppressed,
            "reason": selection_reason,
            "trusted_context_provided": bool(scoped_context),
        },
        "fallback": "continue_without_specialist" if selected is None else None,
        "verification": verification,
        "role_evidence": _role_payload(evidence),
    }
