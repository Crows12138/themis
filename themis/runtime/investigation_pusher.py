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
- ``assumption``  → ``define_assumption``

Group priority is the max priority among its items (HIGH > MEDIUM >
LOW). Input ordering is preserved: groups appear in the order their
first item was encountered; items within a group preserve input
order.

``MissingItem.gap`` — what kind of shortfall this is — is carried
through untouched, as is ``superseded_by_estimation``. This module
translates the repair channel into an action; it does not get an opinion
on the species or on what settles it, and the report downstream reads
what the kernel declared rather than inferring it from the grouping.
"""
from __future__ import annotations

from typing import Sequence

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
    MissingKind.ASSUMPTION:  InvestigationAction.DEFINE_ASSUMPTION,
}


_PRIORITY_ORDER: dict[Priority, int] = {
    Priority.LOW:    0,
    Priority.MEDIUM: 1,
    Priority.HIGH:   2,
}


def _max_priority(priorities: Sequence[Priority]) -> Priority:
    # Indexing, not ``.get``: a priority the order does not rank is a hole in
    # the table above, and it should say so rather than sort as ``None``.
    return max(priorities, key=_PRIORITY_ORDER.__getitem__)


def summarise(
    group: str,
    entries: "Sequence[tuple[str, str | None, Priority]]",
) -> "tuple[str, str | None, Priority]":
    """How a request describes the items it holds: target, note, priority.

    A single item speaks for itself; several are named by their count,
    and share a note only when they share a reason. The group priority
    is the strongest among them.

    Stated once because it is applied twice. This module summarises when
    the kernel first writes what it lacks; the estimation pass
    re-summarises when the arriving sample answers part of it. A second
    copy of the rule there would let a request keep a summary describing
    items it no longer holds — "4_items" over two of them — which is the
    same drift by a shorter route.

    Takes ``(target, reason, priority)`` triples rather than a dataclass
    so the pass working on a serialized envelope can call it too.
    """
    priority = _max_priority([p for _, _, p in entries])
    if len(entries) == 1:
        target, note, _ = entries[0]
        return target, note, priority
    reasons = {r for _, r, _ in entries if r is not None}
    if len(reasons) == 1:
        note = next(iter(reasons))
    elif not reasons:
        note = None
    else:
        note = f"{len(entries)} 条，各有各的原因"
    return f"{group}:{len(entries)}_items", note, priority


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
                gap=m.gap,
                superseded_by_estimation=m.superseded_by_estimation,
            )
            for m in group_items
        )
        target, note, priority = summarise(
            kind.value,
            [(i.target, i.reason, m.priority)
             for i, m in zip(inv_items, group_items)],
        )
        result.append(
            InvestigationRequest(
                action=action,
                target=target,
                priority=priority,
                note=note,
                group=kind.value,
                items=inv_items,
            )
        )
    return tuple(result)
