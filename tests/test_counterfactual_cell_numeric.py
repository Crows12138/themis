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
from themis.estimation.bounds_numeric import evaluate_balke_pearl_bounds
from themis.estimation.causation import estimate_causation_probabilities
from themis.estimation.counterfactual_cell import estimate_counterfactual_cell
from themis.output.assumption_glossary import classify_assumption
from themis import refusals
from themis.refusals import EstimatorFailure
from themis.runtime import counterfactual as cf
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


def test_the_two_doors_take_the_same_route_on_every_graph():
    """The invariant behind the three numeric agreements, stated directly.

    PN through the counterfactual door and PN through the causation door are
    the same number, so which route each door can reach must not depend on
    which door was knocked on. That held while both doors had the same
    cascade; it stopped holding the moment one of them grew a route, and
    nothing said so, because from inside either file its own cascade reads
    complete. Comparing them on examples catches it only where an example
    happens to exist — comparing the LICENCE over the graphs that select each
    route is the statement itself.
    """
    routes = {}
    for name, graph, bidirected, df in (
        ("backdoor", _confounded_graph(), frozenset(),
         _sample_nonmono(4_000, seed=3)),
        ("bow+instrument", _bow_iv_graph(), _LATENT,
         _sample_bow_iv(4_000, seed=7)[0]),
        ("front-door", _front_door_graph(), _LATENT,
         _front_door_sample(4_000, seed=3)),
    ):
        poc = estimate_causation_probabilities(
            df, graph=graph, bidirected=bidirected, cause=X, effect=Y,
            monotonic=False, ci_bootstrap=0,
        )
        cell = estimate_counterfactual_cell(
            df, graph=graph, bidirected=bidirected,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )
        routes[name] = (
            poc.interventional_risk_provenance,
            cell.interventional_risk_provenance,
        )
    assert routes == {
        "backdoor": ("backdoor_adjustment", "backdoor_adjustment"),
        "bow+instrument": ("instrument_response_polytope",
                           "instrument_response_polytope"),
        "front-door": ("general_id_plug_in", "general_id_plug_in"),
    }


def test_pn_matches_the_causation_door_over_the_instrument_polytope():
    """The registered asymmetry, as a behaviour: this door answered and the
    other refused, on the same PN and the same DataFrame."""
    df, y0, _y1 = _sample_bow_iv(20_000, seed=7)
    poc = estimate_causation_probabilities(
        df, graph=_bow_iv_graph(), bidirected=_LATENT, cause=X, effect=Y,
        monotonic=False, ci_bootstrap=0,
    )
    cell = _iv_cell(df, graph=_bow_iv_graph())
    assert poc.pn_lower == pytest.approx(cell.low, abs=1e-12)
    assert poc.pn_upper == pytest.approx(cell.high, abs=1e-12)
    assert poc.p_y_do_x1 is None and poc.p_y_do_x0 is None
    assert poc.instrument == "z"
    assert poc.pn_lower <= _true_pn(df, y0) <= poc.pn_upper


