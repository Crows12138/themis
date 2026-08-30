"""Simulation-extrapolation: what a second author can redo, and what they cannot.

The deferral this overturns said SIMEX "does not fit the per-number
re-derivation contract" because it is a simulation. That treats SIMEX as
one thing and it is two, and the seam between them is where the contract
holds again: only the FIRST stage is random, and its output — the
simulation ladder — is the second stage's sufficient statistic. So the
ladder travels, and everything downstream of it is a closed-form least
squares problem an independent transcription redoes.

What that leaves is stated rather than papered over, and the tests here
are in three groups for the three claims:

- the arithmetic is right, measured against the one case where a closed
  form exists (a linear outcome, where the decay is exactly rational, so
  SIMEX must reproduce regression calibration's moment correction);
- the audit accepts honest ladders and rejects forged ones, including the
  forgery of withholding an interval for a reason that is not true;
- the caller declares which estimand they want, and the declaration is
  what routes — because nothing in the data distinguishes a
  linear-probability slope from a log-odds ratio.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _simex_block
from themis.estimation.regression_calibration import (
    estimate_regression_calibration,
)
from themis.estimation.simex import (
    DEFAULT_LAMBDAS,
    SimexEstimate,
    estimate_simex,
)
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.errors import VerificationError
from themis.verifier.simex_rules import verify_simex_numeric

SIGMA2_U = 0.5


# --- data ---------------------------------------------------------------------


def _linear_frame(n=4000, seed=0, beta=0.8, sigma2_u=SIGMA2_U):
    """A LINEAR outcome, which is the oracle: the naive slope decays exactly
    as θ(λ) = θ_naive·Var(W|Z)/(Var(W|Z)+λσ²_u), a rational function."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + beta * x + 0.4 * z + rng.normal(0, 1.0, n)
    w = x + rng.normal(0, np.sqrt(sigma2_u), n)
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _logistic_frame(n=6000, seed=1, beta=1.0, sigma2_u=SIGMA2_U):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 1, n)
    p = 1.0 / (1.0 + np.exp(-(-0.2 + beta * x + 0.5 * z)))
    y = (rng.random(n) < p).astype(float)
    w = x + rng.normal(0, np.sqrt(sigma2_u), n)
    return pd.DataFrame({"w": w, "y": y, "z": z, "x_true": x})


def _fit(frame=None, **kwargs):
    kwargs.setdefault("error_variance", SIGMA2_U)
    kwargs.setdefault("n_replicates", 60)
    kwargs.setdefault("random_state", 3)
    return estimate_simex(
        _logistic_frame() if frame is None else frame,
        treatment="w", outcome="y", adjustment=("z",), **kwargs)


def _envelope(est: SimexEstimate) -> dict:
    """The numeric_estimate the dispatch writes, which is what the audit
    reads — built through the producer's own block so the two agree."""
    return {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": "simex",
        "treatment": est.treatment,
        "outcome": est.outcome,
        "simex": _simex_block(est),
    }


@pytest.fixture(scope="module")
def honest() -> dict:
    """One accepted artifact, reused by the forgeries so that each one is
    the honest record with exactly one thing changed."""
    return _envelope(_fit(outcome_model="linear", frame=_linear_frame(),
                          extrapolant="quadratic"))


# --- the arithmetic, against the one closed form there is ---------------------


def test_a_linear_outcome_reproduces_the_moment_correction():
    """The oracle. Under a linear outcome the decay is exactly rational, so
    the rational extrapolant must land on regression calibration's closed
    form — the whole pipeline, simulation stage included, against a number
    computed by algebra that never simulated anything."""
    df = _linear_frame()
    closed = estimate_regression_calibration(
        df, treatment="w", outcome="y", adjustment=("z",),
        error_variance=SIGMA2_U, ci_bootstrap=0)
    est = _fit(frame=df, outcome_model="linear", extrapolant="rational",
               n_replicates=200, random_state=7)
    assert est.point == pytest.approx(closed.point, abs=5e-3)
    # And the correction moved the number the way attenuation says it must.
    assert est.naive_point < est.point
    assert est.naive_point == pytest.approx(closed.naive_point, abs=1e-9)


