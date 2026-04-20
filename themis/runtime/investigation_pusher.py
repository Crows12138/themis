"""Translate missing-information findings into actionable investigation
requests.

v0.2 (slice 9.x-B) groups items by ``MissingKind`` — one request per
kind, with per-item detail carried in ``items``. Scheduler may hand
in a per-name skeleton map so PARAMETER items can carry a
paste-ready ``probabilityStatement`` stub.

MissingKind → InvestigationAction mapping:

- ``parameter``   → ``validate_parameter``
- ``observation`` → ``collect_observation``
- ``sample``      → ``increase_sample``
- ``structure``   → ``run_experiment``   (best-effort; some
                      structure gaps are not repairable by
                      experiments — the mapping is suggestive only)

Group priority is the max priority among its items (HIGH > MEDIUM >
LOW). Input ordering is preserved: groups appear in the order their
first item was encountered; items within a group preserve input
order.
"""
from __future__ import annotations

from ..types import (
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    MissingItem,
    MissingKind,
    Priority,
)


_ACTION_OF: dict[MissingKind, InvestigationAction] = {
    MissingKind.PARAMETER:   InvestigationAction.VALIDATE_PARAMETER,
    MissingKind.OBSERVATION: InvestigationAction.COLLECT_OBSERVATION,
    MissingKind.SAMPLE:      InvestigationAction.INCREASE_SAMPLE,
    MissingKind.STRUCTURE:   InvestigationAction.RUN_EXPERIMENT,
}


_PRIORITY_ORDER: dict[Priority, int] = {
    Priority.LOW:    0,
    Priority.MEDIUM: 1,
    Priority.HIGH:   2,
}


def _max_priority(priorities) -> Priority:
    return max(priorities, key=_PRIORITY_ORDER.get)


def _summary_target(kind: MissingKind, items) -> str:
    if len(items) == 1:
        return items[0].target
    return f"{kind.value}:{len(items)}_items"


def _summary_note(items) -> str | None:
    """Surface the item reason for single-item groups; for multi-item
    groups collapse only if all reasons are identical."""
    if len(items) == 1:
        return items[0].reason
    unique_reasons = {i.reason for i in items if i.reason is not None}
    if len(unique_reasons) == 1:
        return next(iter(unique_reasons))
    if not unique_reasons:
        return None
    return f"{len(items)} items with distinct reasons"


def push(
    missing: tuple[MissingItem, ...],
    *,
    skeletons: dict | None = None,
) -> tuple[InvestigationRequest, ...]:
    """Map MissingItem tuple → grouped InvestigationRequest tuple.

    One request per distinct MissingKind present in the input. Items
    within a group preserve input order. Groups emerge in the order
    their first item was encountered.

    ``skeletons`` is an optional ``{missing_item.name: skeleton_dict}``
    map supplied by the scheduler. PARAMETER items whose name appears
    as a key get a paste-ready ``probabilityStatement`` stub attached
    to their ``InvestigationItem.skeleton``. Other kinds ignore it.
    """
    if not missing:
        return ()
    skeletons = skeletons or {}

    # Group preserving first-seen order.
    groups: dict[MissingKind, list[MissingItem]] = {}
    for m in missing:
        groups.setdefault(m.kind, []).append(m)

    result: list[InvestigationRequest] = []
    for kind, group_items in groups.items():
        action = _ACTION_OF[kind]
        inv_items = tuple(
            InvestigationItem(
                target=m.name,
                reason=m.reason,
                skeleton=(
                    skeletons.get(m.name)
                    if kind is MissingKind.PARAMETER
                    else None
                ),
            )
            for m in group_items
        )
        priority = _max_priority(m.priority for m in group_items)
        result.append(
            InvestigationRequest(
                action=action,
                target=_summary_target(kind, inv_items),
                priority=priority,
                note=_summary_note(inv_items),
                group=kind.value,
                items=inv_items,
            )
        )
    return tuple(result)
