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
from themis import gaps as _gaps


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


def test_only_the_data_end_carries_sampling_variance():
    """The one place the two payloads legitimately differ, pinned so it
    stays a decision rather than a drift.

    The variance columns and the weak-robust set are sampling quantities:
    they need an n. The theta end is handed probabilities, not a sample,
    so it has no n to speak of — filling those fields there would mean
    inventing them, and a confidence set that rests on an invented n is
    worse than no confidence set.
    """
    theta_numeric = themis.run(_theta_program())["results"][0][
        "extensions"]["iv_identification"]["numeric"]
    _, result = _data_result()
    numeric = result["numeric_estimate"]

    assert "stratified_anderson_rubin_confidence_set" in numeric
    assert "stratified_anderson_rubin_confidence_set" not in theta_numeric
    for row in numeric["stratified_wald"]["strata"]:
        assert {"shift_var_yy", "shift_var_xy", "shift_var_xx"} <= set(row)
    for row in theta_numeric["strata"]:
        assert not {"shift_var_yy", "shift_var_xy", "shift_var_xx"} & set(row)


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
    NARROWER population than the query asked about.

    Every column is trimmed and every aggregate recomputed, so the record
    is internally consistent; only the weights summing to less than 1
    still says the average is over a different population.
    """
    def mutate(result, inputs):
        for key in ("stratum_weights", "stratum_outcome_shifts",
                    "stratum_treatment_shifts", "stratum_shift_var_yy",
                    "stratum_shift_var_xy", "stratum_shift_var_xx"):
            inputs[key]["items"] = inputs[key]["items"][:1]
        for key in ("sar_kind", "sar_lower", "sar_upper", "sar_point",
                    "sar_kappa", "sar_outcome_shift", "sar_treatment_shift",
                    "sar_var_yy", "sar_var_xy", "sar_var_xx", "sar_n_obs",
                    "sar_n_strata", "sar_dof"):
            inputs.pop(key, None)
        result["numeric_estimate"].pop(
            "stratified_anderson_rubin_confidence_set", None,
        )
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


def test_verifier_rejects_mismatched_stratum_table_lengths():
    """Six columns of one table. A record where they disagree describes no
    partition at all, so nothing downstream of it means anything."""
    def mutate(result, inputs):
        inputs["stratum_shift_var_xx"]["items"] = (
            inputs["stratum_shift_var_xx"]["items"][:1]
        )

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="disagree on length"):
        themis.verify(ast, result)


# --------------------------------------- the stratified weak-robust set

def test_payload_carries_the_stratified_ar_set_and_not_the_linear_one():
    _, result = _data_result()
    numeric = result["numeric_estimate"]
    sar = numeric["stratified_anderson_rubin_confidence_set"]
    assert "anderson_rubin_confidence_set" not in numeric
    assert sar["kind"] in {
        "bounded", "disconnected", "unbounded_below", "unbounded_above",
        "whole_line", "empty",
    }
    assert sar["point"] == pytest.approx(numeric["point"])
    assert sar["outcome_shift"] == pytest.approx(
        numeric["stratified_wald"]["outcome_shift"]
    )
    assert sar["n_strata"] == len(numeric["stratified_wald"]["strata"])
    assert sar["dof"] == sar["n_obs"] - 2 * sar["n_strata"]


def test_verifier_rejects_a_stratified_ar_set_centred_off_the_point():
    """The substitution this whole path exists to prevent, in its last
    remaining hiding place: a set for one estimand beside a point for
    another."""
    def mutate(result, inputs):
        inputs["sar_point"] += 0.05

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="sar_point"):
        themis.verify(ast, result)


def test_verifier_rejects_a_widened_stratified_ar_set():
    def mutate(result, inputs):
        inputs["sar_upper"] += 0.2

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="stratified AR upper mismatch"):
        themis.verify(ast, result)


def test_verifier_rejects_a_tampered_stratum_variance():
    """The endpoints are a closed form of the variance columns, so a
    verifier that took those on trust would be auditing metadata again."""
    def mutate(result, inputs):
        items = list(inputs["stratum_shift_var_yy"]["items"])
        items[0] *= 0.25
        inputs["stratum_shift_var_yy"]["items"] = items

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="sar_var_yy"):
        themis.verify(ast, result)


def test_verifier_rejects_a_tampered_stratified_ar_kappa():
    def mutate(result, inputs):
        inputs["sar_kappa"] *= 0.5

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="sar_kappa"):
        themis.verify(ast, result)


def test_verifier_rejects_a_wrong_stratum_count_on_the_set():
    def mutate(result, inputs):
        inputs["sar_n_strata"] += 1

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="strata but the recorded table"):
        themis.verify(ast, result)


def test_verifier_rejects_the_linear_ar_set_on_a_stratified_method():
    """Caught structurally rather than numerically: when the strata happen
    to share a first-stage strength the linear and stratified points
    coincide, and a value comparison alone would wave this through."""
    def mutate(result, inputs):
        inputs["ar_kind"] = "bounded"
        inputs["ar_lower"] = 0.1
        inputs["ar_upper"] = 0.9

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="carries the LINEAR"):
        themis.verify(ast, result)


def _weak_sample(n: int = 3000, seed: int = 11) -> pd.DataFrame:
    """Same graph, first stage weak enough to trip the Stock-Yogo warning."""
    rng = np.random.default_rng(seed)
    w = rng.random(n) < _P_W1
    z = rng.random(n) < np.where(w, 0.5, 0.3)
    # The instrument barely moves treatment: shift ~0.03 in either stratum.
    p_x = np.where(w, 0.45, 0.40) + np.where(z, 0.03, 0.0)
    x = rng.random(n) < p_x
    p_y = 0.3 + 0.3 * x + 0.2 * w
    return pd.DataFrame({"w": w, "z": z, "x": x, "y": rng.random(n) < p_y})


def test_a_weak_conditional_instrument_surfaces_its_own_robust_set():
    """A weak first stage is exactly when the caller needs the set, so
    this disclosure must not go blind on the path whose set is not the
    linear one. It used to: the warning read the linear field, which the
    stratified path leaves empty, and offered the AR set as something to
    go compute rather than something already on the page."""
    _, result = _data_result(_weak_sample())
    assert result["numeric_estimate"]["method"] == "iv_stratified_wald"

    gaps = (result.get("data_gap_report") or {}).get("gaps", [])
    weak = [g for g in gaps if g["kind"] == "weak_iv_instrument"]
    assert weak, "premise broken: this sample is meant to be weak"
    assert "Anderson-Rubin" in _gaps.described(weak[0])
    assert "弱工具稳健置信集" in _gaps.described(weak[0])
    assert "Anderson-Rubin" in (result.get("explanation") or "")


def test_verifier_rejects_a_stratified_ar_set_on_a_non_stratified_method():
    def mutate(result, inputs):
        for key in ("stratum_weights", "stratum_outcome_shifts",
                    "stratum_treatment_shifts", "stratum_shift_var_yy",
                    "stratum_shift_var_xy", "stratum_shift_var_xx",
                    "aggregate_outcome_shift", "aggregate_treatment_shift"):
            del inputs[key]
        inputs["method"] = "iv_2sls"
        result["numeric_estimate"]["method"] = "iv_2sls"
        result["numeric_estimate"].pop("stratified_wald", None)

    ast, result = _tampered(mutate)
    with pytest.raises(Exception, match="stands for no other estimand"):
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
    assert "顺从者" in _gaps.described(gap)
    # It names the stratum that forced the fallback, so the reader can act.
    assert "w=True" in _gaps.described(gap)
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