def test_the_zero_rung_is_the_uncorrected_fit_and_not_a_simulation():
    est = _fit()
    first = est.grid[0]
    assert first.lam == 0.0
    assert first.replicates == 1
    assert first.replicate_variance == 0.0
    assert first.theta == est.naive_point


def test_the_ladder_climbs_and_the_estimate_decays_along_it():
    """Adding noise makes the measurement worse, and worse measurement
    attenuates. A ladder that did not decay would mean the simulation was
    not doing what the extrapolation reads."""
    est = _fit(n_replicates=120)
    lams = [g.lam for g in est.grid]
    assert lams == list(DEFAULT_LAMBDAS)
    thetas = [g.theta for g in est.grid]
    assert all(b < a for a, b in zip(thetas, thetas[1:]))


def test_the_correction_moves_the_coefficient_toward_the_true_exposure():
    """The unattainable comparison: fit on the exposure nobody measured."""
    from themis.estimation.simex import _design, _fit_logistic

    df = _logistic_frame()
    y = df["y"].to_numpy(float)
    covariates = df[["z"]].to_numpy(float)
    target, _ = _fit_logistic(
        _design(df["x_true"].to_numpy(float), covariates), y)
    est = _fit(frame=df, n_replicates=200, random_state=5)
    assert abs(est.point - target) < abs(est.naive_point - target)


def test_a_finer_ladder_does_not_move_the_oracle_case():
    """Where the rational model holds exactly the fit is exact, so more
    rungs buy precision rather than a different answer."""
    df = _linear_frame()
    coarse = _fit(frame=df, outcome_model="linear", extrapolant="rational",
                  n_replicates=300, random_state=11)
    fine = _fit(frame=df, outcome_model="linear", extrapolant="rational",
                lambdas=tuple(np.round(np.linspace(0, 2, 9), 3).tolist()),
                n_replicates=300, random_state=11)
    assert fine.point == pytest.approx(coarse.point, abs=1e-2)


# --- the audit accepts what is honest ----------------------------------------


@pytest.mark.parametrize("outcome_model", ["linear", "logistic"])
@pytest.mark.parametrize("extrapolant", ["linear", "quadratic", "rational"])
def test_every_declared_family_is_re_derived_from_its_own_ladder(
    outcome_model, extrapolant,
):
    frame = _linear_frame() if outcome_model == "linear" else _logistic_frame()
    est = _fit(frame=frame, outcome_model=outcome_model,
               extrapolant=extrapolant)
    verify_simex_numeric(_envelope(est))


def test_the_audit_is_quiet_about_an_estimate_that_is_not_its_business():
    verify_simex_numeric({"method": "backdoor_gformula", "point": 1.0})


def test_the_re_derivation_uses_only_the_ladder():
    """Strip the estimate to what the audit is allowed to read and it still
    passes — which is the claim the whole overturn rests on."""
    full = _envelope(_fit())
    bare = {
        "method": "simex", "point": full["point"],
        "ci_lower": full["ci_lower"], "ci_upper": full["ci_upper"],
        "ci_level": full["ci_level"], "simex": full["simex"],
    }
    verify_simex_numeric(bare)


# --- and rejects what is not --------------------------------------------------


def _forged(honest: dict, mutate) -> dict:
    bad = copy.deepcopy(honest)
    mutate(bad)
    return bad


def _bump(node: dict, path, delta):
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = node[path[-1]] + delta