def test_pn_matches_the_causation_door_over_a_general_id_estimand():
    """The other route the shared cascade brought with it. A front-door
    structure point-identifies both arms where no covariate set does."""
    df = _front_door_sample(20_000, seed=3)
    g, bi = _front_door_graph(), _LATENT
    poc = estimate_causation_probabilities(
        df, graph=g, bidirected=bi, cause=X, effect=Y,
        monotonic=False, ci_bootstrap=0,
    )
    cell = estimate_counterfactual_cell(
        df, graph=g, bidirected=bi,
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert poc.pn_lower == pytest.approx(cell.low, abs=1e-12)
    assert poc.pn_upper == pytest.approx(cell.high, abs=1e-12)
    # The cell needs the ONE arm it crosses to; the three quantities need both.
    # Sharing a cascade must not have made either ask for the other's data.
    assert poc.p_y_do_x0 == pytest.approx(cell.p_y_do_x_cf, abs=1e-12)
    assert poc.p_y_do_x1 is not None


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
    mono = [a for a in cell.assumptions if a.startswith("monotonicity_")]
    assert mono == ["monotonicity_assumed_non_decreasing_in_treatment"]
    entry = classify_assumption(mono[0])
    assert entry["testable"] is False
    assert "没有可以反驳它的东西" in entry["claim"]


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


def test_the_cell_says_which_kind_its_band_is_and_the_verifier_checks_it():
    """#419: one pair of keys, two objects, and the run settles which.

    ``ci_lower`` / ``ci_upper`` on this cell is the point's bootstrap
    interval when the identified set collapsed and a conservative band on
    ``[lower, upper]`` when it did not. The two are indistinguishable in
    the numbers and narrow with different things, so the estimator — the
    only thing that saw which came out — states it, and the verifier
    re-derives it rather than taking the word.
    """
    ast, res = _estimated()
    step = [s for s in res["derivation"]["steps"]
            if s["rule"] == "numeric_counterfactual_cell_estimate"]
    assert len(step) == 1, [s["rule"] for s in res["derivation"]["steps"]]
    assert step[0]["inputs"]["ci_width_is"] == "outer_band"
    assert (res["numeric_estimate"]["counterfactual_cell"]["ci_width_is"]
            == "outer_band")
    themis.verify(ast, res)

    for wrong in ("sampling", None):
        bad = copy.deepcopy(res)
        for s in bad["derivation"]["steps"]:
            if s["rule"] == "numeric_counterfactual_cell_estimate":
                if wrong is None:
                    s["inputs"].pop("ci_width_is")
                else:
                    s["inputs"]["ci_width_is"] = wrong
        with pytest.raises(VerificationError, match="ci_width_is"):
            themis.verify(ast, bad)


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


# ============================================ the instrument route (#322)
#
# The cascade above stops when no do-risk is POINT-identified. An instrument
# does not hand over the risk as a number, but it does pin down the set of
# models the data admit, and the cell is a linear functional on that set — so
# the same query that used to get nothing gets an interval, from a different
# solver, under different assumptions. Balke & Pearl 1994 (UAI) is the method;
# what these pin is that Themis takes the sharp route rather than the one that
# reduces the instrument to a scalar first, and that it says which route ran.

_BOW_IV = (_cause("z", "x"), _cause("x", "y"))


def _bow_iv_graph():
    """Z → X → Y with an unmeasured common cause of X and Y.

    The do-risk is not identified from this graph by any covariate set, and ID
    returns a hedge; the instrument is the only thing left that says anything.
    """
    g = nx.DiGraph()
    g.add_edges_from([(Z, X), (X, Y)])
    return g


def _sample_bow_iv(n: int, seed: int):
    """Rank-preserving SCM behind a bow arc, driven by an instrument.

    The latent ``w`` moves both the treatment and the outcome, so no measured
    set blocks the back door; ``z`` moves only the treatment. Returns the
    frame the estimator sees together with the two potential outcomes it
    cannot see, so a test can count units instead of re-deriving a theorem.
    """
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.5
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0 = u < np.where(w, 0.55, 0.15)
    y1 = u < np.where(w, 0.90, 0.45)
    x = rng.random(n) < np.where(z, np.where(w, 0.85, 0.55),
                                 np.where(w, 0.35, 0.10))
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z}), y0, y1


def _front_door_graph():
    """X → M → Y with an unmeasured common cause of X and Y.

    No covariate set blocks the back door, and unlike the bow above the ID
    algorithm reaches BOTH arms through the mediator — so this graph selects
    the general-ID route rather than the instrument one.
    """
    g = nx.DiGraph()
    g.add_edges_from([(X, M), (M, Y)])
    return g


