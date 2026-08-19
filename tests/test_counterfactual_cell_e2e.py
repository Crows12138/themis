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


# ================== the instrument route on the parameter end (#359)
#
# Where a bow arc leaves no interventional risk to be had, the identity
# route has nothing to consume and the cell used to reach the reader as a
# gap report. The instrument answers a different program on the same theta,
# and reaching it needed the recovery to stop dropping Z out of Y's
# conditioning set: exclusion is exactly what keeps Z from being Y's parent,
# so a parent-keyed recovery cannot ask for the one factor the polytope
# needs.

_IV_P_Z1 = 0.5
_IV_P_X1_GIVEN_Z = {True: 0.7, False: 0.2}
_IV_P_Y1_GIVEN_XZ = {(True, True): 0.8, (True, False): 0.6,
                     (False, True): 0.3, (False, False): 0.1}


def _iv_theta(*, p_x1_given_z=None, p_y1_given_xz=None) -> list:
    """``P(Z)``, ``P(X|Z)``, ``P(Y|X,Z)`` — the chain rule in topological order.

    Not ``P(X)`` and ``P(Y|X)``: under a bow arc the graph stops licensing the
    drop of Z out of Y's conditioning set, and these are the factors that
    survive when it does.
    """
    px = _IV_P_X1_GIVEN_Z if p_x1_given_z is None else p_x1_given_z
    py = _IV_P_Y1_GIVEN_XZ if p_y1_given_xz is None else p_y1_given_xz
    out = [_p("z", True, [], _IV_P_Z1), _p("z", False, [], 1 - _IV_P_Z1)]
    for z_val, p_x1 in px.items():
        out += [_p("x", True, [("z", z_val)], p_x1),
                _p("x", False, [("z", z_val)], 1 - p_x1)]
    for (x_val, z_val), p_y1 in py.items():
        out += [_p("y", True, [("x", x_val), ("z", z_val)], p_y1),
                _p("y", False, [("x", x_val), ("z", z_val)], 1 - p_y1)]
    return out


