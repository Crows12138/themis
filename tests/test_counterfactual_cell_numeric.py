"""Data end of the binary counterfactual cell — estimator, wiring, verifier.

The theta end (``tests/test_counterfactual_cell_e2e.py``) answers
``P(Y_{x'}=y*|X=x[,Y=y])`` from a declared distribution. This slice threads the
DATA end through the estimation dispatch, schema, and independent verifier, so a
client can hand the kernel a counterfactual query + a DataFrame and get the cell
back with a bootstrap the theta end cannot express.

The through-line is the same cross-door invariant, now on data: the PN cell
asked here and PN asked through the ``causation`` door are the same number, and
they must agree to the last bit when computed from the same DataFrame.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.causation import estimate_causation_probabilities
from themis.estimation.counterfactual_cell import estimate_counterfactual_cell
from themis.refusals import EstimatorFailure
from themis.input.syntactic_validator import validate_result
from themis.types import (
    Atom,
    CounterfactualAssumptions,
    CounterfactualQuery,
    Intervention,
    Monotonicity,
    ValuedAtom,
)
from themis.verifier import VerificationError

import networkx as nx


X = Atom(predicate="x", args=())
Y = Atom(predicate="y", args=())
Z = Atom(predicate="z", args=())
M = Atom(predicate="m", args=())


# ------------------------------------------------------------------ builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _atom(p):
    return {"predicate": p, "args": []}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _cf_query_json(*, x_obs, x_cf, y_star, factual_y=None, **extra):
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


def _ast(edges, *, variables=("x", "y", "z"), bidirected=(), **qkw):
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *(_var(v) for v in variables),
            *edges,
            *bidirected,
            {"kind": "query", "id": "q", "query": _cf_query_json(**qkw)},
        ],
    }


_CONFOUNDED = (_cause("z", "x"), _cause("z", "y"), _cause("x", "y"))
_BIDIRECTED_XY = ({"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},)


def _confounded_graph():
    g = nx.DiGraph()
    g.add_edges_from([(Z, X), (Z, Y), (X, Y)])
    return g


def _latent_graph():
    """X → Y with an unmeasured common cause — no admissible adjustment set."""
    g = nx.DiGraph()
    g.add_edge(X, Y)
    return g


_LATENT = frozenset({frozenset({X, Y})})


def _query(*, x_obs, x_cf, y_star, factual_y=None, mono=None, risk1=None, risk0=None):
    return CounterfactualQuery(
        observed=ValuedAtom(atom=X, value=x_obs),
        counterfactual_intervention=Intervention(atom=X, value=x_cf),
        counterfactual_target=ValuedAtom(atom=Y, value=y_star),
        factual_target_known=factual_y,
        assumptions=CounterfactualAssumptions(monotonicity=mono) if mono else None,
        experimental_risk_treated=risk1,
        experimental_risk_control=risk0,
    )


def _sample(n: int, seed: int) -> pd.DataFrame:
    """Rank-preserving MONOTONE SCM with an observed confounder Z; the same
    generator the causation numeric tests use (true PN≈0.446)."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.5, 0.2)
    b = np.where(z, 0.8, 0.6)
    y0, y1 = u < a, u < b
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _sample_with_potential_outcomes(n: int, seed: int):
    """``_sample`` again, but ALSO returning the latent potential outcomes.

    Y_0 and Y_1 are not observable from the frame the estimator sees — half of
    each is counterfactual. Keeping them here gives a truth oracle that counts
    units rather than re-running any identity: it tests the whole chain
    (back-door g-formula → consistency identity) against the SCM that generated
    the data, not against a second implementation of the same theorem."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.5, 0.2)
    b = np.where(z, 0.8, 0.6)
    y0, y1 = u < a, u < b
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z}), y0, y1


def _sample_nonmono(n: int, seed: int) -> pd.DataFrame:
    """Confounded SCM WITH preventive units, so Y is NOT monotone in X."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.15, 0.25)
    b = np.where(z, 0.55, 0.55)
    c = np.where(z, 0.80, 0.75)
    surv, helped, hurt = u < a, (u >= a) & (u < b), (u >= b) & (u < c)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.zeros(n, dtype=bool)
    y[surv] = True
    y[helped] = x[helped]
    y[hurt] = ~x[hurt]
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _exact_joint_frame(n_x1y1, n_x1y0, n_x0y1, n_x0y0) -> pd.DataFrame:
    """A two-column frame with EXACT cell counts, so the empirical joint is
    known to the last digit and hand arithmetic can be checked against it."""
    rows = (
        [(True, True)] * n_x1y1 + [(True, False)] * n_x1y0
        + [(False, True)] * n_x0y1 + [(False, False)] * n_x0y0
    )
    return pd.DataFrame(rows, columns=["x", "y"])