def _front_door_sample(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.5                       # unmeasured, moves x and y
    x = rng.random(n) < np.where(w, 0.8, 0.3)
    m = rng.random(n) < np.where(x, 0.75, 0.2)
    y = rng.random(n) < np.where(m, 0.8, 0.25) * np.where(w, 1.0, 0.7)
    return pd.DataFrame({"x": x, "y": y, "m": m})


def _true_pn(df, y0):
    sel = df["x"].to_numpy() & df["y"].to_numpy()
    return float((~y0[sel]).mean())


def _iv_cell(df, *, mono=None, graph=None, bidirected=_LATENT, **qkw):
    kw = dict(x_obs=True, x_cf=False, y_star=False, factual_y=True)
    kw.update(qkw)
    return estimate_counterfactual_cell(
        df, graph=graph if graph is not None else _bow_iv_graph(),
        bidirected=bidirected,
        query=_query(mono=mono, **kw), ci_bootstrap=0,
    )


def test_a_bow_arc_with_an_instrument_is_answered_instead_of_refused():
    """The registered gap, as a behaviour: this cell used to have no number.

    The route is named on the answer, no interventional risk is reported
    beside it (there is none to report), and the interval covers the SCM's
    own PN — counted off the potential outcomes, not re-derived.
    """
    df, y0, _y1 = _sample_bow_iv(40_000, seed=7)
    est = _iv_cell(df)
    assert est.interventional_risk_provenance == "instrument_response_polytope"
    assert est.instrument == "z"
    assert est.p_y_do_x_cf is None
    assert est.point is None
    assert est.low <= _true_pn(df, y0) <= est.high
    assert est.high - est.low < 1.0     # it says something


def test_the_cell_is_bounded_sharply_rather_than_through_the_arm_interval():
    """Sharpness, against the honest alternative rather than against nothing.

    Bounding the ARM with Balke-Pearl and then running the consistency
    identity at both ends of that interval is valid — and weaker, because the
    identity takes the risk as a scalar and a scalar cannot carry that one
    distribution has to produce both the risk and the cell. Both are shipped
    APIs here, so the comparison is between two things Themis can actually do.
    """
    df, _y0, _y1 = _sample_bow_iv(40_000, seed=7)
    arm = evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z",
        treatment_value=False, outcome_value=True, ci_bootstrap=0,
    )
    query = _query(x_obs=True, x_cf=False, y_star=False, factual_y=True)
    twin = cf.project_twin_network(_bow_iv_graph(), _LATENT, query)
    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    joint = {
        (xv, yv): float(((x == xv) & (y == yv)).mean())
        for xv in (True, False) for yv in (True, False)
    }
    two_step = [
        cf.counterfactual_cell_interval(twin, query, joint, p_y_do_x_cf=r)
        for r in (arm.lower_value, arm.upper_value)
    ]
    lo = min(i.low for i in two_step)
    hi = max(i.high for i in two_step)

    est = _iv_cell(df)
    assert lo - 1e-9 <= est.low and est.high <= hi + 1e-9
    assert est.high - est.low < (hi - lo) - 1e-6


def test_a_declared_monotonicity_narrows_the_polytope():
    """It is a constraint on this route too, not an assumption it ignores."""
    df, y0, _y1 = _sample_bow_iv(40_000, seed=7)
    free = _iv_cell(df)
    pinned = _iv_cell(df, mono=Monotonicity.NON_DECREASING)
    assert free.low <= pinned.low and pinned.high <= free.high
    assert pinned.high - pinned.low < free.high - free.low
    assert pinned.low <= _true_pn(df, y0) <= pinned.high
    assert pinned.monotonicity == "non_decreasing"


def test_the_polytope_refutes_a_monotonicity_the_data_contradict():
    """The gate this route earns: the pin route cannot be refuted at all.

    ``_sample_bow_iv`` is rank-preserving, so no unit's outcome moves against
    the treatment. Declaring the OPPOSITE direction empties the type space,
    and the refusal says the assumption is what failed rather than the
    instrument — which the caller can act on and 'infeasible' cannot.
    """
    df, _y0, _y1 = _sample_bow_iv(40_000, seed=7)
    with pytest.raises(EstimatorFailure) as excinfo:
        _iv_cell(df, mono=Monotonicity.NON_INCREASING)
    assert excinfo.value.failure_type == "counterfactual_inputs_infeasible"
    # Which language, said out loud — see the twin of this test in
    # tests/test_causation_numeric_wiring.py.
    assert "monotonicity" in refusals.sentence(
        excinfo.value.failure_type, excinfo.value.details, "en")


