"""A conditional instrument must name the same estimand from either end.

Themis answers an effect query two ways: from declared probabilities
(``themis.run``, the theta end) and from a DataFrame (``themis.estimate``,
the data end). They share no code — ``themis/runtime`` does not import
``themis/estimation`` — so nothing but a test can hold them to the same
quantity.

They used to disagree. The theta end grew a stratified Wald, which
aggregates the strata as a ratio of averages and reports the LATE on
compliers. The data end resolved a non-empty conditioning set to 2SLS,
which enters W additively and therefore weights each stratum's effect by
the instrument's residual variance there. Those coincide exactly when
the first stage is equally strong in every stratum, and differ by ~10%
in either direction when it is not — with both answers internally
consistent and nothing to mark the substitution.

The DGP below makes the first stage unequal on purpose. Without that,
every estimator in this file would look correct.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _gr(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target_pred, target_v, given_pairs, value):
    return {
        "kind": "probability",
        "target": _gr(target_pred, target_v),
        "given": [_gr(p, v) for p, v in given_pairs],
        "value": value,
    }


# w → z, w → y, z → x, x → y, x ↔ y.
# z is an instrument only once w is held fixed: z ← w → y is open in the
# mutilated graph otherwise.
_P_W1 = 0.4
_STRATA = {
    True:  (0.9, 0.3, 0.7, 0.4),   # first stage 0.6, LATE(w=1) = 0.50
    False: (0.6, 0.2, 0.5, 0.2),   # first stage 0.4, LATE(w=0) = 0.75
}
_RATIO_OF_AVERAGES = 0.625
_AVERAGE_OF_RATIOS = 0.65
# P(z|w=1) != P(z|w=0) is what separates the stratified Wald from 2SLS.
_P_Z_GIVEN_W = {True: 0.5, False: 0.1}


def _structure() -> list[dict]:
    return [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("x", "y", "z", "w")
    ] + [
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    ]


def _query_stmt() -> dict:
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
        "assumptions": {"monotonicity": "non_decreasing"},
    }}


def _data_program() -> dict:
    """Structure only — the numbers arrive as a DataFrame."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _structure() + [_query_stmt()],
    }


def _theta_program() -> dict:
    """The same structure with the conditionals declared outright."""
    stmts = _structure() + [
        _prob("w", True, [], _P_W1),
        _prob("w", False, [], 1 - _P_W1),
    ]
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        stmts += [
            _prob("x", True, [("z", True), ("w", wv)], pxz1),
            _prob("x", True, [("z", False), ("w", wv)], pxz0),
            _prob("y", True, [("z", True), ("w", wv)], pyz1),
            _prob("y", True, [("z", False), ("w", wv)], pyz0),
        ]
    stmts.append(_query_stmt())
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def _sample(n=400_000, seed=11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    w = rng.random(n) < _P_W1
    z = rng.random(n) < np.where(w, _P_Z_GIVEN_W[True], _P_Z_GIVEN_W[False])
    p_x, p_y = np.empty(n), np.empty(n)
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        m = (w == wv)
        p_x[m] = np.where(z[m], pxz1, pxz0)
        p_y[m] = np.where(z[m], pyz1, pyz0)
    return pd.DataFrame({
        "w": w, "z": z,
        "x": rng.random(n) < p_x, "y": rng.random(n) < p_y,
    })


def _theta_point() -> float:
    r = themis.run(_theta_program())["results"][0]
    assert r["status"] == "numerically_solved", r.get("missing_information")
    return r["numeric_result"]["value"]


def _data_result(df=None, **options):
    df = _sample() if df is None else df
    ast = _data_program()
    out = themis.estimate(ast, df, ci_bootstrap=options.pop("ci_bootstrap", 0),
                          **options)
    return ast, out["results"][0]


# ------------------------------------------------------- the premise

def test_the_two_estimands_actually_differ_on_this_design():
    """Guard the guard. If 2SLS happened to agree with the stratified
    Wald here, every parity assertion below would pass for the wrong
    reason."""
    from themis.estimation.iv import estimate_iv_ate

    df = _sample()
    linear = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), model="2sls", ci_bootstrap=0,
    )
    assert abs(linear.point - _RATIO_OF_AVERAGES) > 0.04, (
        f"2SLS gives {linear.point}, which is not far enough from the LATE "
        f"{_RATIO_OF_AVERAGES} for this design to separate the estimands"
    )


