# -*- coding: utf-8 -*-
"""The ⚠ lines in ``explanation`` restate part of the gap report.

That makes them a derived view, and a view has to be derived again when
its source changes. It was not: a point estimate arriving withdrew
``answer_is_bounds_not_point_estimate`` from the gaps and left its line —
"the answer is a symbolic interval, not a point estimate; the renderer
must state this is bounds rather than a specific number" — on 246 of one
suite run's envelopes, every one of which had just computed a number. The
renderer prompt makes every ⚠ line must-quote, so that is not a dormant
field: it is an instruction to withhold the answer, shipped beside the
answer.

The invariant these hold is stated without naming any kind: of the caveat
lines the identification pass wrote, exactly those whose gap survived are
still there. Naming the kind would pass a table that had drifted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.gaps import describe
from themis.types import (
    MIRRORED_INTO_EXPLANATION,
    NOT_MIRRORED_INTO_EXPLANATION,
    GapKind,
    mirrored_caveat_lines,
)


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _effect_query(qid: str = "q") -> dict:
    return {
        "kind": "query", "id": qid, "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [],
        },
    }


def _identifiable_program() -> dict:
    """Z confounds X and Y and is observed, so the back door closes.

    Bounds are attached anyway while theta is missing, which is what puts
    the caveat on the envelope; supplying data then answers the query for
    real and the caveat has to go.
    """
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            _effect_query(),
        ],
    }


def _unidentifiable_program() -> dict:
    """A latent common cause, so no point is honest however much data
    arrives — the caveat is still true and has to stay."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            _effect_query(),
        ],
    }


def _frame(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.4
    x = rng.random(n) < (0.3 + 0.4 * z)
    y = rng.random(n) < (0.2 + 0.3 * x + 0.3 * z)
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _lines(result: dict) -> list[str]:
    return [ln.strip() for ln in (result.get("explanation") or "").split("\n") if ln.strip()]


def _gaps(result: dict) -> list[dict]:
    return list(((result.get("data_gap_report") or {}).get("gaps") or []))


# --------------------------------------------------------------- the table

def test_every_gap_kind_says_whether_it_is_mirrored():
    """The two rows partition the enum. The import-time check enforces it;
    this states it where someone adding a kind will read it."""
    assert MIRRORED_INTO_EXPLANATION | NOT_MIRRORED_INTO_EXPLANATION == frozenset(GapKind)
    assert not (MIRRORED_INTO_EXPLANATION & NOT_MIRRORED_INTO_EXPLANATION)


def test_the_declaration_agrees_with_the_list_it_replaced():
    """The whitelist the scheduler used to keep, kept as the thing the
    declaration has to reproduce — a move that changes the set is a
    behaviour change wearing a refactor's clothes."""
    from themis.runtime.scheduler import _LEGACY_MUST_DISCLOSE_GAP_KINDS

    assert {k.value for k in MIRRORED_INTO_EXPLANATION} == set(
        _LEGACY_MUST_DISCLOSE_GAP_KINDS
    )


def test_mirrored_lines_are_written_in_one_place():
    """Two modules derive these lines and one withdraws them; they agree
    down to the marker only because one function writes it."""
    gaps = [{"kind": GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE.value,
             "describes": [{"sentence": "tian_found_a_hedge"}]},
            {"kind": GapKind.MISSING_DISTRIBUTION.value,
             "describes": [{"sentence": "a_distribution_is_missing",
                            "said": {"what": "P(y|x)"}}]}]
    assert mirrored_caveat_lines(gaps) == {
        "⚠ " + describe({"sentence": "tian_found_a_hedge"})}


# ------------------------------------------------------- the live behaviour

def test_a_point_estimate_withdraws_the_bounds_caveat_it_contradicts():
    program = _identifiable_program()

    structural = themis.run(program)["results"][0]
    before = mirrored_caveat_lines(_gaps(structural))
    assert any("不是点估计" in ln for ln in before), (
        "fixture no longer produces the caveat this is about"
    )
    assert set(before) <= set(_lines(structural))

    solved = themis.estimate(program, _frame())["results"][0]
    assert solved["status"] == "numerically_solved"
    assert solved["numeric_estimate"]["point"] is not None

    # Of the caveat lines the identification pass wrote, exactly those
    # whose gap survived are still there. Stated without naming a kind:
    # naming one would pass a table that had drifted.
    assert set(_lines(solved)) & before == mirrored_caveat_lines(_gaps(solved))
    assert not any("不是点估计" in ln for ln in _lines(solved))


def test_the_caveats_a_number_does_not_contradict_stay():
    """The withdrawal is targeted. An answer that came out of data does
    not make the intervention well defined, or the DAG complete."""
    program = _identifiable_program()
    structural = themis.run(program)["results"][0]
    solved = themis.estimate(program, _frame())["results"][0]

    survived = mirrored_caveat_lines(_gaps(solved))
    assert len(survived) >= 2, (
        "fixture no longer carries caveats that outlive the estimate"
    )
    assert survived <= set(_lines(solved))
    assert survived < mirrored_caveat_lines(_gaps(structural))


def test_an_unidentifiable_query_keeps_its_bounds_caveat():
    """No amount of data licenses a point here, so the line is still true.
    The reconciliation gate reads the unidentifiable gap; this holds it to
    leaving the explanation alone as well."""
    program = _unidentifiable_program()
    structural = themis.run(program)["results"][0]
    assert any("不是点估计" in ln for ln in _lines(structural))

    df = _frame()
    solved = themis.estimate(program, df[["x", "y"]])["results"][0]
    assert any("不是点估计" in ln for ln in _lines(solved)), (
        "the honest answer is still an interval; the caveat may not be dropped"
    )


@pytest.mark.parametrize(
    "make_program", [_identifiable_program, _unidentifiable_program],
    ids=["identifiable", "unidentifiable"],
)
def test_the_view_matches_its_source_on_both_paths(make_program):
    """Every mirrored gap the final report states has its line, and no
    line the identification pass wrote outlives its gap."""
    program = make_program()
    structural = themis.run(program)["results"][0]
    wrote = mirrored_caveat_lines(_gaps(structural))
    assert wrote, "a fixture that writes no caveat proves nothing here"

    for result in (structural, themis.estimate(program, _frame())["results"][0]):
        implied = mirrored_caveat_lines(_gaps(result))
        lines = set(_lines(result))
        assert implied <= lines, "a gap the report states without its ⚠ line"
        assert lines & wrote == implied, "a ⚠ line that outlived its gap"