def test_the_monotonicity_this_route_carries_is_marked_testable():
    """It was read off "was a risk an input", which is a different question.

    The polytope consumes no risk and can still empty out, so the ledger line
    that says the data cannot refute this assumption would be false here.
    """
    df, _y0, _y1 = _sample_bow_iv(20_000, seed=7)
    est = _iv_cell(df, mono=Monotonicity.NON_DECREASING)
    mono = [a for a in est.assumptions if a.startswith("monotonicity_")]
    assert mono == ["monotonicity_refutable_non_decreasing_in_treatment"]
    entry = classify_assumption(mono[0])
    assert entry["testable"] is True
    assert "没有可以反驳它的东西" not in entry["claim"]


def test_the_ett_cell_is_bounded_too_when_no_factual_outcome_is_given():
    """Without the factual outcome the identity point-identifies from a risk;
    with no risk to be had, the same cell is an interval over the polytope."""
    df, y0, _y1 = _sample_bow_iv(40_000, seed=7)
    est = _iv_cell(df, factual_y=None)
    truth = float((~y0[df["x"].to_numpy()]).mean())
    assert est.instrument == "z"
    assert est.low <= truth <= est.high


def test_a_point_identified_do_risk_still_wins_over_the_instrument():
    """The cascade's order is not arbitrary: a point beats an interval.

    This graph carries BOTH a measured confounder and an instrument, so a
    route chosen by availability rather than by strength would answer a
    perfectly identified cell with bounds.
    """
    df = _sample_nonmono(20_000, seed=21)
    g = nx.DiGraph()
    g.add_edges_from([(Z, X), (Z, Y), (X, Y)])
    est = estimate_counterfactual_cell(
        df, graph=g, bidirected=frozenset(),
        query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
        ci_bootstrap=0,
    )
    assert est.interventional_risk_provenance == "backdoor_adjustment"
    assert est.instrument is None


def test_a_candidate_with_a_path_to_the_outcome_is_not_an_instrument():
    """Exclusion is checked on the graph, not assumed of anything upstream."""
    df, _y0, _y1 = _sample_bow_iv(20_000, seed=7)
    leaky = nx.DiGraph()
    leaky.add_edges_from([(Z, X), (Z, Y), (X, Y)])
    with pytest.raises(EstimatorFailure) as excinfo:
        estimate_counterfactual_cell(
            df, graph=leaky, bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )
    assert excinfo.value.failure_type == "interventional_risk_not_identifiable"


def test_two_valid_instruments_are_not_silently_narrowed_to_one():
    """Several instruments carry more than any one of them.

    Answering from one would be a claim about a smaller model than the graph
    describes, and nothing on the answer would say so.
    """
    df, _y0, _y1 = _sample_bow_iv(20_000, seed=7)
    df = df.assign(z2=df["z"].to_numpy()[::-1])
    two = nx.DiGraph()
    two.add_edges_from([(Z, X), (Atom(predicate="z2", args=()), X), (X, Y)])
    with pytest.raises(EstimatorFailure) as excinfo:
        estimate_counterfactual_cell(
            df, graph=two, bidirected=_LATENT,
            query=_query(x_obs=True, x_cf=False, y_star=False, factual_y=True),
            ci_bootstrap=0,
        )
    assert excinfo.value.failure_type == "interventional_risk_not_identifiable"


def test_an_instrument_too_wide_to_solve_says_so_instead_of_falling_back():
    """The cap is not silent. The LP is re-solved once per bootstrap draw, so
    the size is a real limit — and a caller told nothing would read the
    weaker route it fell back to as the best available."""
    df, _y0, _y1 = _sample_bow_iv(4_000, seed=7)
    rng = np.random.default_rng(0)
    df = df.assign(z=rng.integers(0, 40, size=len(df)))
    with pytest.raises(EstimatorFailure) as excinfo:
        _iv_cell(df)
    assert excinfo.value.failure_type == "response_model_too_large"
    assert "40" in str(excinfo.value)


