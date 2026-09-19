"""Unit tests for MissingItem -> InvestigationRequest mapping."""
from __future__ import annotations

from themis import gaps
from themis.runtime.investigation_pusher import push
from themis.types import (
    GapKind,
    InvestigationAction,
    MissingItem,
    MissingKind,
    Priority,
)

#: Two species with the same kind, so items built from either group
#: together and only what they are ASKING FOR differs. The first names a
#: probability, the second names nothing — which is what lets a test say
#: "these two have the same thing to say" without saying it twice.
_NAMED = gaps.Need.THETA_ENTRY_MISSING
_UNSLOTTED = gaps.Need.QUERY_BOUND_ATOM_UNRESOLVED
#: A second species of the same sort, for the one test that needs two
#: items whose notes carry no value slots and whose names differ. They
#: differ by species and not by spelling: a species that says nothing
#: about its occasion is filed under one name every time it is raised,
#: so there is no second spelling of it to hand out.
_UNSLOTTED_TOO = gaps.Need.NO_BACKDOOR_OR_FRONTDOOR


def _mk(kind: MissingKind, subject: str = "x", **occasion) -> MissingItem:
    """An item, built the way the channel that raises one would.

    With a species, through the door — so the name is the one that
    species is filed under, and ``subject`` is the half a site
    supplies where there is one to supply. Where the species settles
    the whole name there is nothing to pass and nothing is passed.

    Without one, the record straight: most of these tests are about
    the pusher's mapping from kind to action, and a species would
    only add a sentence none of them read.
    """
    need = occasion.get("need")
    if need is None:
        return MissingItem(
            kind=kind, name=subject, priority=Priority.MEDIUM,
            gap=GapKind.MISSING_DISTRIBUTION,
        )
    return gaps.missing(
        kind=kind,
        **({"subject": subject} if need in gaps.FILED_UNDER else {}),
        **occasion)


def test_parameter_becomes_validate_parameter():
    reqs = push((_mk(MissingKind.PARAMETER, "P(y|x)"),))
    assert reqs[0].action is InvestigationAction.VALIDATE_PARAMETER
    assert reqs[0].target == "P(y|x)"


def test_observation_becomes_collect_observation():
    reqs = push((_mk(MissingKind.OBSERVATION, "y(alice)"),))
    assert reqs[0].action is InvestigationAction.COLLECT_OBSERVATION


def test_sample_becomes_increase_sample():
    reqs = push((_mk(MissingKind.SAMPLE, "cohort_a"),))
    assert reqs[0].action is InvestigationAction.INCREASE_SAMPLE


def test_structure_becomes_run_experiment():
    reqs = push((_mk(MissingKind.STRUCTURE, "edge:x->y"),))
    assert reqs[0].action is InvestigationAction.RUN_EXPERIMENT


def test_what_the_item_asks_for_is_carried_into_the_note():
    reqs = push((_mk(MissingKind.PARAMETER, "p1",
                     need=_NAMED, key="P(y|x)"),))
    assert reqs[0].note == {
        "need": "theta_entry_missing", "said": {"key": "P(y|x)"},
    }


def test_priority_passes_through():
    item = MissingItem(
        kind=MissingKind.PARAMETER, name="p", priority=Priority.HIGH,
        gap=GapKind.MISSING_DISTRIBUTION,
    )
    reqs = push((item,))
    assert reqs[0].priority is Priority.HIGH


def test_empty_input_empty_output():
    assert push(()) == ()


def test_multiple_items_preserve_order():
    items = (
        _mk(MissingKind.PARAMETER, "a"),
        _mk(MissingKind.OBSERVATION, "b"),
        _mk(MissingKind.SAMPLE, "c"),
    )
    reqs = push(items)
    assert [r.target for r in reqs] == ["a", "b", "c"]


# ------------------------------------------------- slice 9.x-B: grouping

def test_same_kind_items_merge_into_single_group():
    """Three PARAMETER items become one request with items=(3 items).
    The request's target degenerates to a kind-and-count summary."""
    items = (
        _mk(MissingKind.PARAMETER, "P(a|b)"),
        _mk(MissingKind.PARAMETER, "P(c|d)"),
        _mk(MissingKind.PARAMETER, "P(e|f)"),
    )
    reqs = push(items)
    assert len(reqs) == 1
    r = reqs[0]
    assert r.action is InvestigationAction.VALIDATE_PARAMETER
    assert r.group == "parameter"
    assert r.target == "parameter:3_items"
    assert len(r.items) == 3
    assert [it.target for it in r.items] == ["P(a|b)", "P(c|d)", "P(e|f)"]


def test_mixed_kinds_yield_separate_groups_in_first_seen_order():
    items = (
        _mk(MissingKind.PARAMETER, "p1"),
        _mk(MissingKind.OBSERVATION, "o1"),
        _mk(MissingKind.PARAMETER, "p2"),
    )
    reqs = push(items)
    # Two groups: parameter (2 items), observation (1 item), in first-seen order.
    assert len(reqs) == 2
    assert reqs[0].group == "parameter"
    assert [it.target for it in reqs[0].items] == ["p1", "p2"]
    assert reqs[1].group == "observation"
    assert [it.target for it in reqs[1].items] == ["o1"]