def _iv_program(query, *, theta=None, z_to_y=False, bow=True) -> dict:
    statements = [
        {"kind": "variable", "predicate": pred, "domain": [True, False]}
        for pred in ("x", "y", "z")
    ] + [
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
    ]
    if z_to_y:
        statements.append(
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")})
    if bow:
        statements.append(
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")})
    statements += _iv_theta() if theta is None else theta
    statements.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


_PN_CELL = _cf_query(x_obs=True, x_cf=False, y_star=False, factual_y=True)


def _licence(result: dict) -> str | None:
    step = result["derivation"]["steps"][-1]
    return step["inputs"].get("interventional_risk_provenance")


def _plain(value):
    """A derivation envelope's tagged tuples, read back as plain Python.

    The audit trail encodes an ordered sequence as
    ``{"kind": "value_tuple", "items": [...]}``; the verifier reads it through
    its own decoder, and a test going at the raw JSON has to do the same.
    """
    if isinstance(value, dict) and value.get("kind") == "value_tuple":
        return [_plain(item) for item in value["items"]]
    return value


def test_the_instrument_bounds_the_cell_where_no_risk_is_identifiable():
    r = _run(_iv_program(_PN_CELL))

    assert r["status"] == "counterfactual_bounded"
    assert _licence(r) == "instrument_response_polytope"
    assert r["numeric_result"]["interval"]["low"] == pytest.approx(0.5441176470588235)
    assert r["numeric_result"]["interval"]["high"] == pytest.approx(1.0)


def test_the_parameter_end_solves_the_program_the_data_end_solves():
    """The cross-END invariant, the way the cross-DOOR one reads above: the
    same eight numbers, whether they arrived as CPTs or as a DataFrame, are
    the same polytope and must give the same two endpoints."""
    import numpy as np

    from themis.response_polytope import counterfactual_cell_response_bounds

    r = _run(_iv_program(_PN_CELL))
    inputs = r["derivation"]["steps"][-1]["inputs"]
    low, high = counterfactual_cell_response_bounds(
        np.array(_plain(inputs["p_xyz"]), dtype=float),
        np.array(_plain(inputs["p_z"]), dtype=float),
        x_observed=1, x_counterfactual=0, y_star=0, factual_y=1,
    )
    assert r["numeric_result"]["interval"]["low"] == pytest.approx(low)
    assert r["numeric_result"]["interval"]["high"] == pytest.approx(high)


def test_the_recorded_table_marginalises_to_the_observational_joint():
    """P(X, Y) and P(X, Y | Z) are two readings of one recovered joint, so a
    theta that reaches the second reaches the first by summing it."""
    r = _run(_iv_program(_PN_CELL))
    inputs = r["derivation"]["steps"][-1]["inputs"]
    p_z, p_xyz = _plain(inputs["p_z"]), _plain(inputs["p_xyz"])

    p_x1_y1 = sum(p_z[z] * p_xyz[z][1][1] for z in range(len(p_z)))
    expected = sum(
        (_IV_P_Z1 if z_val else 1 - _IV_P_Z1)
        * _IV_P_X1_GIVEN_Z[z_val]
        * _IV_P_Y1_GIVEN_XZ[(True, z_val)]
        for z_val in (True, False)
    )
    assert p_x1_y1 == pytest.approx(expected)


def test_a_theta_without_the_z_conditional_factors_gets_the_gap():
    """The root cause, from the other side: with only P(X) and P(Y|X) the
    instrument has no table to be fitted to, and the cell is a gap again.
    What the instrument route needed was never the solver's location — it
    was a conditioning set the recovery would not ask for."""
    marginal_theta = [
        _p("x", True, [], 0.45), _p("x", False, [], 0.55),
        _p("y", True, [("x", True)], 0.7), _p("y", False, [("x", True)], 0.3),
        _p("y", True, [("x", False)], 0.2), _p("y", False, [("x", False)], 0.8),
    ]
    r = _run(_iv_program(_PN_CELL, theta=marginal_theta))

    assert r["status"] == "needs_investigation"
    names = {item["name"] for item in r["missing_information"]}
    assert "counterfactual:interventional_risk_unavailable" in names


def test_a_back_door_is_taken_before_the_instrument():
    """Same theta, same instrument, one edge more: with Z→Y the risk is
    identifiable, and the route that rests on assumptions the caller already
    granted is the one that answers. The data end orders the two the same
    way."""
    r = _run(_iv_program(_PN_CELL, z_to_y=True, bow=False))

    assert r["status"].startswith("counterfactual_")
    assert _licence(r) == "derived_identification"


def test_an_instrument_that_rules_nothing_out_leaves_the_gap_standing():
    """An interval of [0, 1] excludes nothing, and returning it would replace
    a gap naming a remedy with something shaped like an answer."""
    flat = _iv_program(_PN_CELL, theta=_iv_theta(
        p_x1_given_z={True: 0.4, False: 0.4},
        p_y1_given_xz={(True, True): 0.8, (True, False): 0.8,
                       (False, True): 0.3, (False, False): 0.3},
    ))
    r = _run(flat)

    assert r["status"] == "needs_investigation"
    reason = " ".join(item["reason"] for item in r["missing_information"])
    assert "rules nothing out" in reason
    assert "z" in reason


def test_a_theta_the_instrument_model_refutes_says_so():
    """Pearl's instrumental inequality is violated at X=1, so no distribution
    over response types reproduces this table. The finding is about the
    instrument the door FOUND, not about anything the caller wrote, so it
    reaches the reader beside the gap rather than as a refusal of the query."""
    refuting = _iv_program(_PN_CELL, theta=_iv_theta(
        p_x1_given_z={True: 0.9, False: 0.9},
        p_y1_given_xz={(True, True): 1.0, (True, False): 0.0,
                       (False, True): 0.0, (False, False): 0.0},
    ))
    r = _run(refuting)

    assert r["status"] == "needs_investigation"
    reason = " ".join(item["reason"] for item in r["missing_information"])
    assert "instrumental inequality" in reason.lower()


def test_the_declared_monotonicity_narrows_the_instrument_cell():
    """It restricts the type space rather than pinning the cell — measured,
    not assumed: both endpoints move and neither meets the other."""
    free = _run(_iv_program(_PN_CELL))
    narrowed = _run(_iv_program(_cf_query(
        x_obs=True, x_cf=False, y_star=False, factual_y=True,
        assumptions={"monotonicity": "non_decreasing"},
    )))

    assert narrowed["status"] == "counterfactual_bounded"
    assert _licence(narrowed) == "instrument_response_polytope"
    f, n = free["numeric_result"]["interval"], narrowed["numeric_result"]["interval"]
    assert n["low"] > f["low"] and n["high"] < f["high"]


def test_the_derivation_chain_names_which_route_ran():
    """The rule is one name over two solvers, so the sentence keyed by it
    cannot say which ran; the licence beside it can."""
    from themis.output.analysis_report import build_analysis_report

    program = _iv_program(_PN_CELL)
    text = build_analysis_report(_run(program), program=program)
    assert "响应函数多面体" in text


def test_both_doors_read_the_same_instrument_off_the_same_edges():
    """The structural half of "is Z an instrument here" is one function. Two
    copies of it would let the effect query and the cell disagree about a
    graph, which is the shape that put the two ends out of step to begin
    with."""
    from themis.runtime.scheduler import _instrument_candidates

    edges = [("z", "x"), ("x", "y")]
    assert _instrument_candidates(edges, treatment="x", outcome="y") == {"z"}
    assert _instrument_candidates(
        edges + [("z", "y")], treatment="x", outcome="y") == set()


# ------------------------------------------------ the audit, on this route

def test_the_instrument_route_survives_independent_verification():
    program = _iv_program(_PN_CELL)
    themis.verify(program, _run(program))


# ------------------------------- the cross-door invariant, on this route

_CAUSATION = {"kind": "causation", "cause": _atom("x"), "effect": _atom("y")}


def test_pn_agrees_between_the_doors_over_the_instrument():
    """The whole point of the pair. PN is one of the cell door's cells, so a
    door that answered while the other refused — one theta, one graph, one
    question — would be the asymmetry this pair exists to not have."""
    via_cell = _run(_iv_program(_PN_CELL))
    via_causation = _run(_iv_program(_CAUSATION))

    assert via_causation["status"] == "counterfactual_bounded"
    assert _licence(via_causation) == "instrument_response_polytope"
    pn = via_causation["extensions"]["causation"]["pn"]
    interval = via_cell["numeric_result"]["interval"]
    assert interval["low"] == pn["lower"]
    assert interval["high"] == pn["upper"]


def test_the_causation_route_reports_no_interventional_risk():
    """Three quantities read off one polytope consume no arm at all, and the
    envelope says so rather than leaving the reader to infer it."""
    envelope = _run(_iv_program(_CAUSATION))["extensions"]["causation"]

    assert envelope["p_y_do_x1"] is None and envelope["p_y_do_x0"] is None
    assert envelope["instrument"] == "z"
    for qty in ("pn", "ps", "pns"):
        assert envelope[qty]["point"] is None


def test_the_causation_instrument_route_survives_verification():
    program = _iv_program(_CAUSATION)
    themis.verify(program, _run(program))


def test_the_causation_door_answers_while_only_some_quantities_are_vacuous():
    """The decline is "every quantity is [0, 1]", not "any of them is".

    An instrument that does not move the treatment tells you nothing about PN
    or PS, but PNS is constrained by the joint whatever the instrument does —
    so an answer was reached and withholding all three would throw away the
    one that was. Same theta reaches the CELL door as a gap, because there the
    only quantity asked for is the one that stayed at [0, 1]."""
    theta = _iv_theta(
        p_x1_given_z={True: 0.4, False: 0.4},
        p_y1_given_xz={(True, True): 0.8, (True, False): 0.8,
                       (False, True): 0.3, (False, False): 0.3},
    )
    causation = _run(_iv_program(_CAUSATION, theta=theta))
    cell = _run(_iv_program(_PN_CELL, theta=theta))

    envelope = causation["extensions"]["causation"]
    assert causation["status"] == "counterfactual_bounded"
    assert (envelope["pn"]["lower"], envelope["pn"]["upper"]) == (0.0, 1.0)
    assert envelope["pns"]["upper"] < 1.0
    assert cell["status"] == "needs_investigation"


@pytest.mark.parametrize("tamper", [
    lambda r: r["extensions"]["causation"]["pn"].__setitem__("lower", 0.1),
    # A point where the audited envelope has none. Unreachable while the two
    # routes disagreed about how "no point" was spelled: the cross-check could
    # only ask whether the key was there, and forging one put it there on both
    # sides of a comparison that never looked at the value.
    lambda r: r["extensions"]["causation"]["pn"].__setitem__("point", 0.99),
    lambda r: _inputs(r)["p_xyz"]["items"][0]["items"][1]["items"].__setitem__(
        1, 0.05),
    lambda r: _inputs(r)["instrument_levels"]["items"].reverse(),
    lambda r: _inputs(r).__setitem__("p_y_do_x1", 0.4),
    lambda r: _inputs(r).__setitem__(
        "interventional_risk_provenance", "derived_identification"),
], ids=["pn-bound", "forged-point", "table-cell", "permuted-strata",
        "forged-risk", "relabelled-as-derived"])
def test_the_verifier_rejects_a_tampered_causation_instrument_answer(tamper):
    import copy

    from themis.verifier import VerificationError

    program = _iv_program(_CAUSATION)
    result = copy.deepcopy(_run(program))
    assert _licence(result) == "instrument_response_polytope"
    tamper(result)

    with pytest.raises(VerificationError):
        themis.verify(program, result)


def _inputs(result: dict) -> dict:
    return result["derivation"]["steps"][-1]["inputs"]


@pytest.mark.parametrize("tamper", [
    lambda r: r["numeric_result"]["interval"].__setitem__("low", 0.1),
    lambda r: _inputs(r)["p_xyz"]["items"][0]["items"][1]["items"].__setitem__(
        1, 0.05),
    lambda r: _inputs(r)["instrument_levels"]["items"].reverse(),
    lambda r: _inputs(r).__setitem__("p_y_do_x_cf", 0.4),
    lambda r: _inputs(r).__setitem__(
        "interventional_risk_provenance", "backdoor_adjustment"),
    lambda r: _inputs(r).__setitem__("instrument", "y"),
    lambda r: _inputs(r).__setitem__("instrument", "not_a_node"),
], ids=["interval", "table-cell", "permuted-strata", "forged-risk",
        "relabelled-as-backdoor", "outcome-named-as-instrument",
        "instrument-not-on-the-graph"])
def test_the_verifier_rejects_a_tampered_instrument_answer(tamper):
    import copy

    from themis.verifier import VerificationError

    program = _iv_program(_PN_CELL)
    result = copy.deepcopy(_run(program))
    assert _licence(result) == "instrument_response_polytope"
    tamper(result)

    with pytest.raises(VerificationError):
        themis.verify(program, result)