def _result(out):
    return out["results"][0]


# ================================================ the cross-door invariant
def test_pn_cell_matches_the_causation_door_on_the_same_dataframe():
    """PN = P(Y_{x=0}=0 | X=1, Y=1) computed both ways from one DataFrame."""
    df = _sample_nonmono(20_000, seed=3)
    g = _confounded_graph()
    poc = estimate_causation_probabilities(
        df, graph=g, cause=X, effect=Y, monotonic=False, ci_bootstrap=0,
    )
    cell = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert cell.low == pytest.approx(poc.pn_lower, abs=1e-12)
    assert cell.high == pytest.approx(poc.pn_upper, abs=1e-12)
    assert cell.point is None                       # genuinely an interval
    assert cell.high - cell.low > 1e-3


def test_ps_cell_matches_the_causation_door_on_the_same_dataframe():
    """PS = P(Y_{x=1}=1 | X=0, Y=0) computed both ways from one DataFrame."""
    df = _sample_nonmono(20_000, seed=4)
    g = _confounded_graph()
    poc = estimate_causation_probabilities(
        df, graph=g, cause=X, effect=Y, monotonic=False, ci_bootstrap=0,
    )
    cell = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=False, x_cf=True, y_star=True, factual_y=False),
        ci_bootstrap=0,
    )
    assert cell.low == pytest.approx(poc.ps_lower, abs=1e-12)
    assert cell.high == pytest.approx(poc.ps_upper, abs=1e-12)


def test_monotone_pn_cell_matches_the_causation_point_and_the_truth():
    df = _sample(60_000, seed=5)
    g = _confounded_graph()
    poc = estimate_causation_probabilities(
        df, graph=g, cause=X, effect=Y, monotonic=True, ci_bootstrap=0,
    )
    cell = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=0,
    )
    assert cell.point == pytest.approx(poc.pn_point, abs=1e-12)
    assert cell.point == pytest.approx(0.446, abs=0.02)   # the generator's truth


# ===================================== truth oracle: count, don't re-derive
def test_ett_point_recovers_the_counted_truth():
    """P(Y_{x=0}=1 | X=1) against the units the generator actually made."""
    df, y0, _y1 = _sample_with_potential_outcomes(200_000, seed=18)
    truth = y0[df.x.to_numpy()].mean()
    cell = estimate_counterfactual_cell(
        df, graph=_confounded_graph(),
        query=_query(x_obs=True, x_cf=False, y_star=True),
        ci_bootstrap=0,
    )
    assert cell.point == pytest.approx(truth, abs=0.01)


def test_monotone_pn_point_recovers_the_counted_truth():
    """PN = P(Y_{x=0}=0 | X=1, Y=1) against the counted potential outcomes.

    The generator is rank-preserving, so the declared monotonicity is TRUE
    here and the point identification it licenses must land on the truth."""
    df, y0, _y1 = _sample_with_potential_outcomes(200_000, seed=19)
    x = df.x.to_numpy()
    y = df.y.to_numpy()
    truth = (~y0[x & y]).mean()
    cell = estimate_counterfactual_cell(
        df, graph=_confounded_graph(),
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=0,
    )
    assert cell.point == pytest.approx(truth, abs=0.01)