FORGERIES = {
    "the point moved": lambda d: _bump(d, ["point"], 0.02),
    "the point moved by a hair": lambda d: _bump(d, ["point"], 1e-6),
    "a coefficient moved":
        lambda d: _bump(d, ["simex", "coefficients", 0], 0.01),
    "a rung's estimate moved":
        lambda d: _bump(d, ["simex", "grid", 2, "theta"], 0.01),
    "the naive point moved":
        lambda d: _bump(d, ["simex", "naive_point"], 0.01),
    "the zero rung claims replicates":
        lambda d: d["simex"]["grid"][0].__setitem__("replicates", 60),
    "the zero rung claims a spread":
        lambda d: d["simex"]["grid"][0].__setitem__(
            "replicate_variance", 1e-9),
    "the ladder does not start at zero":
        lambda d: d["simex"]["grid"][0].__setitem__("lambda", 0.1),
    "the ladder goes backwards":
        lambda d: d["simex"]["grid"][3].__setitem__("lambda", 0.25),
    "a rung disagrees about the replicate count":
        lambda d: d["simex"]["grid"][2].__setitem__("replicates", 59),
    "the interval widened": lambda d: _bump(d, ["ci_upper"], 0.05),
    "the level changed and the endpoints did not":
        lambda d: d.__setitem__("ci_level", 0.99),
    "the extrapolated variance moved":
        lambda d: _bump(d, ["simex", "extrapolated_variance"], 0.001),
    "a variance coefficient moved":
        lambda d: _bump(d, ["simex", "variance_coefficients", 0], 0.01),
    "the ladder was truncated below the family's need":
        lambda d: d["simex"].__setitem__("grid", d["simex"]["grid"][:3]),
    "the extrapolant was relabelled":
        lambda d: d["simex"].__setitem__("extrapolant", "rational"),
    "a rung reports a negative variance":
        lambda d: d["simex"]["grid"][1].__setitem__("variance_mean", -1.0),
    "one endpoint only": lambda d: d.__setitem__("ci_upper", None),
    "no ladder at all": lambda d: d.__setitem__("simex", None),
    "an interval beside a declared cluster":
        lambda d: d["simex"].__setitem__("cluster", "family"),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_tampered_record_is_rejected(honest, name):
    verify_simex_numeric(honest)      # the same record, unaltered, passes
    with pytest.raises(VerificationError):
        verify_simex_numeric(_forged(honest, FORGERIES[name]))


def _withhold(d: dict, reason: str) -> None:
    d["ci_lower"] = d["ci_upper"] = None
    d["simex"]["extrapolated_variance"] = None
    d["simex"]["no_interval_because"] = reason


@pytest.mark.parametrize("reason", [
    "extrapolated_variance_is_not_positive",
    "declared_clustering_is_not_in_the_variance",
    "the_dog_ate_it",
    None,
])
def test_withholding_an_interval_is_a_claim_that_is_checked(honest, reason):
    """The forgery a re-derivation invites: drop the interval rather than
    have it disagree. Both reasons the producer may give are held against
    the record — the variance has to recompute non-positive, and the
    clustering has to name a column."""
    with pytest.raises(VerificationError):
        verify_simex_numeric(_forged(honest, lambda d: _withhold(d, reason)))


def test_a_cluster_withholds_the_interval_rather_than_widening_it():
    """A model-based variance is a statement about independent rows, and
    the caller has said they are not. The point is untouched, because
    clustering costs precision and not identification."""
    df = _logistic_frame()
    df["family"] = np.repeat(np.arange(len(df) // 4), 4)
    plain = _fit(frame=df)
    clustered = _fit(frame=df, cluster="family")
    assert clustered.point == plain.point
    assert clustered.ci_lower is None and clustered.ci_upper is None
    assert clustered.extrapolated_variance is None
    assert (clustered.no_interval_because
            == "declared_clustering_is_not_in_the_variance")
    verify_simex_numeric(_envelope(clustered))


# --- the refusals -------------------------------------------------------------


@pytest.mark.parametrize("kwargs, expected", [
    ({"lambdas": (0.5, 1.0, 1.5, 2.0)}, Refusal.SIMEX_GRID_IS_NOT_A_LADDER),
    ({"lambdas": (0.0, 1.0, 0.5, 2.0)}, Refusal.SIMEX_GRID_IS_NOT_A_LADDER),
    ({"lambdas": (0.0, 1.0, 1.0)}, Refusal.SIMEX_GRID_IS_NOT_A_LADDER),
    ({"lambdas": (0.0, 1.0, 2.0)},
     Refusal.SIMEX_GRID_IS_TOO_SHORT_FOR_THE_EXTRAPOLANT),
    ({"error_variance": 0.0}, Refusal.NON_POSITIVE_ERROR_VARIANCE),
    ({"error_variance": -1.0}, Refusal.NON_POSITIVE_ERROR_VARIANCE),
])
def test_a_request_the_method_cannot_serve_is_refused(kwargs, expected):
    with pytest.raises(EstimatorFailure) as caught:
        _fit(**kwargs)
    assert caught.value.failure_type is expected


def test_a_near_discrete_exposure_is_a_misclassification_object():
    df = _logistic_frame()
    df["w"] = (df["w"] > 0).astype(float)
    with pytest.raises(EstimatorFailure) as caught:
        _fit(frame=df)
    assert caught.value.failure_type is Refusal.EXPOSURE_NOT_CONTINUOUS


def test_a_non_binary_outcome_under_a_logistic_model_is_refused():
    with pytest.raises(EstimatorFailure) as caught:
        _fit(frame=_linear_frame())
    assert caught.value.failure_type is Refusal.OUTCOME_NOT_BINARY


# --- the declaration is what routes ------------------------------------------


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "w",
             "measurement": "single-occasion continuous measurement (noisy)"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("w")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("w"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _binary_frame(seed=11, n=5000):
    df = _logistic_frame(n=n, seed=seed)
    return pd.DataFrame(
        {"w": df["w"], "y": df["y"].astype(bool), "z": df["z"]})


def _run(spec: dict) -> dict:
    out = themis.estimate(_program(), _binary_frame(), ci_bootstrap=0,
                          measurement_error=spec)
    return out["results"][0]


@pytest.mark.parametrize("spec, method", [
    ({"w": {"error_variance": SIGMA2_U, "outcome_model": "logistic"}},
     "simex"),
    # No declaration, and an explicit linear one, are the same request: the
    # closed form answers, because it beats a seeded simulation of itself.
    ({"w": {"error_variance": SIGMA2_U}}, "regression_calibration"),
    ({"w": {"error_variance": SIGMA2_U, "outcome_model": "linear"}},
     "regression_calibration"),
])
def test_the_declared_outcome_model_is_what_routes(spec, method):
    result = _run(spec)
    assert result["status"] == "numerically_solved"
    assert result["numeric_estimate"]["method"] == method


def test_a_second_mismeasured_column_is_refused_rather_than_ignored():
    """Simulation perturbs one variable. Perturbing two needs their errors'
    covariance, which per-column variances do not carry — so the request is
    refused rather than half honoured under a heading that says the
    measurement was corrected."""
    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"},
                   "z": {"error_variance": 0.2}})
    assert result.get("numeric_estimate") is None
    assert (result["estimator_failure"]["failure_type"]
            == "simex_perturbs_one_mismeasured_column")


def test_the_whole_road_verifies():
    program = _program()
    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    themis.verify(program, result)


def test_the_envelope_carries_the_ladder_and_who_pulled_each_lever():
    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    block = result["numeric_estimate"]["simex"]
    assert block["outcome_model_was_declared"] is True
    # The extrapolant was not named, so nobody but the estimator chose it.
    assert block["extrapolant_was_declared"] is False
    assert [g["lambda"] for g in block["grid"]] == list(DEFAULT_LAMBDAS)
    assert block["grid"][0]["theta"] == block["naive_point"]


def test_the_ledger_offers_the_declaration_as_the_readers_to_change():
    """A line marked as the caller's CHOICE promises a lever they can find.
    Here it is the outcome model, and the block records the pull as a fact
    beside what the lever settled at."""
    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    ledger = result["extensions"]["assumption_ledger"]["assumptions"]
    lines = {e.get("id"): e for e in ledger}
    estimand = lines["simex_estimand_is_the_exposure_coefficient_in_a_logistic"]
    assert estimand["provenance"] == "caller_chose"
    assert estimand["layer"] == "functional_form"
    assert lines["simex_extrapolant_declared_rational"]["provenance"] == \
        "default"
    # And what the interval does NOT cover is a declared row, not a footnote.
    covers = lines["simex_interval_covers_sampling_not_extrapolation_error"]
    assert covers["layer"] == "confidence"


def _ledger_line(result: dict, line_id: str) -> dict:
    for entry in result["extensions"]["assumption_ledger"]["assumptions"]:
        if entry.get("id") == line_id:
            return entry
    raise AssertionError(f"{line_id} is not on this ledger")


def _restate(result: dict, line_id: str, provenance: str) -> None:
    """Say the same new thing on BOTH surfaces that carry an attribution.

    The ledger line and the mechanism audit answer the same question, and a
    separate pass already holds them to each other — so a forgery that
    moves only one is caught before it reaches the pass under test here.
    Moving both is what isolates the third record: the estimate's own note
    of which lever the caller actually pulled.
    """
    _ledger_line(result, line_id)["provenance"] = provenance
    for mech in result["extensions"]["mechanism_audit"]["mechanisms"]:
        for named in mech.get("assumptions") or ():
            if named.get("id") == line_id:
                named["settled_by"] = provenance


@pytest.mark.parametrize("line_id, provenance, field", [
    # A line handed to the reader as THEIRS to change, on a run where they
    # changed nothing: the lever is one they cannot find.
    ("simex_extrapolant_declared_rational", "caller_chose",
     "extrapolant_was_declared"),
    # And the mirror: a line saying nobody chose it, on a run where the
    # caller did — a lever the reader is told they do not have.
    ("simex_estimand_is_the_exposure_coefficient_in_a_logistic", "default",
     "outcome_model_was_declared"),
])
def test_an_attribution_the_record_contradicts_is_rejected(
    line_id, provenance, field,
):
    from themis.verifier.assumption_ledger_rules import (
        verify_assumption_ledger,
    )

    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    verify_assumption_ledger(result)          # honest, and it passes

    forged = copy.deepcopy(result)
    _restate(forged, line_id, provenance)
    with pytest.raises(VerificationError):
        verify_assumption_ledger(forged)

    # The same relabelling with the RECORD moved to match is not a forgery,
    # which is what makes the check about agreement rather than about the
    # attribution alone.
    consistent = copy.deepcopy(forged)
    block = consistent["numeric_estimate"]["simex"]
    block[field] = provenance == "caller_chose"
    verify_assumption_ledger(consistent)


def test_a_choice_attributed_to_the_wrong_position_is_rejected():
    """The line names the lever AND where it was set. A run that chose the
    rational family does not back a claim that the caller chose the
    quadratic one, even though both are legitimate values."""
    from themis.verifier.assumption_ledger_rules import (
        verify_assumption_ledger,
    )

    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    forged = copy.deepcopy(result)
    _restate(forged, "simex_extrapolant_declared_rational", "caller_chose")
    _ledger_line(forged, "simex_extrapolant_declared_rational")["id"] = \
        "simex_extrapolant_declared_quadratic"
    forged["numeric_estimate"]["simex"]["extrapolant_was_declared"] = True
    with pytest.raises(VerificationError):
        verify_assumption_ledger(forged)


def test_the_report_says_what_the_number_is_before_how_it_was_made():
    from themis.output.analysis_report import build_analysis_report

    program = _program()
    result = _run({"w": {"error_variance": SIGMA2_U,
                         "outcome_model": "logistic"}})
    for lang, expected in (
        ("zh", ("模拟外推", "条件对数优势比", "λ=0 那一档不是模拟", "有理式")),
        ("en", ("Simulation-extrapolation", "log-odds ratio",
                "not a simulation", "rational")),
    ):
        text = build_analysis_report(result, program=program, lang=lang)
        for phrase in expected:
            assert phrase in text, (lang, phrase)


# --- the shape says its own shape ---------------------------------------------


def test_the_schema_says_what_cannot_be_re_derived():
    """The honest residue, on the artifact rather than only in a docstring:
    the ladder is a seeded Monte Carlo, reproducible from the seed and not
    recomputable by a second author."""
    path = (pathlib.Path(themis.__file__).resolve().parent
            / "schemas" / "query_result.schema.json")
    block = json.loads(path.read_text(encoding="utf-8"))[
        "properties"]["numeric_estimate"]["properties"]["simex"]
    assert "not recomputable by a second author" in block["description"]
    assert "random_state" in block["required"]