def test_group_priority_is_max_across_items():
    items = (
        MissingItem(kind=MissingKind.PARAMETER, name="a", priority=Priority.LOW,
                    gap=GapKind.MISSING_DISTRIBUTION),
        MissingItem(kind=MissingKind.PARAMETER, name="b", priority=Priority.HIGH,
                    gap=GapKind.MISSING_DISTRIBUTION),
        MissingItem(kind=MissingKind.PARAMETER, name="c", priority=Priority.MEDIUM,
                    gap=GapKind.MISSING_DISTRIBUTION),
    )
    reqs = push(items)
    assert reqs[0].priority is Priority.HIGH


def test_single_item_group_still_looks_like_before():
    """One-item groups preserve the pre-9.x-B target/note surface so
    existing callers don't have to care about groups."""
    reqs = push((_mk(MissingKind.PARAMETER, need=_UNSLOTTED),))
    r = reqs[0]
    assert r.target == "numeric:unresolved_query_bound"
    assert r.note == {"need": "query_bound_atom_unresolved"}
    # Items are still populated though, just with one entry.
    assert len(r.items) == 1
    assert r.items[0].target == "numeric:unresolved_query_bound"
    assert r.items[0].need is _UNSLOTTED


def test_a_group_whose_items_ask_for_different_things_has_no_note():
    """What a note answers is "what do these have in common", and for a
    mixed group the honest answer is nothing.

    The count is already in the target, so the sentence that used to
    stand here — "N 条，各有各的原因" — said the count again and called it
    a reason. Sameness is decided on the species and the occasion rather
    than on two rendered sentences, so it does not depend on the language
    they would have been rendered in."""
    reqs = push((
        _mk(MissingKind.PARAMETER, "a", need=_NAMED, key="P(y|x)"),
        _mk(MissingKind.PARAMETER, need=_UNSLOTTED),
    ))
    assert reqs[0].target == "parameter:2_items"
    assert reqs[0].note is None


def test_a_group_asking_the_same_thing_twice_keeps_the_one_note():
    reqs = push((
        _mk(MissingKind.PARAMETER, "a", need=_NAMED, key="P(y|x)"),
        _mk(MissingKind.PARAMETER, "b", need=_NAMED, key="P(y|x)"),
    ))
    assert reqs[0].note == {
        "need": "theta_entry_missing", "said": {"key": "P(y|x)"},
    }


# ------------------------------- the statement that would settle the ask

def test_the_statement_rides_on_the_item():
    """No second argument, and so no call site that can forget one.

    The stub used to arrive as a ``{name: skeleton}`` map beside the
    items, rejoined here by the rendered name. Two call sites carried no
    map at all and 289 asks a run raises reached the reader with nothing
    to paste, while their siblings from the same producer had one."""
    skeleton = {"kind": "probability", "target": {"atom": {}, "value": True}}
    item = MissingItem(
        kind=MissingKind.PARAMETER, name="p1", priority=Priority.MEDIUM,
        gap=GapKind.MISSING_DISTRIBUTION, skeleton=skeleton,
    )
    assert push((item,))[0].items[0].skeleton == skeleton


def test_an_ask_with_no_statement_behind_it_carries_none():
    """A shortfall no statement settles — an atom the graph does not
    declare, an assumption nobody can write down for you."""
    reqs = push((_mk(MissingKind.OBSERVATION, "o1"),))
    assert reqs[0].items[0].skeleton is None
    reqs = push((_mk(MissingKind.PARAMETER, "p1"),))
    assert reqs[0].items[0].skeleton is None


# ============================================ shrinking a written request


def test_a_shrunk_request_describes_the_items_it_still_holds():
    """``summarise`` is applied twice and must say the same thing twice.

    The estimation pass removes the items a supplied sample answered and
    re-summarises what is left. Whatever it produces has to be what this
    module would have produced had only those items ever been raised —
    otherwise a request survives describing a set it no longer holds
    ("parameter:4_items" over two), which is the drift a second copy of
    the rule would have guaranteed.

    Measured note: across the whole suite no request has ever lost a
    strict subset of its items (712 requests reached the shrink; 359 lost
    every item, 353 lost none). The mixed case is reachable in principle
    — a result would have to raise both a study-population ask and a
    named-population one — so the rule is pinned here rather than left to
    a path no test travels.
    """
    from themis.estimation.dispatch import _drop_investigation_items

    raised = (
        _mk(MissingKind.PARAMETER, "P(y|x)", need=_NAMED, key="P(y|x)"),
        _mk(MissingKind.PARAMETER, need=_UNSLOTTED),
        _mk(MissingKind.PARAMETER, need=_UNSLOTTED_TOO),
    )
    written = push(raised)
    result = {
        "investigation_requests": [
            {
                "action": r.action.value,
                "target": r.target,
                "priority": r.priority.value,
                **({"note": r.note} if r.note is not None else {}),
                "group": r.group,
                "items": [
                    {"target": i.target, "gap": i.gap.value,
                     **(gaps.carried(i) or {})}
                    for i in r.items
                ],
            }
            for r in written
        ],
    }
    _drop_investigation_items(
        result,
        {"parameter:P(y|x)"},
        {m.name: m.priority.value for m in raised},
    )

    survived = result["investigation_requests"][0]
    as_if_only_those = push(raised[1:])[0]
    assert survived["target"] == as_if_only_those.target
    assert survived.get("note") == as_if_only_those.note
    assert survived["priority"] == as_if_only_those.priority.value
    assert [i["target"] for i in survived["items"]] == [
        i.target for i in as_if_only_those.items
    ]