def test_the_assumption_free_interval_covers_the_counted_truth():
    """Without monotonicity the answer is an interval — and an honest one has
    to CONTAIN the truth even on data whose SCM is non-monotone."""
    rng = np.random.default_rng(20)
    n = 200_000
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.15, 0.25)
    b = np.where(z, 0.55, 0.55)
    c = np.where(z, 0.80, 0.75)
    surv, helped, hurt = u < a, (u >= a) & (u < b), (u >= b) & (u < c)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y0 = surv | hurt
    y1 = surv | helped
    y = np.where(x, y1, y0)
    df = pd.DataFrame({"x": x, "y": y, "z": z})

    truth = (~y0[x & y]).mean()
    cell = estimate_counterfactual_cell(
        df, graph=_confounded_graph(),
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert cell.point is None
    assert cell.low - 1e-6 <= truth <= cell.high + 1e-6
    # ... and not vacuously so. On THIS SCM the assumption-free bound bites
    # from below only (the upper end really is 1: no observational
    # distribution rules out every treated-and-recovered unit having been
    # saved by the treatment), so the informativeness claim is one-sided.
    assert cell.low > 0.1
    assert truth - cell.low > 0.05


# ============================================ what each shape of cell gives
def test_no_factual_outcome_is_a_point_not_an_interval():
    """Without the factual Y the target IS the left side of the identity over
    P(x) — the ETT identity, point-identified outright."""
    df = _exact_joint_frame(3200, 800, 1800, 4200)
    cell = estimate_counterfactual_cell(
        df, graph=_latent_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=True, risk0=0.30),
        ci_bootstrap=0,
    )
    # k = 0.30 - 0.18 = 0.12; P(x=1) = 0.40; 0.12/0.40 = 0.30
    assert cell.point == pytest.approx(0.30)
    assert cell.interventional_risk_provenance == "user_experimental"


def test_same_world_cell_needs_no_interventional_risk_at_all():
    df = _sample(5_000, seed=6)
    cell = estimate_counterfactual_cell(
        df, graph=_confounded_graph(),
        query=_query(x_obs=True, x_cf=True, y_star=True),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "not_required"
    assert cell.p_y_do_x_cf is None
    assert cell.adjustment == ()
    assert cell.point == pytest.approx(df[df.x].y.mean())


def test_only_the_arm_the_cell_asks_about_is_ever_fetched():
    """A dataset with a positivity hole in the arm the cell does NOT use.

    Stratum z=1 contains only X=1 rows, so P(Y=1|do(X=0)) is not estimable by
    standardization. A cell asking about do(X=1) must still be answerable —
    demanding the other arm would manufacture a data requirement out of
    information the answer never touches. The causation door, which needs BOTH
    arms, correctly refuses on the same frame."""
    rows = (
        [(True, True, True)] * 900 + [(True, True, False)] * 600
        + [(False, True, True)] * 400 + [(False, True, False)] * 700
        + [(False, False, True)] * 500 + [(False, False, False)] * 900
    )
    df = pd.DataFrame(rows, columns=["z", "x", "y"])
    assert ((df.z) & (~df.x)).sum() == 0          # the hole, by construction
    g = _confounded_graph()

    cell = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=False, x_cf=True, y_star=True, factual_y=False),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "backdoor_adjustment"
    assert cell.adjustment == ("z",)
    assert cell.p_y_do_x_cf is not None

    with pytest.raises(EstimatorFailure):
        estimate_causation_probabilities(
            df, graph=g, cause=X, effect=Y, monotonic=False, ci_bootstrap=0,
        )


