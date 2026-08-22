"""#422 — the shape disclosure was opt-in, so the families nobody wired had none.

The ledger line and the mechanism block say different things about the same
assumption. The line says a functional form is being assumed; the block says
WHICH one, fitted by what method, and who settled it. Ten families declared the
assumption and attached no block, so their readers got the warning without the
thing to audit — and got it silently, because a family nobody wired looked
exactly like a family with no shape to disclose.

Wiring the ten would have left the mechanism intact: an eleventh family added
tomorrow would be silent again, and the way it announces itself is that nothing
happens. So the funnel every numeric answer already passes through now asks the
question, and a shape declared without a block ends the run naming the method
that declared it. The whole test suite is the census after that — which is how
the one family still missing (transport) was found, rather than by reading
twenty-four call sites and hoping.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.output.result_orchestrator import augment_assumption_ledger


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _frontdoor_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


@pytest.fixture(scope="module")
def frontdoor_frame() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    n = 4_000
    u = rng.random(n) < 0.5
    x = rng.random(n) < np.where(u, 0.7, 0.3)
    m = rng.random(n) < np.where(x, 0.8, 0.2)
    y = rng.random(n) < np.clip(0.2 + 0.3 * m + 0.3 * u, 0.0, 1.0)
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _blocks(result: dict) -> dict:
    return result.get("extensions") or {}


# ====================================================== a family that was silent


def test_front_door_now_says_which_shape_it_fitted(frontdoor_frame):
    """It declared ``logit_outcome_regression`` and disclosed nothing.

    Front-door was one of the ten: the ledger carried the row, so a reader
    knew a form was assumed, and no surface said it was the logit link on the
    outcome model, chosen by the system because nothing was specified.
    """
    result = themis.estimate(
        _frontdoor_program(), frontdoor_frame, ci_bootstrap=0)["results"][0]
    audit = _blocks(result).get("mechanism_audit")
    assert audit is not None
    mechanism = audit["mechanisms"][0]
    assert mechanism["method"] == "frontdoor_logistic"
    assert mechanism["form"] == "logistic"
    assert mechanism["assumptions"] == [
        {"id": "logit_outcome_regression", "settled_by": "default"},
    ]


def test_the_block_and_the_ledger_name_the_same_assumption(frontdoor_frame):
    """Two surfaces, one id — which is what makes them checkable against
    each other rather than two accounts of the same run."""
    result = themis.estimate(
        _frontdoor_program(), frontdoor_frame, ci_bootstrap=0)["results"][0]
    named = {str(a["id"]) for a in
             _blocks(result)["mechanism_audit"]["mechanisms"][0]["assumptions"]}
    on_ledger = {
        str(e["id"])
        for e in _blocks(result)["assumption_ledger"]["assumptions"]
        if e.get("id")
    }
    assert named
    assert named <= on_ledger


def test_the_caller_naming_the_form_changes_who_settled_it(frontdoor_frame):
    told = themis.estimate(
        _frontdoor_program(), frontdoor_frame, ci_bootstrap=0,
        model="logistic")["results"][0]
    mechanism = _blocks(told)["mechanism_audit"]["mechanisms"][0]
    assert mechanism["assumptions"] == [
        {"id": "logit_outcome_regression", "settled_by": "caller_asserted"},
    ]


# ====================================================== the refusal


def _result_that_assumed_a_shape_and_said_nothing() -> dict:
    """The artefact the ten families produced, rebuilt.

    A numeric estimate whose flat list carries a functional-form id, and no
    mechanism block beside it. Reconstructed rather than described, because a
    gate that has never seen the thing it refuses is a gate nobody has tried.
    """
    return {
        "query_id": "q",
        "numeric_estimate": {
            "point": 0.2,
            "method": "frontdoor_logistic",
            "assumptions": [
                "front_door_criterion_holds_on_graph",
                "logit_outcome_regression",
            ],
        },
    }


def test_a_shape_declared_with_no_block_ends_the_run():
    result = _result_that_assumed_a_shape_and_said_nothing()
    with pytest.raises(ValueError) as raised:
        augment_assumption_ledger(result)
    said = str(raised.value)
    assert "frontdoor_logistic" in said
    assert "logit_outcome_regression" in said


def test_the_same_result_with_its_block_passes():
    """The gate must let the wired shape through, or it is measuring the
    presence of a key rather than the presence of a disclosure."""
    result = _result_that_assumed_a_shape_and_said_nothing()
    result["extensions"] = {"mechanism_audit": {
        "mechanisms": [{
            "target": "y", "form": "logistic", "method": "frontdoor_logistic",
            "assumptions": [{"id": "logit_outcome_regression",
                             "settled_by": "default"}],
        }],
        "summary": "…",
    }}
    augment_assumption_ledger(result)
    assert result["extensions"]["assumption_ledger"]["assumptions"]


def test_a_family_that_assumes_no_shape_is_not_asked_to_disclose_one():
    """``None`` from the block builder is a real answer, and the gate must
    not turn it into a missing one. A saturated plug-in assumes no form."""
    result = {
        "query_id": "q",
        "numeric_estimate": {
            "point": 0.2,
            "method": "general_id_plug_in",
            "assumptions": [
                "consistency_of_potential_outcomes",
                "positivity_overlap_of_treatment_arms",
            ],
        },
    }
    augment_assumption_ledger(result)
    assert "mechanism_audit" not in (result.get("extensions") or {})
    assert result["extensions"]["assumption_ledger"]["assumptions"]
