"""An instrument, a dose with steps, and what the number is an average of.

Angrist & Imbens (1995): with variable treatment intensity the IV estimand is
not one local effect. Writing the outcome as

    Y = Y_{s_0} + Σ_j (Y_{s_j} − Y_{s_{j−1}}) · 1{S ≥ s_j}

and using only that Z is independent of every potential outcome makes the
ratio Cov(Y,Z)/Cov(S,Z) an exactly weighted average of the per-unit response
at each step, with weights

    w_j = (s_j − s_{j−1}) · Cov(1{S ≥ s_j}, Z) / Cov(S, Z)

identified from the treatment and the instrument alone. There is no split
between a binary and an ordered instrument because the identity never had one.

Two things follow that the 2SLS answer never said. The weights are a fact
about the data and can be reported. And under monotonicity every one of them
shares the sign of the aggregate first stage — so a NEGATIVE weight refutes
monotonicity, and it can sit behind a perfectly ordinary aggregate first
stage, which is why it has to be looked for.

The oracle here is population-level and exact: the identity is checked
against latent per-unit responses that the estimator never sees.
"""
from __future__ import annotations

import copy
import itertools

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.iv import estimate_iv_ate
from themis.output.analysis_report import build_analysis_report
from themis.refusals import EstimatorFailure

# --------------------------------------------------------------------------
# D1 — the identity, against latent potential outcomes
# --------------------------------------------------------------------------

_DOSE = (0.0, 1.0, 3.0, 4.0)      # deliberately unequal steps
_Z_LEVELS = (0.0, 1.0, 4.0, 9.0)  # deliberately unequal, and ordered


def _population(rng, n, *, monotone: bool):
    """Per unit: the dose it takes at each instrument level, and its own
    outcome at each dose. Nothing here is visible to the estimator."""
    k = len(_DOSE)
    idx = np.zeros((n, len(_Z_LEVELS)), dtype=int)
    idx[:, 0] = rng.integers(0, k, size=n)
    for c in range(1, len(_Z_LEVELS)):
        step = rng.integers(0, 2, size=n)
        if monotone:
            idx[:, c] = np.minimum(k - 1, idx[:, c - 1] + step)
        else:
            down = rng.random(n) < 0.35
            idx[:, c] = np.where(
                down, np.maximum(0, idx[:, c - 1] - step),
                np.minimum(k - 1, idx[:, c - 1] + step))
    return idx, rng.uniform(-2.0, 2.0, size=(n, k))


def _estimand_and_parts(seed: int, *, monotone: bool):
    rng = np.random.default_rng(seed)
    q = rng.uniform(0.15, 0.5, size=len(_Z_LEVELS))
    q = q / q.sum()
    idx, y = _population(rng, 3000, monotone=monotone)
    n = idx.shape[0]
    unit = np.full(n, 1.0 / n)
    z_arr = np.asarray(_Z_LEVELS)
    e_z = float(q @ z_arr)

    s_of = np.asarray(_DOSE)[idx]
    y_of = np.take_along_axis(y, idx, axis=1)
    cov_sz = float(q @ ((z_arr - e_z) * (unit @ s_of)))
    cov_yz = float(q @ ((z_arr - e_z) * (unit @ y_of)))

    weights, responses = [], []
    for j in range(1, len(_DOSE)):
        ind = (s_of >= _DOSE[j]).astype(float)
        cov_ind = float(q @ ((z_arr - e_z) * (unit @ ind)))
        step = _DOSE[j] - _DOSE[j - 1]
        weights.append(step * cov_ind / cov_sz)
        delta = (y[:, j] - y[:, j - 1]) / step
        contrib = float(q @ ((z_arr - e_z) * (unit @ (delta[:, None] * ind))))
        responses.append(contrib / cov_ind)
    return cov_yz / cov_sz, np.array(weights), np.array(responses)


@pytest.mark.parametrize("monotone", [True, False], ids=["monotone", "defiers"])
def test_the_estimand_is_exactly_this_weighted_average(monotone):
    """An identity, not an approximation — so it holds with defiers too."""
    worst = max(
        abs(beta - float(w @ r))
        for beta, w, r in (_estimand_and_parts(s, monotone=monotone)
                           for s in range(40))
    )
    assert worst < 1e-12, worst