def test_unmeasured_confounding_refuses_rather_than_returning_the_vacuous_range():
    df = _sample_nonmono(4_000, seed=7)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_counterfactual_cell(
            df, graph=_latent_graph(), bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "interventional_risk_not_identifiable"


def test_a_pinned_cell_answers_even_when_the_do_risk_is_unavailable():
    """Monotonicity + consistency determine this cell on their own, so the
    unidentifiable do-risk is not an obstacle — and the provenance says so."""
    df = _sample(4_000, seed=8)
    cell = estimate_counterfactual_cell(
        df, graph=_latent_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=True, factual_y=False,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "pinned_by_monotonicity"
    assert cell.p_y_do_x_cf is None
    assert cell.point == pytest.approx(0.0)
    # This used to look for a declaration of its own saying the cell was
    # pinned by monotonicity alone. A do-risk being unavailable assumes
    # nothing about the world; what it means is that the one assumption
    # here has nothing to be checked against, so it is said on that line.
    mono = [s for s in cell.identification_assumptions
            if s["id"] == "monotonicity_non_decreasing_in_treatment"]
    assert len(mono) == 1
    assert mono[0]["testable"] is False
    assert "数据无从推翻" in mono[0]["claim"]


def test_experimental_risk_rescues_the_confounded_cell():
    df = _exact_joint_frame(3200, 800, 1800, 4200)
    cell = estimate_counterfactual_cell(
        df, graph=_latent_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     risk0=0.30),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "user_experimental"
    # k = 0.12, other cell free in [0,1]: target ∈ [(0.12-0.08)/0.32, 0.12/0.32]
    assert cell.low == pytest.approx(1.0 - 0.12 / 0.32)
    assert cell.high == pytest.approx(1.0 - (0.12 - 0.08) / 0.32)


# ================================================ what the data can refute
def test_an_experimental_risk_that_contradicts_the_joint_is_refused():
    df = _exact_joint_frame(3200, 800, 1800, 4200)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_counterfactual_cell(
            df, graph=_latent_graph(), bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                         risk0=0.05),          # below P(x=0, Y=1) = 0.18
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "counterfactual_inputs_infeasible"


def test_a_monotonicity_the_data_refute_is_reported_not_clamped():
    """With the other cell pinned at 0, the target is forced to 1.156 — outside
    [0, 1]. Clamping first would have reported a confident 1.0."""
    df = _exact_joint_frame(3200, 800, 1800, 4200)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_counterfactual_cell(
            df, graph=_latent_graph(), bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                         mono=Monotonicity.NON_DECREASING, risk0=0.55),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "counterfactual_inputs_infeasible"
    assert "monotonicity assumption is refuted" in str(exc.value)


def test_bootstrap_counts_the_draws_a_declared_monotonicity_refutes():
    """A risk sitting just inside feasibility at the point estimate puts a
    sizeable share of resamples outside it — data evidence against an
    assumption usually described as untestable."""
    df = _exact_joint_frame(3200, 800, 1800, 4200)
    cell = estimate_counterfactual_cell(
        df, graph=_latent_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING, risk0=0.4995),
        ci_bootstrap=200, random_state=1,
    )
    assert cell.bootstrap_draws_infeasible > 0
    assert cell.bootstrap_draws_used > 0
    assert cell.bootstrap_draws_used + cell.bootstrap_draws_infeasible <= 200


# ================================================================ bootstrap
def test_point_ci_brackets_the_point_and_band_brackets_the_interval():
    df = _sample(6_000, seed=9)
    g = _confounded_graph()
    point = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=200, random_state=2,
    )
    assert point.point is not None
    assert point.ci_lower <= point.point <= point.ci_upper
    assert point.ci_lower < point.ci_upper

    interval = estimate_counterfactual_cell(
        df, graph=g,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=200, random_state=2,
    )
    assert interval.point is None
    # The OUTER band is the sampling uncertainty of the whole interval.
    assert interval.ci_lower <= interval.low
    assert interval.ci_upper >= interval.high


def test_zero_bootstrap_skips_the_ci_without_affecting_the_answer():
    df = _sample(4_000, seed=10)
    g = _confounded_graph()
    q = _query(x_obs=True, x_cf=False, y_star=False, factual_y=True)
    with_ci = estimate_counterfactual_cell(df, graph=g, query=q, ci_bootstrap=20)
    without = estimate_counterfactual_cell(df, graph=g, query=q, ci_bootstrap=0)
    assert without.ci_lower is None and without.ci_upper is None
    assert without.low == with_ci.low and without.high == with_ci.high


# ============================================================ scope refusals
def test_non_binary_outcome_is_refused():
    df = _sample(2_000, seed=11)
    df["y"] = np.arange(len(df)) % 3
    with pytest.raises(EstimatorFailure):
        estimate_counterfactual_cell(
            df, graph=_confounded_graph(),
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )


def test_intervening_on_a_different_variable_than_the_one_observed_is_refused():
    df = _sample(2_000, seed=12)
    q = CounterfactualQuery(
        observed=ValuedAtom(atom=X, value=True),
        counterfactual_intervention=Intervention(atom=Z, value=False),
        counterfactual_target=ValuedAtom(atom=Y, value=False),
        factual_target_known=True,
    )
    with pytest.raises(EstimatorFailure) as exc:
        estimate_counterfactual_cell(
            df, graph=_confounded_graph(), query=q, ci_bootstrap=0,
        )
    assert exc.value.failure_type == "counterfactual_cell_cross_variable"


