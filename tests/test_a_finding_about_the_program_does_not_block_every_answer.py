"""One mismatch, two scopes: whose finding it is, and whose cost.

Reconciling a declared measurement type against the supplied column
produces a finding about the PROGRAM — this column disagrees with what
was declared for it — which is true on every result the program
produces. What that costs belongs to the ANSWER in hand: a column no
query estimated changes no number in it.

Written as one gap the two could only be carried at the stronger of the
pair, and the stronger one is ``domain_violated`` blocking
``point_estimate``. So a variable declared in the program, supplied out
of its declared range, and used by no query at all blocked the point
estimate of every query there was.

Nothing is dropped to fix it. The finding still reaches every result,
because ``extensions.type_reconciliation`` reaches no reader surface at
all and the gap is the only way it arrives; what changes is that off the
estimand it is informational and touches interpretation, and says so in
its own sentence rather than leaving the reader to infer which claim
was meant.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import (
    _TYPE_MISMATCH_BLOCKS,
    _attach_type_reconciliation,
    _names_this_result_stands_on,
)
from themis.verifier import verify_type_reconciliation
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(extra_variables=(), extra_edges=()):
    """Backdoor z→x, z→y, x→y, plus whatever the case adds."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            *extra_variables,
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            *extra_edges,
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _frame(extra_columns=None, n=400, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    frame = pd.DataFrame({
        "x": x.astype(bool), "y": y.astype(bool), "z": z.astype(bool),
    })
    for name, values in (extra_columns or {}).items():
        frame[name] = values(rng, n)
    return frame


def _reconciled(program, frame):
    out = themis.run(program)
    _attach_type_reconciliation(program, out, frame)
    return out["results"][0]


def _mismatch_gaps(result):
    gaps = (result.get("data_gap_report") or {}).get("gaps") or []
    return [g for g in gaps if g.get("kind") == "declared_type_data_mismatch"]


#: A variable declared discrete over {0, 1}, supplied with a 2, wired to
#: nothing. Nothing estimates it; the declaration is still wrong.
_UNUSED_OUT_OF_RANGE = (
    ({"kind": "variable", "predicate": "w", "scale": "discrete",
      "domain": [0, 1]},),
    {"w": lambda rng, n: rng.integers(0, 3, n)},
)

#: The same disagreement on a column the answer does stand on: z is the
#: back-door adjustment set.
_ADJUSTMENT_OUT_OF_RANGE = (
    (),
    None,
)


def _unused_case():
    variables, columns = _UNUSED_OUT_OF_RANGE
    return _reconciled(_program(variables), _frame(columns))


# ------------------------------------------------- the finding still arrives


def test_a_column_no_query_estimated_is_still_reported():
    result = _unused_case()
    gaps = _mismatch_gaps(result)
    assert len(gaps) == 1
    assert "`w`" in gaps[0]["description"]
    # And the evidence is on the result either way — it is on every result,
    # because the finding is the program's.
    checks = result["extensions"]["type_reconciliation"]["checks"]
    assert [c["predicate"] for c in checks] == ["w"]


def test_a_column_no_query_estimated_blocks_no_estimate():
    result = _unused_case()
    gap = _mismatch_gaps(result)[0]
    # The verdict whose consequence, ON the estimand, is the strongest one
    # there is — which is what a single-scope gap had to carry everywhere.
    assert gap["signature"] == "domain_violated"
    assert _TYPE_MISMATCH_BLOCKS["domain_violated"] == "point_estimate"
    assert gap["blocks"] == "interpretation"
    assert gap["severity"] == "informational"


def test_the_sentence_says_which_of_the_two_claims_it_is():
    """A reader cannot act on a finding without knowing whose it is."""
    gap = _mismatch_gaps(_unused_case())[0]
    assert "不在本查询的估计量里" in gap["description"]
    assert "程序的声明" in gap["description"]


def test_the_remedies_are_the_same_because_they_are_the_programs():
    """Fix the column or fix the declaration — true whichever query asks."""
    gap = _mismatch_gaps(_unused_case())[0]
    assert len(gap["alternative_paths"]) == 2


# --------------------------------------------------- and still blocks on it


def test_a_column_the_answer_stands_on_still_blocks_the_estimate():
    variables, _ = _ADJUSTMENT_OUT_OF_RANGE
    program = _program(variables)
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "z":
            stmt["scale"] = "discrete"
            stmt["domain"] = [True]          # supplied column carries False too
    result = _reconciled(program, _frame())
    gap = _mismatch_gaps(result)[0]
    assert "z" in _names_this_result_stands_on(result)
    assert gap["signature"] == "domain_violated"
    assert gap["blocks"] == "point_estimate"
    assert gap["severity"] == "important"


# ------------------------------------------------------ the reading itself


def test_the_reconciliation_block_does_not_make_a_column_stand():
    """It names every declared predicate, so counting it says yes always."""
    result = _unused_case()
    assert "w" in {
        c["predicate"]
        for c in result["extensions"]["type_reconciliation"]["checks"]
    }
    assert "w" not in _names_this_result_stands_on(result)


def test_the_gap_report_does_not_make_a_column_stand():
    """The answer being written is not evidence for itself."""
    result = _unused_case()
    result["data_gap_report"]["gaps"].append({
        "kind": "invented", "signature": "w", "severity": "informational",
        "blocks": "interpretation", "description": "w", "provenance": [],
    })
    assert "w" not in _names_this_result_stands_on(result)


def test_what_the_answer_does_stand_on_is_found():
    result = _unused_case()
    names = _names_this_result_stands_on(result)
    assert {"x", "y", "z"} <= names


# -------------------------------------------------- the verifier's own read


def test_the_verifier_accepts_the_scoped_pair():
    verify_type_reconciliation(_unused_case())


def test_the_verifier_refuses_a_program_finding_dressed_as_this_answers():
    result = _unused_case()
    tampered = copy.deepcopy(result)
    gap = _mismatch_gaps(tampered)[0]
    gap["severity"] = "important"
    gap["blocks"] = "point_estimate"
    with pytest.raises(VerificationError) as exc:
        verify_type_reconciliation(tampered)
    assert "does not stand on" in str(exc.value)


def test_the_verifier_refuses_this_answers_cost_downgraded():
    variables, _ = _ADJUSTMENT_OUT_OF_RANGE
    program = _program(variables)
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "z":
            stmt["scale"] = "discrete"
            stmt["domain"] = [True]
    tampered = _reconciled(program, _frame())
    gap = _mismatch_gaps(tampered)[0]
    gap["severity"] = "informational"
    gap["blocks"] = "interpretation"
    with pytest.raises(VerificationError) as exc:
        verify_type_reconciliation(tampered)
    assert "stands on" in str(exc.value)
