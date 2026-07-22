"""End-to-end behaviour of the binary counterfactual-cell query.

The through-line: asking "would Y have happened had X been different?"
through the ``counterfactual`` door must give the same answer as asking
for the corresponding probability of causation through the ``causation``
door. They are the same quantity, so two doors onto it that disagree is a
defect regardless of which one is wrong.
"""
from __future__ import annotations

import pytest

import themis


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _p(pred: str, value: bool, given, v: float) -> dict:
    return {
        "kind": "probability",
        "target": {"atom": _atom(pred), "value": value},
        "given": [{"atom": _atom(g), "value": gv} for g, gv in given],
        "value": v,
    }


# P(x=1) = 0.4, P(y=1|x=0) = 0.3, P(y=1|x=1) = 0.8, so the joint is
# P(0,0)=.42 P(0,1)=.18 P(1,0)=.08 P(1,1)=.32 and P(Y=1) = 0.5.
_THETA = [
    _p("x", False, [], 0.6),
    _p("x", True, [], 0.4),
    _p("y", True, [("x", False)], 0.3),
    _p("y", False, [("x", False)], 0.7),
    _p("y", True, [("x", True)], 0.8),
    _p("y", False, [("x", True)], 0.2),
]


def _program(query: dict, *, confounded: bool = False, theta=True) -> dict:
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
    ]
    if confounded:
        statements.append(
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")}
        )
    if theta:
        statements.extend(_THETA)
    statements.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


def _cf_query(*, x_obs, x_cf, y_star, factual_y=None, **extra) -> dict:
    q = {
        "kind": "counterfactual",
        "observed": {"atom": _atom("x"), "value": x_obs},
        "counterfactual_intervention": {"atom": _atom("x"), "value": x_cf},
        "counterfactual_target": {"atom": _atom("y"), "value": y_star},
    }
    if factual_y is not None:
        q["factual_target_known"] = factual_y
    q.update(extra)
    return q


def _run(program) -> dict:
    return themis.run(program)["results"][0]


# ============================================== the cross-door invariant

def test_pn_agrees_between_the_counterfactual_and_causation_doors():
    """PN = P(Y_{x=0}=0 | X=1, Y=1) asked both ways."""
    via_cf = _run(_program(_cf_query(
        x_obs=True, x_cf=False, y_star=False, factual_y=True,
    )))
    via_causation = _run(_program({
        "kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
    }))

    assert via_cf["status"] == "counterfactual_bounded"
    pn = via_causation["extensions"]["causation"]["pn"]
    assert via_cf["numeric_result"]["interval"]["low"] == pytest.approx(pn["lower"])
    assert via_cf["numeric_result"]["interval"]["high"] == pytest.approx(pn["upper"])


def test_ps_agrees_between_the_counterfactual_and_causation_doors():
    """PS = P(Y_{x=1}=1 | X=0, Y=0) asked both ways."""
    via_cf = _run(_program(_cf_query(
        x_obs=False, x_cf=True, y_star=True, factual_y=False,
    )))
    via_causation = _run(_program({
        "kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
    }))

    ps = via_causation["extensions"]["causation"]["ps"]
    assert via_cf["numeric_result"]["interval"]["low"] == pytest.approx(ps["lower"])
    assert via_cf["numeric_result"]["interval"]["high"] == pytest.approx(ps["upper"])


def test_monotone_pn_agrees_with_the_causation_point():
    """Under monotonicity both doors must collapse to the same point."""
    via_cf = _run(_program(_cf_query(
        x_obs=True, x_cf=False, y_star=False, factual_y=True,
        assumptions={"monotonicity": "non_decreasing"},
    )))
    via_causation = _run(_program({
        "kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
        "monotonic": True,
    }))

    assert via_cf["status"] == "counterfactual_solved"
    pn_point = via_causation["extensions"]["causation"]["pn"]["point"]
    assert via_cf["numeric_result"]["value"] == pytest.approx(pn_point)


# ================================================= the answer it now gives

def test_pn_is_informative_where_the_old_path_returned_zero_to_one():
    """(P(Y=1) - P(y|do(x=0))) / P(x=1,y=1) = (0.5 - 0.3) / 0.32."""
    r = _run(_program(_cf_query(
        x_obs=True, x_cf=False, y_star=False, factual_y=True,
    )))

    assert r["numeric_result"]["interval"]["low"] == pytest.approx(0.625)
    assert r["numeric_result"]["interval"]["high"] == pytest.approx(0.875)


def test_ett_is_a_point_not_an_interval():
    """With no factual outcome the cell is point-identified outright."""
    r = _run(_program(_cf_query(x_obs=False, x_cf=True, y_star=True)))

    assert r["status"] == "counterfactual_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.8)