# ====================================== the do-risk beyond back-door: general ID
#
# A cell across worlds consumes P(Y=1 | do(x')). When no covariate set blocks
# the back-door paths, that used to end the matter — the cell was answerable
# only if a declared monotonicity pinned it outright. But "no adjustment set"
# is not "not identified": the general ID algorithm reaches estimands no set
# expresses. These cases sit on a front-door structure with an UNMEASURED X-Y
# confounder, where adjustment provably fails and ID provably succeeds.
def _frontdoor_graph():
    g = nx.DiGraph()
    g.add_edges_from([(X, M), (M, Y)])
    return g


_FRONTDOOR = (_cause("x", "m"), _cause("m", "y"))


def _sample_frontdoor(n: int, seed: int):
    """Front-door SCM with an unmeasured U confounding X and Y, MONOTONE by
    construction: every mechanism thresholds ONE uniform draw, so a higher
    input can only raise the output (Y_1 ≥ Y_0 unit by unit).

    Returns the observable frame plus the latent potential outcomes, so the
    truth oracle counts units in the generator instead of re-running the
    identity the estimator uses."""
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    e_x, e_m, e_y = rng.random(n), rng.random(n), rng.random(n)
    x = np.where(u, e_x < 0.75, e_x < 0.25)      # U confounds X …
    m_of = lambda xv: np.where(xv, e_m < 0.8, e_m < 0.25)
    y_of = lambda mv: np.where(mv, e_y < 0.9, e_y < (0.15 + 0.4 * u))  # … and Y
    m = m_of(x)
    df = pd.DataFrame({"x": x, "m": m, "y": y_of(m)})
    return df, y_of(m_of(np.zeros(n, bool))), y_of(m_of(np.ones(n, bool)))


def test_general_id_answers_a_cell_no_adjustment_set_can():
    df, _y0, _y1 = _sample_frontdoor(20_000, seed=31)
    from themis.estimation.binary_do_risk import minimal_backdoor_adjustment

    # The premise: adjustment really is unavailable on this ADMG.
    with pytest.raises(EstimatorFailure) as exc:
        minimal_backdoor_adjustment(_frontdoor_graph(), X, Y, _LATENT)
    assert exc.value.failure_type == "do_risk_not_identifiable"

    cell = estimate_counterfactual_cell(
        df, graph=_frontdoor_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "general_id_plug_in"
    assert cell.adjustment == ()                 # standardizes over nothing
    assert cell.p_y_do_x_cf is not None
    assert cell.risk_formula is not None
    assert cell.point is not None
    assert cell.form == "nonparametric_c_factor_plug_in"


def test_general_id_cell_recovers_the_counted_truth():
    """The whole chain — c-factor estimand → plug-in risk → consistency
    identity — against potential outcomes counted in the generator."""
    df, y0, _y1 = _sample_frontdoor(200_000, seed=32)
    x, y = df.x.to_numpy(), df.y.to_numpy()
    truth = (~y0[x & y]).mean()                  # PN, counted not derived
    cell = estimate_counterfactual_cell(
        df, graph=_frontdoor_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True,
                     mono=Monotonicity.NON_DECREASING),
        ci_bootstrap=0,
    )
    assert cell.point == pytest.approx(truth, abs=0.01)