# ------------------------------------------------------- parity

def test_theta_end_and_data_end_agree_on_the_conditional_instrument():
    theta = _theta_point()
    _, result = _data_result()
    data = result["numeric_estimate"]["point"]

    assert abs(theta - _RATIO_OF_AVERAGES) < 1e-9
    assert abs(data - theta) < 0.01, (
        f"the theta end reports {theta} and the data end {data} for the "
        f"same query on the same graph — one of them is answering a "
        f"different question"
    )


def test_data_end_names_the_stratified_wald():
    _, result = _data_result()
    assert result["numeric_estimate"]["method"] == "iv_stratified_wald"


def test_both_ends_publish_the_same_stratum_table_shape():
    """Parity of the payload, not only of the headline: a reader moving
    between the two surfaces should not have to learn two vocabularies."""
    theta_ext = themis.run(_theta_program())["results"][0]["extensions"]
    theta_numeric = theta_ext["iv_identification"]["numeric"]
    _, result = _data_result()
    data_block = result["numeric_estimate"]["stratified_wald"]

    for key in ("strata", "outcome_shift", "treatment_shift"):
        assert key in theta_numeric, key
        assert key in data_block, key
    assert len(theta_numeric["strata"]) == len(data_block["strata"]) == 2
    for row in data_block["strata"]:
        assert set(row) >= {"values", "weight", "outcome_shift",
                            "treatment_shift"}
    assert abs(
        theta_numeric["treatment_shift"] - data_block["treatment_shift"]
    ) < 0.01


def test_data_end_reports_the_complier_share():
    _, result = _data_result()
    block = result["numeric_estimate"]["stratified_wald"]
    assert abs(block["treatment_shift"] - 0.48) < 0.01
    recomputed = sum(
        s["weight"] * s["treatment_shift"] for s in block["strata"]
    )
    assert abs(recomputed - block["treatment_shift"]) < 1e-9


def test_data_end_is_not_the_average_of_the_per_stratum_ratios():
    _, result = _data_result()
    block = result["numeric_estimate"]["stratified_wald"]
    average_of_ratios = sum(
        s["weight"] * s["outcome_shift"] / s["treatment_shift"]
        for s in block["strata"]
    )
    assert abs(average_of_ratios - _AVERAGE_OF_RATIOS) < 0.02, (
        "premise broken: the per-stratum table no longer implies a "
        "distinguishable average-of-ratios"
    )
    assert abs(result["numeric_estimate"]["point"] - average_of_ratios) > 0.015


# ------------------------------------------------------- verifier

def test_verify_accepts_the_stratified_estimate():
    ast, result = _data_result()
    assert themis.verify(ast, result) is None


def _tampered(mutate):
    ast, result = _data_result()
    step = next(
        s for s in result["derivation"]["steps"]
        if s["rule"] == "numeric_iv_estimate"
    )
    mutate(result, step["inputs"])
    return ast, result


def test_verifier_rejects_the_average_of_ratios_planted_as_the_point():
    """The one wrong answer that looks right. Every recorded stratum is
    untouched and internally consistent; only the aggregation rule is
    swapped."""
    def mutate(result, inputs):
        weights = inputs["stratum_weights"]["items"]
        d_y = inputs["stratum_outcome_shifts"]["items"]
        d_x = inputs["stratum_treatment_shifts"]["items"]
        planted = sum(w * a / b for w, a, b in zip(weights, d_y, d_x))
        inputs["point"] = planted
        result["numeric_estimate"]["point"] = planted

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="average of the per-stratum ratios"):
        themis.verify(ast, result)


