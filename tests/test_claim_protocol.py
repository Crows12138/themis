"""The estimation cascade's claim protocol (Phase 17 slice 1).

Before this protocol the cascade carried a handler's decision in two
incompatible conventions — ten handlers returned ``bool``, nine returned
``None``, and one of the ten meant the OPPOSITE of the other nine — and
none of them could say the thing that decides correctness: whether a
handler owns a query it could not answer. Two measured defects came out of
exactly that gap, so the protocol is pinned here rather than left to
review.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis.estimation.claim import (
    BLOCK_REASONS,
    Claim,
    annotated,
    answered,
    blocked,
    passed,
)

_DISPATCH = pathlib.Path(
    __import__("themis").__file__
).parent / "estimation" / "dispatch.py"

_CONSTRUCTORS = {"answered", "blocked", "passed", "annotated"}


def _handlers() -> list[ast.FunctionDef]:
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    return [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("_try_")
    ]


def _own_returns(node: ast.FunctionDef) -> list[ast.Return]:
    """Returns belonging to this handler, not to a closure inside it."""
    nested = {
        s for f in ast.walk(node)
        if isinstance(f, ast.FunctionDef) and f is not node
        for s in ast.walk(f) if isinstance(s, ast.Return)
    }
    return [
        s for s in ast.walk(node)
        if isinstance(s, ast.Return) and s not in nested
    ]


# --- the protocol itself ------------------------------------------------


def test_the_four_outcomes_differ_where_it_matters():
    """``blocked`` is the one that stops the cascade without an answer — the
    state the old bool could not express."""
    assert answered().stops_here and answered().answered
    assert blocked("not_identified").stops_here
    assert not blocked("not_identified").answered
    assert not annotated().stops_here
    assert not passed("estimator_refused").stops_here


def test_a_decline_must_name_a_registered_reason():
    """An open vocabulary is an unauditable one: a typo would become a new
    category nobody ever reads."""
    with pytest.raises(ValueError, match="unregistered"):
        blocked("something_went_wrong")
    with pytest.raises(ValueError, match="unregistered"):
        passed("something_went_wrong")


def test_every_registered_reason_says_who_can_change_it():
    """A reason is only actionable if the reader can tell whether it is
    their graph, their data, or this package that has to change."""
    for name, text in BLOCK_REASONS.items():
        assert len(text) > 40, name


def test_claim_is_immutable():
    with pytest.raises(Exception):
        answered().owned = False  # type: ignore[misc]


# --- every handler speaks it -------------------------------------------


def test_every_handler_returns_a_claim():
    offenders = [
        n.name for n in _handlers()
        if not (n.returns and ast.unparse(n.returns) == "Claim")
    ]
    assert not offenders, offenders


def test_no_handler_still_returns_a_bare_bool_or_none():
    """The two old conventions are gone, including the handler whose True
    meant the opposite of everyone else's."""
    offenders = []
    for node in _handlers():
        for ret in _own_returns(node):
            ok = (
                isinstance(ret.value, ast.Call)
                and isinstance(ret.value.func, ast.Name)
                and ret.value.func.id in _CONSTRUCTORS
            )
            if not ok:
                offenders.append(f"{node.name}:{ret.lineno}")
    assert not offenders, offenders


def test_every_reason_literal_in_dispatch_is_registered():
    """Caught statically as well as at runtime: a reason on a path no test
    exercises would otherwise reach a user before it reached a test."""
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    unregistered = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"blocked", "passed"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            if node.args[0].value not in BLOCK_REASONS:
                unregistered.append((node.lineno, node.args[0].value))
    assert not unregistered, unregistered


def test_a_handler_that_annotates_may_stop_the_query_only_on_what_it_learned():
    """Ownership is a property of the handler, not of the outcome.

    A handler whose success exit is ``annotated()`` has no estimand of its
    own — whoever answers the query answers it — so an exit of the SAME
    handler that returns ``blocked()`` takes the query away from the one that
    would have produced the number. That is how declaring an outcome
    measurement error came to cost the caller their front-door and IV
    estimate: the row stopped on ``not adjustment_sets``, which is exactly
    what DEFINES those two routes.

    One handler legitimately does both, and the line it turns on is not
    syntactic, which is why this is a census and not a ban: it may stop the
    query on what it LEARNED (a declared variance that does not fit under the
    residual variation puts in doubt the very independence premise that made
    the point safe) and never on what it could not REACH. A second name here
    means someone drew that line again — come and read it.
    """
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    both = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        verbs = {
            r.value.func.id for r in _own_returns(node)
            if isinstance(r.value, ast.Call)
            and isinstance(r.value.func, ast.Name)
            and r.value.func.id in _CONSTRUCTORS
        }
        if {"annotated", "blocked"} <= verbs:
            both.append(node.name)

    assert both == ["_try_outcome_error_assessment"], both


def test_no_handler_is_dispatched_by_a_hand_written_branch():
    """``Claim`` is a dataclass, so ``if handler(...)`` is truthy always and
    would silently claim every query — a defect this suite has already
    caught once, in the migration that introduced the type.

    Since the cascade became a table there is exactly one place that reads
    a claim, so the property worth holding is stronger than "call sites say
    ``.stops_here``": no call site branches on a handler at all. A new
    ``if`` around a handler is a second dispatcher, and two dispatchers is
    how the layers drifted apart in the first place.
    """
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id.startswith("_try_")
            ):
                offenders.append(f"{sub.func.id}:{sub.lineno}")
    assert not offenders, offenders