@pytest.mark.parametrize("monotone", [True, False], ids=["monotone", "defiers"])
def test_the_weights_sum_to_one_without_being_normalised(monotone):
    """They are not scaled to sum to one on the way out; the identity makes
    them, which is why a vector that sums to one and disagrees with the data
    is still catchable."""
    for seed in range(40):
        _beta, w, _r = _estimand_and_parts(seed, monotone=monotone)
        assert abs(w.sum() - 1.0) < 1e-10


def test_the_spacing_between_doses_is_part_of_the_weight():
    """Dropping (s_j − s_{j−1}) leaves the identity true for equally spaced
    doses and false otherwise — so the factor is pinned rather than left to
    look like a harmless constant."""
    steps = np.diff(np.asarray(_DOSE))
    worst = 0.0
    for seed in range(40):
        beta, w, r = _estimand_and_parts(seed, monotone=True)
        unspaced = w / steps
        unspaced = unspaced / unspaced.sum()
        # Relative: the estimand's own scale varies a lot across draws, and an
        # absolute gap says nothing about a draw whose beta is near zero.
        worst = max(worst, abs(beta - float(unspaced @ r)) / abs(beta))
    assert worst > 0.1, worst


# --------------------------------------------------------------------------
# Samples the estimator actually sees
# --------------------------------------------------------------------------


def _monotone_frame(n=20000, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, size=n)
    u = rng.normal(0, 1, size=n)
    s = np.clip(rng.integers(0, 2, size=n) + z * rng.integers(0, 3, size=n)
                + (u > 1).astype(int), 0, 3)
    p = np.clip(0.12 + 0.18 * s + 0.10 * u, 0.02, 0.98)
    return pd.DataFrame({"z": z.astype(bool), "s": s,
                         "y": rng.random(n) < p})


def _defiant_frame(n=40000, seed=7) -> pd.DataFrame:
    """Sixty per cent of the population is pushed DOWN across the first step
    and forty per cent is pushed hard up across all three. The aggregate
    first stage stays positive, so nothing at the top level looks wrong."""
    rng = np.random.default_rng(seed)
    a = rng.random(n) < 0.60
    z = rng.random(n) < 0.5
    s = np.where(a, np.where(z, 0, 1), np.where(z, 3, 0))
    p = np.clip(0.15 + 0.2 * s, 0.02, 0.98)
    return pd.DataFrame({"z": z, "s": s, "y": rng.random(n) < p})


def _ordered_instrument_frame(n=24000, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 4, size=n)
    u = rng.normal(0, 1, size=n)
    s = np.clip((z > 0).astype(int) + (z > 1).astype(int)
                + (u > 0.8).astype(int), 0, 3)
    p = np.clip(0.2 + 0.15 * s + 0.1 * u, 0.02, 0.98)
    return pd.DataFrame({"z": z, "s": s, "y": rng.random(n) < p})


def test_the_number_does_not_move_when_the_route_changes():
    """This route re-describes a number; it must not recompute one. Bit
    identity, because the point comes from the same function."""
    df = _monotone_frame()
    common = dict(treatment="s", outcome="y", instrument="z", ci_bootstrap=0)
    assert (estimate_iv_ate(df, model="acr", **common).point
            == estimate_iv_ate(df, model="2sls", **common).point)


def test_the_weights_the_estimator_reports_sum_to_one():
    est = estimate_iv_ate(_monotone_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=0)
    assert est.method == "iv_acr"
    assert abs(sum(m.weight for m in est.acr.margins) - 1.0) < 1e-12


def test_a_margin_spans_two_adjacent_levels_the_data_shows():
    """The decomposition is over the levels the sample HAS. The defiant
    population never takes dose 2, so there is no 1 → 2 margin to report and
    the step from 1 to 3 is worth two units."""
    est = estimate_iv_ate(_defiant_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=0)
    spans = [(m.from_dose, m.to_dose, m.step) for m in est.acr.margins]
    assert spans == [(0.0, 1.0, 1.0), (1.0, 3.0, 2.0)]


# --------------------------------------------------------------------------
# The refutation
# --------------------------------------------------------------------------


