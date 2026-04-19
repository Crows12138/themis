"""Translate missing-information findings into concrete investigation
requests that the caller can act on.

When a query is structurally defined but lacks parameters / observations
/ samples, the scheduler routes it to ``needs_investigation``. This
module turns the list of missing items into actionable suggestions:

- ``parameter``   -> ``validate_parameter``
- ``observation`` -> ``collect_observation``
- ``sample``      -> ``increase_sample``
- ``structure``   -> ``run_experiment``   (best-effort default;
                      some structure gaps are not repairable by
                      experiments — the request is suggestive only)

Priorities pass through from the MissingItem unchanged. v0.1 does not
derive richer priorities from context; that heuristic can be replaced
in a later version without touching call sites.
"""
from __future__ import annotations

from ..types import (
    InvestigationAction,
    InvestigationRequest,
    MissingItem,
    MissingKind,
)


_ACTION_OF: dict[MissingKind, InvestigationAction] = {
    MissingKind.PARAMETER:   InvestigationAction.VALIDATE_PARAMETER,
    MissingKind.OBSERVATION: InvestigationAction.COLLECT_OBSERVATION,
    MissingKind.SAMPLE:      InvestigationAction.INCREASE_SAMPLE,
    MissingKind.STRUCTURE:   InvestigationAction.RUN_EXPERIMENT,
}


def _request_for(item: MissingItem) -> InvestigationRequest:
    return InvestigationRequest(
        action=_ACTION_OF[item.kind],
        target=item.name,
        priority=item.priority,
        note=item.reason,
    )


def push(missing: tuple[MissingItem, ...]) -> tuple[InvestigationRequest, ...]:
    """Map a tuple of MissingItem into InvestigationRequest suggestions."""
    return tuple(_request_for(m) for m in missing)