def test_a_pinned_cell_is_answered_without_identifying_the_effect():
    """Monotonicity plus consistency determine this cell, so an
    unidentifiable effect does not block it."""
    r = _run(_program(
        _cf_query(
            x_obs=False, x_cf=True, y_star=True, factual_y=True,
            assumptions={"monotonicity": "non_decreasing"},
        ),
        confounded=True,
    ))

    assert r["status"] == "counterfactual_solved"
    assert r["numeric_result"]["value"] == 1.0


# ============================================== honest refusals and escapes

def test_confounded_cell_reports_the_gap_instead_of_a_vacuous_interval():
    r = _run(_program(
        _cf_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        confounded=True,
    ))

    assert r["status"] == "needs_investigation"
    assert "numeric_result" not in r
    names = {item["name"] for item in r["missing_information"]}
    assert "counterfactual:interventional_risk_unavailable" in names


def test_experimental_risk_rescues_the_confounded_cell():
    """The Tian-Pearl drug-example escape hatch, through this door."""
    r = _run(_program(
        _cf_query(
            x_obs=True, x_cf=False, y_star=False, factual_y=True,
            experimental_risk_control=0.3,
        ),
        confounded=True,
    ))

    assert r["status"] == "counterfactual_bounded"
    assert r["numeric_result"]["interval"]["low"] == pytest.approx(0.625)
    assert r["numeric_result"]["interval"]["high"] == pytest.approx(0.875)


def test_only_the_arm_the_cell_depends_on_is_required():
    """do(X=0) is what this cell needs; supplying it alone is enough even
    though the do(X=1) arm is equally unidentifiable."""
    r = _run(_program(
        _cf_query(
            x_obs=True, x_cf=False, y_star=False, factual_y=True,
            experimental_risk_control=0.3,
        ),
        confounded=True,
    ))

    assert r["status"] == "counterfactual_bounded"


def test_an_experimental_risk_the_joint_forbids_is_reported_not_used():
    """Consistency confines P(y|do(x=0)) to [P(x=0,y=1), +P(x=1)] = [.18, .58]."""
    r = _run(_program(
        _cf_query(
            x_obs=True, x_cf=False, y_star=False, factual_y=True,
            experimental_risk_control=0.9,
        ),
        confounded=True,
    ))

    assert r["status"] == "needs_investigation"
    names = {item["name"] for item in r["missing_information"]}
    assert "counterfactual:inputs_infeasible" in names


def test_monotonicity_refuted_by_the_data_is_reported_not_clamped():
    """Non-decreasing pins P(Y_0=1|X=1,Y=0) = 0, so the identity leaves
    P(Y_0=1|X=1,Y=1) = (P(y|do(x=0)) - 0.18) / 0.32, which exceeds 1 once
    P(y|do(x=0)) > 0.5. Consistency alone would have allowed 0.55."""
    r = _run(_program(
        _cf_query(
            x_obs=True, x_cf=False, y_star=False, factual_y=True,
            assumptions={"monotonicity": "non_decreasing"},
            experimental_risk_control=0.55,
        ),
        confounded=True,
    ))

    assert r["status"] == "needs_investigation"
    reasons = " ".join(item["reason"] for item in r["missing_information"])
    assert "refuted" in reasons


# ================================================================= audit

@pytest.mark.parametrize("query", [
    _cf_query(x_obs=False, x_cf=True, y_star=True),
    _cf_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
    _cf_query(
        x_obs=False, x_cf=True, y_star=True, factual_y=True,
        assumptions={"monotonicity": "non_decreasing"},
    ),
    _cf_query(x_obs=False, x_cf=False, y_star=True),
], ids=["ett", "pn", "pinned", "same-world"])
def test_every_answered_shape_survives_independent_verification(query):
    program = _program(query)
    result = _run(program)

    assert result["status"].startswith("counterfactual_")
    themis.verify(program, result)


def test_tampering_the_declared_interventional_risk_is_rejected():
    import copy

    from themis.verifier import VerificationError

    program = _program(_cf_query(x_obs=False, x_cf=True, y_star=True))
    result = copy.deepcopy(_run(program))
    step = result["derivation"]["steps"][-1]
    assert step["rule"] == "counterfactual_cell_bounds"
    step["inputs"]["p_y_do_x_cf"] = 0.5

    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_claiming_the_risk_was_not_required_is_rejected():
    import copy

    from themis.verifier import VerificationError

    program = _program(_cf_query(x_obs=False, x_cf=True, y_star=True))
    result = copy.deepcopy(_run(program))
    step = result["derivation"]["steps"][-1]
    step["inputs"].pop("p_y_do_x_cf")
    step["inputs"]["interventional_risk_provenance"] = "not_required"

    with pytest.raises(VerificationError):
        themis.verify(program, result)