def test_a_population_that_defies_the_instrument_is_caught():
    est = estimate_iv_ate(_defiant_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=150, random_state=5)
    assert est.acr.first_stage_covariance > 0, "the aggregate must look fine"
    assert est.acr.monotonicity_refuted
    assert est.acr.refuting_margins == (0,)
    assert est.acr.margins[0].weight < 0


def test_an_obedient_population_is_not_accused():
    est = estimate_iv_ate(_monotone_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=150, random_state=5)
    assert not est.acr.monotonicity_refuted
    assert est.acr.refuting_margins == ()


def test_the_interval_decides_when_there_is_one():
    """A weight negative only by sampling noise is not a refutation. Which
    rule was used is not a field — the margins show whether intervals were
    produced, and a field restating that would be a second author of it."""
    df = _monotone_frame()
    with_boot = estimate_iv_ate(df, treatment="s", outcome="y",
                                instrument="z", ci_bootstrap=100,
                                random_state=5)
    without = estimate_iv_ate(df, treatment="s", outcome="y",
                              instrument="z", ci_bootstrap=0)
    assert all(m.ci_upper is not None for m in with_boot.acr.margins)
    assert all(m.ci_upper is None for m in without.acr.margins)


# --------------------------------------------------------------------------
# Which route auto takes, and what it says when it declines
# --------------------------------------------------------------------------


def test_a_binary_treatment_stays_in_the_wald_family():
    """One margin carrying all the weight is the point restated."""
    df = _monotone_frame()
    df["s"] = (df["s"] >= 2).astype(int)
    est = estimate_iv_ate(df, treatment="s", outcome="y", instrument="z",
                          ci_bootstrap=0)
    assert est.method == "iv_wald"
    assert est.acr is None and est.acr_declined is None


def test_a_dose_measured_too_finely_declines_out_loud():
    rng = np.random.default_rng(1)
    n = 6000
    z = rng.integers(0, 2, size=n)
    s = rng.integers(0, 30, size=n) + z * 3
    y = 0.1 * s + rng.normal(0, 1.0, size=n)
    est = estimate_iv_ate(pd.DataFrame({"z": z.astype(bool), "s": s, "y": y}),
                          treatment="s", outcome="y", instrument="z",
                          ci_bootstrap=0)
    assert est.method == "iv_2sls"
    assert est.acr is None
    assert "over_the_cap_of_12" in est.acr_declined


def test_a_conditioning_set_is_a_different_estimand_and_says_so():
    df = _monotone_frame()
    df["w"] = (np.arange(len(df)) % 2).astype(bool)
    auto = estimate_iv_ate(df, treatment="s", outcome="y", instrument="z",
                           conditioning=("w",), ci_bootstrap=0)
    assert auto.method == "iv_2sls"
    assert auto.acr_declined == "conditional_estimand_is_not_the_unconditional_ACR"
    with pytest.raises(EstimatorFailure) as caught:
        estimate_iv_ate(df, treatment="s", outcome="y", instrument="z",
                        conditioning=("w",), model="acr", ci_bootstrap=0)
    assert caught.value.failure_type == "option_answers_another_question"


def test_an_ordered_instrument_claims_no_share_of_anybody():
    """With more than two instrument levels the covariance is still the
    weight's basis but is a proportion of nobody."""
    est = estimate_iv_ate(_ordered_instrument_frame(), treatment="s",
                          outcome="y", instrument="z", ci_bootstrap=0)
    assert est.method == "iv_acr"
    assert len(est.acr.instrument_levels) == 4
    assert all(m.share_moved is None for m in est.acr.margins)
    assert abs(sum(m.weight for m in est.acr.margins) - 1.0) < 1e-12


def test_a_binary_instrument_says_who_it_moved():
    est = estimate_iv_ate(_monotone_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=0)
    assert all(m.share_moved is not None for m in est.acr.margins)


# --------------------------------------------------------------------------
# End to end: the envelope, the reader, and the verifier
# --------------------------------------------------------------------------


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "s", "domain": [0, 1, 2, 3]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("s")},
            {"kind": "cause", "from": _atom("s"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("s"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("s"), "value": 1},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "assumptions": {"monotonicity": "non_decreasing"},
            }},
        ],
    }


