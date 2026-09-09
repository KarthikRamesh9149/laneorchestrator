"""One auditable route-card contract composed from routing and discovery.

This module deliberately consumes discovery records as data.  It never treats a
specialist description as configuration or parses a model identifier from it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Mapping, Optional, Sequence

from .discovery import Capability, TRUSTED_SOURCES, rank
from .adaptive import policy
from .routing import RouteFacts, adaptive_risk_signals, has_editorial_target, validate_route_facts
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


def build_adaptive_card(facts: RouteFacts, config: EffectiveConfig,
                        evidence: Mapping[str, RoleEvidence],
                        candidates: Sequence[Capability], context: Sequence[str]) -> Dict[str, object]:
    """Scope evidence and expertise for Astra without pretending to select a model.

    The CLI supplies deterministic constraints. Astra performs the semantic task
    assessment and submits a selection to the host-supported dispatch validator.
    The legacy v1 keyword router remains available for existing integrations.
    """

    validate_route_facts(facts)
    if set(evidence) != set(config.roles):
        raise ValueError("route evidence must cover every logical role")
    signals = adaptive_risk_signals(facts.objective)
    investigate = facts.read_only or facts.risk == "unknown" or not facts.known_area or not facts.acceptance_criteria
    inspected_editorial = (facts.change_scope == "editorial" and facts.risk == "low"
                          and not investigate and has_editorial_target(facts.objective))
    consequential = facts.risk == "high" or (bool(signals) and not inspected_editorial)
    review_required = facts.require_review or consequential
    kind = "investigation" if investigate else "small" if facts.risk == "low" and facts.files == 1 and not consequential else "routine"
    required = [ROUTING_ROLE]
    if not investigate:
        required.append(LUNA_ROLE if kind == "small" else TERRA_ROLE)
        if review_required:
            required.append(REVIEW_ROLE)
    selected = None
    if context:
        for candidate in rank(facts.objective, candidates, context):
            selected = _specialist_payload(candidate)
            if selected is not None:
                selected["availability"] = Availability.UNKNOWN.value
                selected["profile_discovered"] = True
                selected["runtime_observed"] = False
                break
    selection_policy = policy()
    selection_policy["preset"] = config.preset
    return {
        "schema_version": 2,
        "task_kind": kind,
        "assessment": {"risk": facts.risk, "files": facts.files, "known_area": facts.known_area,
                       "acceptance_criteria": facts.acceptance_criteria, "risk_signals": signals,
                       "change_scope": facts.change_scope,
                       "read_only": facts.read_only, "require_review": facts.require_review,
                       "editorial_scope_asserted": inspected_editorial},
        "policy": selection_policy,
        "configured_preferences": {role: {"model": value.model, "reasoning_effort": value.reasoning_effort}
                                   for role, value in config.roles.items()},
        "selection_status": "awaiting_astra_decision",
        "selected_specialist": selected,
        "verification": {"independent_review_required": review_required,
                         "required_roles": required, "strategy": "proportionate_to_changed_behavior"},
        "role_evidence": _role_payload(evidence),
        "execution": {"status": "not_dispatched", "runtime_observed": False,
                      "profile_readiness": all(evidence[role].availability is Availability.AVAILABLE for role in required),
                      "next_step": "inspect_scope" if investigate else "astra_select_model_and_thinking"},
    }


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
    dynamic = getattr(candidate, "model_binding", "unknown") == "per-task"
    if candidate.source not in TRUSTED_SOURCES or (not dynamic and (
        not is_valid_model_id(model) or not is_valid_reasoning_effort(effort)
    )):
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
        "model_binding": "per-task" if dynamic else "profile",
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