# ---------------------------------------------------------------- wiring
def _iv_estimated(seed=7, n=40_000, ci_bootstrap=20, **qkw):
    df, _y0, _y1 = _sample_bow_iv(n, seed=seed)
    kw = dict(x_obs=True, x_cf=False, y_star=False, factual_y=True)
    kw.update(qkw)
    ast = _ast(_BOW_IV, bidirected=_BIDIRECTED_XY, **kw)
    return ast, _result(themis.estimate(ast, df, ci_bootstrap=ci_bootstrap))


def test_the_instrument_route_is_wired_end_to_end():
    ast, res = _iv_estimated()
    validate_result(res)
    assert res["status"] == "numerically_solved"
    cell = res["numeric_estimate"]["counterfactual_cell"]
    assert cell["interventional_risk_provenance"] == "instrument_response_polytope"
    assert cell["instrument"] == "z"
    assert cell["p_y_do_x_cf"] is None
    assert cell["adjustment"] == []
    assert res["numeric_result"]["interval"]["low"] == pytest.approx(cell["lower"])
    assert res["data_gap_report"]["answer_tier"] == "interval"


def test_the_report_names_the_column_the_interval_leaned_on():
    """A reader told "a response-function polytope" and not which variable
    carried it cannot go and check the assumption."""
    ast, res = _iv_estimated(ci_bootstrap=0)
    report = themis.build_analysis_report(res, program=ast)
    assert "工具变量 `z`" in report
    # And the reason it is an interval is the route, not a missing
    # monotonicity — the report used to assert the latter unconditionally.
    assert "无单调性假设，故为界而非点" not in report


def test_verify_accepts_the_instrument_route():
    ast, res = _iv_estimated()
    themis.verify(ast, res)


def test_verify_rejects_a_tampered_instrument_interval():
    ast, res = _iv_estimated()
    bad = copy.deepcopy(res)
    step = bad["derivation"]["steps"][0]["inputs"]
    step["lower"] = float(step["lower"]) + 0.2
    bad["numeric_result"]["interval"]["low"] = step["lower"]
    bad["extensions"]["counterfactual_cell"]["lower"] = step["lower"]
    bad["numeric_estimate"]["counterfactual_cell"]["lower"] = step["lower"]
    with pytest.raises(VerificationError, match="re-solved cell value"):
        themis.verify(ast, bad)


def test_verify_rejects_a_column_that_is_not_this_graphs_instrument():
    """The arithmetic is right for whichever column was fed in, so the column
    itself is what has to be re-derived from the graph."""
    ast, res = _iv_estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"]["instrument"] = "y"
    with pytest.raises(VerificationError, match="not the instrument"):
        themis.verify(ast, bad)


def test_verify_rejects_a_table_that_contradicts_the_reported_joint():
    """The two halves of the envelope have to agree with each other: a forged
    interval now needs a forged table that still marginalises to the four
    cells the identity route is audited on."""
    ast, res = _iv_estimated()
    bad = copy.deepcopy(res)
    table = bad["derivation"]["steps"][0]["inputs"]["p_xyz"]
    row = table["items"][0]["items"][0]["items"]
    row[0] += 0.05
    row[1] -= 0.05
    with pytest.raises(VerificationError, match="marginalises"):
        themis.verify(ast, bad)


def test_verify_rejects_an_interval_that_dropped_the_declared_monotonicity():
    """The assumption is read off the query, so a producer cannot report the
    wider unrestricted interval while the caller's declaration says the type
    space was smaller."""
    ast, res = _iv_estimated(
        assumptions={"monotonicity": "non_decreasing"})
    free = _iv_cell(_sample_bow_iv(40_000, seed=7)[0])
    bad = copy.deepcopy(res)
    for holder in (
        bad["derivation"]["steps"][0]["inputs"],
        bad["extensions"]["counterfactual_cell"],
        bad["numeric_estimate"]["counterfactual_cell"],
    ):
        holder["lower"], holder["upper"] = free.low, free.high
    bad["numeric_result"]["interval"] = {"low": free.low, "high": free.high}
    with pytest.raises(VerificationError, match="re-solved cell value"):
        themis.verify(ast, bad)
