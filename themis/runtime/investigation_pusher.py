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

import json
from typing import Sequence

from .. import gaps
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
    entries: "Sequence[tuple[str, dict | None, Priority]]",
) -> "tuple[str, dict | None, Priority]":
    """How a request describes the items it holds: target, note, priority.

    A single item speaks for itself; several are named by their count,
    and share a note only when they are asking for the same thing for the
    same reason. The group priority is the strongest among them.

    When they are not, the group has NO note. What a note answers is
    "what do these have in common", and the honest answer to a mixed
    group is nothing — the count is already in the target. The sentence
    that used to stand here said the count again and called it a reason.

    Stated once because it is applied twice. This module summarises when
    the kernel first writes what it lacks; the estimation pass
    re-summarises when the arriving sample answers part of it. A second
    copy of the rule there would let a request keep a summary describing
    items it no longer holds — "4_items" over two of them — which is the
    same drift by a shorter route.

    Takes ``(target, note, priority)`` triples rather than a dataclass so
    the pass working on a serialized envelope can call it too, and the
    note is the species-and-occasion mapping both sides carry rather than
    a sentence, so that "the same reason" is decided on the facts and not
    on whether two renderings came out the same length.
    """
    priority = _max_priority([p for _, _, p in entries])
    if len(entries) == 1:
        target, note, _ = entries[0]
        return target, note, priority
    seen = {json.dumps(n, sort_keys=True, ensure_ascii=False): n
            for _, n, _ in entries if n}
    note = next(iter(seen.values())) if len(seen) == 1 else None
    return f"{group}:{len(entries)}_items", note, priority


def push(
    missing: tuple[MissingItem, ...],
) -> tuple[InvestigationRequest, ...]:
    """Map MissingItem tuple → grouped InvestigationRequest tuple.

    One request per distinct MissingKind present in the input. Items
    within a group preserve input order. Groups emerge in the order
    their first item was encountered.

    The paste-ready statement rides on the item, so this projects it the
    way it projects the species and the occasion. It used to arrive as a
    second argument — a ``{missing_item.name: skeleton}`` map — which made
    the ask and the statement that would settle it two objects joined by
    the rendered name, and left every caller that did not carry the map
    handing the reader an ask with nothing to paste.
    """
    if not missing:
        return ()

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
                need=m.need,
                said=m.said,
                words=m.words,
                skeleton=m.skeleton,
                gap=m.gap,
                superseded_by_estimation=m.superseded_by_estimation,
            )
            for m in group_items
        )
        target, note, priority = summarise(
            kind.value,
            [(i.target, gaps.carried(i), m.priority)
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