def test_general_id_interval_without_monotonicity_covers_the_truth():
    df, y0, _y1 = _sample_frontdoor(60_000, seed=33)
    x, y = df.x.to_numpy(), df.y.to_numpy()
    truth = (~y0[x & y]).mean()
    cell = estimate_counterfactual_cell(
        df, graph=_frontdoor_graph(), bidirected=_LATENT,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert cell.point is None
    assert cell.low - 1e-9 <= truth <= cell.high + 1e-9
    assert cell.interventional_risk_provenance == "general_id_plug_in"


def test_back_door_is_preferred_when_an_adjustment_set_exists():
    """General ID is the fallback, not a replacement: a graph with an
    admissible set must still standardize over it."""
    cell = estimate_counterfactual_cell(
        _sample_nonmono(8_000, seed=34), graph=_confounded_graph(),
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert cell.interventional_risk_provenance == "backdoor_adjustment"
    assert cell.adjustment == ("z",)
    assert cell.risk_formula is None


def test_a_bow_arc_is_still_refused():
    """X→Y with X↔Y is not identified by ANY method; the fallback must not
    manufacture a risk where none exists."""
    df = _sample_nonmono(4_000, seed=35)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_counterfactual_cell(
            df[["x", "y"]], graph=_latent_graph(), bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "interventional_risk_not_identifiable"


def _general_id_estimated(seed=36, n=20_000, ci_bootstrap=30):
    df, _y0, _y1 = _sample_frontdoor(n, seed=seed)
    ast = _ast(_FRONTDOOR, variables=("x", "m", "y"), bidirected=_BIDIRECTED_XY,
               x_obs=True, x_cf=False, y_star=False, factual_y=True,
               assumptions={"monotonicity": "non_decreasing"})
    return ast, _result(themis.estimate(ast, df, ci_bootstrap=ci_bootstrap))


def test_general_id_cell_is_wired_end_to_end():
    ast, res = _general_id_estimated()
    validate_result(res)
    assert res["status"] == "numerically_solved"
    cell = res["numeric_estimate"]["counterfactual_cell"]
    assert cell["interventional_risk_provenance"] == "general_id_plug_in"
    assert cell["adjustment"] == []
    assert res["numeric_result"]["value"] == pytest.approx(cell["point"])


def test_verify_accepts_the_general_id_cell():
    ast, res = _general_id_estimated()
    themis.verify(ast, res)


def test_verify_rejects_general_id_claimed_where_a_back_door_set_exists():
    """The provenance asserts adjustment was unavailable. On a graph where it
    IS available that assertion is false, whatever number came out."""
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["interventional_risk_provenance"] = "general_id_plug_in"
    step["adjustment"] = ""
    bad["extensions"]["counterfactual_cell"][
        "interventional_risk_provenance"] = "general_id_plug_in"
    with pytest.raises(VerificationError, match="no covariate set"):
        themis.verify(ast, bad)


def _flip_arm_literal(node):
    """Flip every bare boolean bound to ``x`` inside a serialized formula —
    turning the recorded estimand into the OTHER arm's."""
    if isinstance(node, list):
        return [_flip_arm_literal(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _flip_arm_literal(v) for k, v in node.items()}
    if (
        out.get("kind") == "valued_atom"
        and (out.get("atom") or {}).get("predicate") == "x"
        and isinstance(out.get("value"), bool)
    ):
        out["value"] = not out["value"]
    return out


def test_verify_rejects_the_other_arms_estimand():
    """The recorded estimand is re-derived for the arm ``ctx.query`` asks
    about, so evaluating do(X=1) and reporting it as the do(X=0) cell fails —
    even though the formula is a perfectly valid identified estimand."""
    ast, res = _general_id_estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    flipped = _flip_arm_literal(step["risk_formula"])
    assert flipped != step["risk_formula"]        # the tamper really landed
    step["risk_formula"] = flipped
    with pytest.raises(VerificationError, match="not the one the verifier derives"):
        themis.verify(ast, bad)


def test_verify_rejects_an_unrecorded_estimand():
    ast, res = _general_id_estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"]["risk_formula"] = None
    with pytest.raises(VerificationError, match="must record the estimand"):
        themis.verify(ast, bad)


# ============================================================ pipeline wiring
def test_schema_accepts_the_counterfactual_cell_numeric_result():
    df = _sample_nonmono(8_000, seed=13)
    res = _result(themis.estimate(
        _ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False, factual_y=True),
        df, ci_bootstrap=50,
    ))
    validate_result(res)


def test_interval_answer_is_wired_end_to_end():
    df = _sample_nonmono(8_000, seed=14)
    res = _result(themis.estimate(
        _ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False, factual_y=True),
        df, ci_bootstrap=50,
    ))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert ne["method"] == "counterfactual_cell_plugin"
    cell = ne["counterfactual_cell"]
    assert cell["point"] is None
    assert cell["interventional_risk_provenance"] == "backdoor_adjustment"
    assert cell["adjustment"] == ["z"]
    assert res["numeric_result"]["value"] is None
    assert res["numeric_result"]["interval"]["low"] == pytest.approx(cell["lower"])
    assert res["data_gap_report"]["answer_tier"] == "interval"
    assert "point" not in ne
    themis.verify(_ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False,
                       factual_y=True), res)


def test_point_answer_is_wired_end_to_end():
    df = _sample(8_000, seed=15)
    ast = _ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False,
               factual_y=True, assumptions={"monotonicity": "non_decreasing"})
    res = _result(themis.estimate(ast, df, ci_bootstrap=50))
    ne = res["numeric_estimate"]
    assert ne["point"] == pytest.approx(ne["counterfactual_cell"]["point"])
    assert res["numeric_result"]["value"] == pytest.approx(ne["point"])
    assert res["data_gap_report"]["answer_tier"] == "point"
    themis.verify(ast, res)


