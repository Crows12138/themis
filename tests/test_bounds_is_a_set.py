"""One estimand, several methods, no ranking to pick between them.

The bounds pass used to return the first method that fired. All three
bracket the same quantity — ``estimand`` is ``arm_probability`` on every
one — under assumption sets that do not contain one another, so nothing
ranked them and the winner was whichever branch ran first.

Two things followed, and only the second had instances. A query
declaring BOTH an instrument and a monotone treatment response got the
instrument by line order; no program in this repo does that, so it never
happened. But the assumption-free floor was computed LAST, under a guard
that held only when nothing sharper had fired — so every answer that
reached a sharper method lost the one interval that assumes nothing,
which is what the channel exists to provide.
"""
from __future__ import annotations

import copy

import pytest

import themis
from tests.bounds_rows import methods, row


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*, instrument: bool, monotone: bool) -> dict:
    """X→Y with a bow arc (point ID fails), optionally with Z→X.

    The instrument is structural (Z→X, no Z→Y); the monotonicity is a
    declaration the caller makes in words. That is the whole reason the
    two intervals are incomparable: one is read off the graph, the other
    is asserted, and neither assumption set contains the other.
    """
    statements: list[dict] = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    ]
    if instrument:
        statements.insert(
            0, {"kind": "variable", "predicate": "z", "domain": [True, False]})
        statements.append(
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")})
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
        },
    })
    program: dict = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }
    if monotone:
        program["extensions"] = {
            "monotonicity": {
                "target": "y", "treatment": "x", "direction": "non_decreasing",
            }
        }
    return program


def _result(**kw) -> dict:
    return themis.run(_program(**kw))["results"][0]


# --- the floor is never displaced -------------------------------------------

def test_the_assumption_free_floor_survives_a_sharper_method():
    """The instance the measurement found: 3 of 36 bounded answers reached
    a sharper method, and all 3 lost the floor to it."""
    res = _result(instrument=True, monotone=False)
    assert methods(res) == ["manski_natural", "balke_pearl_iv"]
    # Omitted from the envelope when empty, which is what "no assumptions"
    # looks like on the wire.
    assert not row(res, "manski_natural").get("assumptions")


def test_the_floor_is_alone_when_nothing_sharper_applies():
    """The counterexample: the set is not padded — a row appears only when
    its assumptions are actually supported."""
    assert methods(_result(instrument=False, monotone=False)) == [
        "manski_natural",
    ]


# --- the state the chain could not express ----------------------------------

def test_two_incomparable_assumption_sets_both_answer():
    """Both apply, so both are reported. Under the chain this query got
    Balke-Pearl because it was tried first — a decision by line order
    between a monotonicity the caller asserted and IV conditions read off
    the graph, which nothing ranks."""
    res = _result(instrument=True, monotone=True)
    assert methods(res) == [
        "manski_natural", "manski_tamer_monotonicity", "balke_pearl_iv",
    ]


def test_every_row_brackets_the_same_quantity():
    """What makes them a set rather than three answers: one estimand.

    Rows over different estimands would not be a choice for the reader at
    all, and the 'do not intersect' advice would be nonsense.
    """
    res = _result(instrument=True, monotone=True)
    assert {b["estimand"] for b in res["bounds_results"]} == {
        "arm_probability",
    }


def test_each_row_carries_the_assumptions_that_produced_it():
    """The only thing that separates them, and so the only thing that lets
    a reader choose."""
    res = _result(instrument=True, monotone=True)
    # Omitted from the envelope when empty, which is what "no assumptions"
    # looks like on the wire.
    assert not row(res, "manski_natural").get("assumptions")
    assert row(res, "manski_tamer_monotonicity")["assumptions"] == [
        "mtr_non_decreasing",
    ]
    assert row(res, "balke_pearl_iv")["assumptions"]


def test_dropping_the_declaration_drops_exactly_its_row():
    """Order carries no meaning now, so removing one premise must remove
    one row and leave the others where they were."""
    both = methods(_result(instrument=True, monotone=True))
    without = methods(_result(instrument=True, monotone=False))
    assert set(both) - set(without) == {"manski_tamer_monotonicity"}
    assert without == [m for m in both if m != "manski_tamer_monotonicity"]


# --- what the reader is told ------------------------------------------------

def test_the_gap_names_every_row_and_what_it_rests_on():
    res = _result(instrument=True, monotone=True)
    gap = next(
        g for g in res["data_gap_report"]["gaps"]
        if g["kind"] == "answer_is_bounds_not_point_estimate"
    )
    for method in methods(res):
        assert method in gap["description"]
    assert "无假设" in gap["description"]
    assert "mtr_non_decreasing" in gap["description"]


def test_the_reader_is_told_not_to_intersect_them():
    """Valid but not sharp, and unlabelled once merged. The advice appears
    only when there is something to merge."""
    assert "不要取交" in _bounds_gap(_result(instrument=True, monotone=True))
    assert "不要取交" not in _bounds_gap(
        _result(instrument=False, monotone=False))


def _bounds_gap(res: dict) -> str:
    return next(
        g["description"] for g in res["data_gap_report"]["gaps"]
        if g["kind"] == "answer_is_bounds_not_point_estimate"
    )


def test_the_report_prints_every_interval_it_has():
    """The main surface. A set that reaches the reader as one number is
    the same loss the slot used to cause, one layer further out."""
    from themis.output.analysis_report import build_analysis_report

    res = _result(instrument=True, monotone=True)
    for b in res["bounds_results"]:
        b["lower_value"], b["upper_value"] = 0.1, 0.9
    md = build_analysis_report(res, program=themis.run(
        _program(instrument=True, monotone=True))["program"])
    for method in methods(res):
        assert method in md


# --- the audit ---------------------------------------------------------------

def test_every_row_is_audited_not_just_the_first():
    """A set audited by its first element is a set with unaudited members.
    Tamper each row in turn; each must be caught."""
    from themis.verifier.errors import VerificationError

    program = _program(instrument=True, monotone=True)
    clean = themis.run(program)["results"][0]
    themis.verify_bounds_results(program, clean)

    for method in methods(clean):
        res = copy.deepcopy(clean)
        row(res, method)["lower_expression"] = "P(y=false)"
        with pytest.raises(VerificationError):
            themis.verify_bounds_results(program, res)