def _answer(frame):
    program = _program()
    result = themis.estimate(program, frame, ci_bootstrap=120,
                             random_state=5)["results"][0]
    assert result["status"] == "numerically_solved", result
    return program, result


def test_the_envelope_carries_the_table_and_verifies():
    program, result = _answer(_monotone_frame())
    block = result["numeric_estimate"]["acr_decomposition"]
    assert result["numeric_estimate"]["method"] == "iv_acr"
    assert len(block["margins"]) == 3
    themis.verify(program, result)


@pytest.mark.parametrize(
    "lang,needle",
    [("zh", "这个数是哪几档剂量的平均"),
     ("en", "Which steps of the dose this number averages over")],
)
def test_the_reader_is_told_which_doses(lang, needle):
    _program_, result = _answer(_monotone_frame())
    assert needle in build_analysis_report(result, lang=lang)


@pytest.mark.parametrize(
    "lang,needle",
    [("zh", "单调性被数据否掉了"), ("en", "The data refutes monotonicity")],
)
def test_the_reader_is_told_when_the_data_says_no(lang, needle):
    _program_, result = _answer(_defiant_frame())
    assert needle in build_analysis_report(result, lang=lang)


FORGERIES = [
    ("a weight nudged",
     lambda a: a["margins"][0].update({"weight": a["margins"][0]["weight"] + 0.05})),
    ("weights swapped between two margins",
     lambda a: (a["margins"][0].__setitem__("weight", a["margins"][1]["weight"]),
                a["margins"][1].__setitem__("weight", a["margins"][0]["weight"]))),
    ("a covariance forged",
     lambda a: a["margins"][-1].update(
         {"covariance": a["margins"][-1]["covariance"] * 1.4})),
    ("a cell count inflated",
     lambda a: a["cells"][0].update({"n": a["cells"][0]["n"] + 25})),
    ("an outcome sum moved",
     lambda a: a["cells"][0].update(
         {"sum_outcome": a["cells"][0]["sum_outcome"] + 40.0})),
    ("a share claimed that nobody moved",
     lambda a: a["margins"][0].update({"share_moved": 0.9})),
    ("the levels reversed",
     lambda a: a.update({"levels": list(reversed(a["levels"]))})),
    ("an interval dropped from one margin only",
     lambda a: a["margins"][0].update({"ci_lower": None, "ci_upper": None})),
    ("a threshold count above the one below it",
     lambda a: a["cells"][0]["at_or_above"].__setitem__(
         -1, a["cells"][0]["at_or_above"][0] + 1)),
    ("the point detached from the covariances",
     lambda a: a.update({"outcome_covariance": a["outcome_covariance"] * 1.2})),
]


@pytest.mark.parametrize("label,mutate", FORGERIES,
                         ids=[f[0] for f in FORGERIES])
def test_a_forged_margin_table_is_rejected(label, mutate):
    program, result = _answer(_monotone_frame())
    tampered = copy.deepcopy(result)
    mutate(tampered["numeric_estimate"]["acr_decomposition"])
    with pytest.raises(Exception):
        themis.verify(program, tampered)


def test_a_suppressed_refutation_is_rejected():
    """The block's one claim about the world, and the one worth lying about."""
    program, result = _answer(_defiant_frame())
    tampered = copy.deepcopy(result)
    tampered["numeric_estimate"]["acr_decomposition"].update(
        {"monotonicity_refuted": False, "refuting_margins": []})
    with pytest.raises(Exception):
        themis.verify(program, tampered)


def test_the_assumptions_it_declares_have_words():
    """A build with no word for an assumption it declares says so out loud in
    the report, which is worse than saying nothing."""
    _program_, result = _answer(_monotone_frame())
    for lang, absent in (("zh", "本版本没有它的说法"),
                         ("en", "this build has no word for it")):
        assert absent not in build_analysis_report(result, lang=lang)


def test_monotonicity_is_declared_refutable_here():
    """The Wald calls it untestable and is right to; this route computes the
    quantity it constrains, so the same word would be false."""
    est = estimate_iv_ate(_monotone_frame(), treatment="s", outcome="y",
                          instrument="z", ci_bootstrap=0)
    assert any(a.startswith("monotonicity_refutable_") for a in est.assumptions)
    assert not any("constant_treatment_effect" in a for a in est.assumptions)