def test_the_data_answer_replaces_the_theta_answer_in_every_surface():
    """run() answers from theta; estimate() must leave no surface still
    showing the theta number while another shows the data one."""
    df = _sample(8_000, seed=16)
    ast = _ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False,
               factual_y=True, assumptions={"monotonicity": "non_decreasing"})
    res = _result(themis.estimate(ast, df, ci_bootstrap=0))
    cell = res["extensions"]["counterfactual_cell"]
    assert cell["point"] == pytest.approx(res["numeric_result"]["value"])
    assert cell["point"] == pytest.approx(
        res["numeric_estimate"]["counterfactual_cell"]["point"]
    )


def test_a_refusal_leaves_the_structural_answer_untouched():
    """No adjustment set and no experimental risk: the estimator declines and
    the theta-side result must survive unmodified."""
    df = _sample_nonmono(4_000, seed=17)
    ast = _ast((_cause("x", "y"),), variables=("x", "y"),
               bidirected=_BIDIRECTED_XY,
               x_obs=True, x_cf=False, y_star=False, factual_y=True)
    res = _result(themis.estimate(ast, df, ci_bootstrap=0))
    assert "numeric_estimate" not in res
    assert res["status"] != "numerically_solved"


# ================================================================== verifier
def _estimated(seed=21, n=8_000, **qkw):
    df = _sample_nonmono(n, seed=seed)
    ast = _ast(_CONFOUNDED, x_obs=True, x_cf=False, y_star=False,
               factual_y=True, **qkw)
    return ast, _result(themis.estimate(ast, df, ci_bootstrap=30))


def test_verify_accepts_the_honest_estimate():
    ast, res = _estimated()
    themis.verify(ast, res)


def test_verify_rejects_a_tampered_interval():
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["lower"] = float(step["lower"]) - 0.2
    bad["numeric_result"]["interval"]["low"] = step["lower"]
    bad["extensions"]["counterfactual_cell"]["lower"] = step["lower"]
    bad["numeric_estimate"]["counterfactual_cell"]["lower"] = step["lower"]
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_a_tampered_interventional_risk():
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["p_y_do_x_cf"] = float(step["p_y_do_x_cf"]) + 0.05
    bad["extensions"]["counterfactual_cell"]["p_y_do_x_cf"] = step["p_y_do_x_cf"]
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_a_false_claim_that_no_risk_was_needed():
    """Dropping the risk and calling it 'not_required' would make the
    provenance self-certifying; the verifier re-derives the claim."""
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["p_y_do_x_cf"] = None
    step["interventional_risk_provenance"] = "not_required"
    step["adjustment"] = ""
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_a_false_monotonicity_pin_claim():
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["p_y_do_x_cf"] = None
    step["interventional_risk_provenance"] = "pinned_by_monotonicity"
    step["adjustment"] = ""
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_an_inadmissible_adjustment_set():
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"]["adjustment"] = "y"
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_a_point_claimed_on_a_non_collapsing_interval():
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"]["point"] = 0.5
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)


def test_verify_rejects_a_tampered_display_copy():
    """The display copy carries numbers a reader sees only there, so it must
    not be able to diverge from the audited derivation on its own."""
    ast, res = _estimated()
    bad = copy.deepcopy(res)
    bad["extensions"]["counterfactual_cell"]["upper"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(ast, bad)