def test_verifier_rejects_a_dropped_stratum():
    """Dropping a stratum leaves the arithmetic self-consistent over a
    NARROWER population than the query asked about."""
    def mutate(result, inputs):
        for key in ("stratum_weights", "stratum_outcome_shifts",
                    "stratum_treatment_shifts"):
            inputs[key]["items"] = inputs[key]["items"][:1]
        weights = inputs["stratum_weights"]["items"]
        d_y = inputs["stratum_outcome_shifts"]["items"]
        d_x = inputs["stratum_treatment_shifts"]["items"]
        inputs["aggregate_outcome_shift"] = sum(
            w * v for w, v in zip(weights, d_y))
        inputs["aggregate_treatment_shift"] = sum(
            w * v for w, v in zip(weights, d_x))
        point = (inputs["aggregate_outcome_shift"]
                 / inputs["aggregate_treatment_shift"])
        inputs["point"] = point
        result["numeric_estimate"]["point"] = point

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="sum to"):
        themis.verify(ast, result)


def test_verifier_rejects_a_reweighted_stratum():
    def mutate(result, inputs):
        items = list(inputs["stratum_weights"]["items"])
        items[0] += 0.05
        inputs["stratum_weights"]["items"] = items

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="sum to"):
        themis.verify(ast, result)


def test_verifier_rejects_a_stratum_table_on_a_non_stratified_method():
    """A table attached to a 2SLS point would let the aggregation check
    pass while the reported number came from somewhere else entirely."""
    def mutate(result, inputs):
        inputs["method"] = "iv_2sls"
        result["numeric_estimate"]["method"] = "iv_2sls"

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="only the stratified Wald"):
        themis.verify(ast, result)


def test_verifier_rejects_a_stratified_method_without_its_table():
    def mutate(result, inputs):
        for key in ("stratum_weights", "stratum_outcome_shifts",
                    "stratum_treatment_shifts"):
            del inputs[key]

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="must record the stratum table"):
        themis.verify(ast, result)


def test_verifier_rejects_a_tampered_aggregate_first_stage():
    """The complier share is reported to the user, so it is a claim in
    its own right and not merely an intermediate."""
    def mutate(result, inputs):
        inputs["aggregate_treatment_shift"] += 0.1

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="aggregate_treatment_shift"):
        themis.verify(ast, result)


# ------------------------------------------------------- fallback

def _thin_sample() -> pd.DataFrame:
    df = _sample(n=8000, seed=3)
    df.loc[df["w"] & df["z"], "z"] = False       # empty w=1's high arm
    return df


def test_fallback_to_linear_is_disclosed_as_a_gap():
    ast, result = _data_result(_thin_sample())
    assert result["numeric_estimate"]["method"] == "iv_2sls"
    kinds = [
        g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", [])
    ]
    assert "iv_estimand_fallback_to_linear" in kinds


def test_fallback_gap_says_the_question_changed_not_that_precision_dropped():
    _, result = _data_result(_thin_sample())
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "iv_estimand_fallback_to_linear"
    )
    assert gap["severity"] == "informational"
    assert "compliers" in gap["description"]
    # It names the stratum that forced the fallback, so the reader can act.
    assert "w=True" in gap["description"]
    # And the data that would restore the LATE is a concrete ask.
    assert gap["required_data"]["data_type"] == "ipd"
    assert set(gap["required_data"]["variables"]) >= {"z", "x", "y", "w"}


def test_fallback_is_mirrored_into_explanation():
    """Same posture as weak_iv_instrument: the renderer cannot drop it."""
    _, result = _data_result(_thin_sample())
    assert "分层 Wald" in (result.get("explanation") or "")


def test_fallback_result_still_verifies():
    ast, result = _data_result(_thin_sample())
    assert themis.verify(ast, result) is None
