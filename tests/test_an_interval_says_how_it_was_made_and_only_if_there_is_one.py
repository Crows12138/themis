"""#603 — an interval's account of itself, read from the loop and not the call.

A confidence-layer sentence — "obtained by percentile bootstrap", "by
resampling whole clusters on fam", "from the efficient influence curve",
"this interval is not cluster-robust" — is a claim ABOUT AN INTERVAL. It was
being derived from the call instead. At thirty-seven of the forty-four places
one is decided the gate was ``cluster is not None``, a fact settled before any
loop runs; four more read ``ci_method``, which names a road rather than a
journey; three were unconditional. None of the forty-four asked whether an
interval came out.

Wrong in both directions at once, and the two halves hide each other:

- A run given a cluster column and ``ci_bootstrap=0`` declared "the interval
  was obtained by resampling whole clusters" beside an answer with no
  interval in it.
- A run that DID resample, with no cluster column, reported an interval and
  said nothing at all about how it was made — nothing named the column, so
  nothing fired, and the silence read as an analytic width.

The repair is a witness rather than a rule: ``Draws.declares`` speaks for the
loop that ran, ``influence_interval_declares`` for the analytic width, and
each family calls one of them instead of writing the sentence itself. The
routes with neither — a Greenwood interval, a SIMEX ladder, a dose-response
curve — ask their own endpoints.

Pinned here at every level the invariant can be read: the witnesses, the
estimators on both sides, the source, and one real run.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd
import pytest

from themis import kernel
from themis.estimation.aipw import estimate_aipw_ate, influence_interval_declares
from themis.estimation.backdoor import estimate_backdoor_ate
from themis.estimation.dose_response import (
    CurvePoint,
    _an_estimated_interval_is_on_the_curve,
)
from themis.estimation.iv import estimate_iv_vector
from themis.estimation.mediation import estimate_mediation
from themis.estimation.resample import FEWEST_DRAWS, Draws, declared_by
from themis.estimation.simex import estimate_simex
from themis.estimation.survival import restricted_mean_survival

#: Every id that is a claim about an interval rather than about the world.
#: An answer with no interval may carry none of them.
ABOUT_AN_INTERVAL = (
    "ci_via_",
    "ci_not_cluster_robust_",
    "cluster_robust_influence_variance_on_",
    "simex_interval_covers_",
)

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "themis" / "estimation"


def _about_an_interval(assumptions) -> list[str]:
    return [str(a) for a in assumptions or ()
            if str(a).startswith(ABOUT_AN_INTERVAL)]


# ============================================ the witnesses


def test_a_loop_that_never_ran_says_nothing_about_an_interval():
    """``draws is None`` is how every family spells "no interval was asked
    for", so it is the one place the absent loop needs answering."""
    assert declared_by(None, cluster=None) == ()
    assert declared_by(None, cluster="fam") == ()


def test_a_loop_that_kept_too_few_draws_says_nothing_either():
    """The loop ran. What it produced is not an interval this package will
    report, and a sentence describing how it was made would be about
    endpoints nobody was shown."""
    draws = Draws(10)
    for _ in draws:
        draws.usable()
        break
    assert draws.used < FEWEST_DRAWS
    assert draws.declares(cluster="fam") == ()


def test_a_bootstrap_with_no_cluster_column_still_says_it_was_a_bootstrap():
    """The half that used to be silent: nothing named a column, so nothing
    fired, and an interval arrived with no account of its own origin."""
    draws = Draws(4)
    for _ in draws:
        draws.usable()
    assert draws.declares(cluster=None) == ("ci_via_percentile_bootstrap",)


def test_the_cluster_id_refines_the_bootstrap_rather_than_replacing_it():
    """An interval from whole-cluster resampling IS a percentile bootstrap.
    Saying only the second leaves a reader who filters on the first unable
    to see it at all."""
    draws = Draws(4)
    for _ in draws:
        draws.usable()
    assert draws.declares(cluster="fam") == (
        "ci_via_percentile_bootstrap",
        "ci_via_pairs_cluster_bootstrap_on_fam",
    )


def test_an_analytic_width_that_was_not_reported_says_nothing():
    """``ci_method`` names the road. A run asked for no interval takes that
    road nowhere, which is why the road cannot be the predicate."""
    assert influence_interval_declares(reported=False, cluster=None) == ()
    assert influence_interval_declares(reported=False, cluster="fam") == ()


def test_an_analytic_width_that_was_reported_says_which_curve_and_which_unit():
    assert influence_interval_declares(reported=True, cluster=None) == (
        "ci_via_analytic_influence_function",)
    assert influence_interval_declares(reported=True, cluster="fam") == (
        "ci_via_analytic_influence_function",
        "cluster_robust_influence_variance_on_fam",
    )


# ============================================ the bootstrap families


def _clustered(rng, *, G=40, per=10, ate=2.0) -> pd.DataFrame:
    """Cluster-level treatment and a shared family effect on a continuous Y."""
    fam = np.repeat(np.arange(G), per)
    a_by = rng.integers(0, 2, G)
    a = a_by[fam].astype(float)
    u = rng.standard_normal(G) * 2.0
    m = (rng.random(G * per) < np.where(a == 1, 0.7, 0.3)).astype(float)
    y = ate * a + 1.0 * m + u[fam] + rng.standard_normal(G * per) * 0.5
    z = rng.standard_normal(G * per)
    return pd.DataFrame({"A": a, "M": m, "Y": y, "Z": z, "fam": fam})


def _backdoor(df, **kw):
    return estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                 random_state=1, **kw)


def _mediation(df, **kw):
    return estimate_mediation(df, treatment="A", outcome="Y", mediator="M",
                              random_state=1, **kw)


def _aipw_bootstrap(df, **kw):
    return estimate_aipw_ate(df, treatment="A", outcome="Y",
                             adjustment=("Z",), ci_method="bootstrap",
                             random_state=1, **kw)


BOOTSTRAP_FAMILIES = {
    "backdoor": _backdoor,
    "mediation": _mediation,
    "aipw": _aipw_bootstrap,
}


@pytest.mark.parametrize("name", sorted(BOOTSTRAP_FAMILIES))
def test_a_run_asked_for_no_interval_declares_no_interval(name):
    """The counterexample the old gate got wrong: a cluster column is named,
    no loop runs, and the answer used to claim whole clusters were
    resampled."""
    df = _clustered(np.random.default_rng(0))
    est = BOOTSTRAP_FAMILIES[name](df, ci_bootstrap=0, cluster="fam")
    assert _about_an_interval(est.assumptions) == []


@pytest.mark.parametrize("name", sorted(BOOTSTRAP_FAMILIES))
def test_an_unclustered_bootstrap_still_says_how_it_was_made(name):
    """The mirror counterexample: an interval exists, no column names it,
    and the answer used to say nothing at all."""
    df = _clustered(np.random.default_rng(0))
    est = BOOTSTRAP_FAMILIES[name](df, ci_bootstrap=30)
    assert _about_an_interval(est.assumptions) == ["ci_via_percentile_bootstrap"]


@pytest.mark.parametrize("name", sorted(BOOTSTRAP_FAMILIES))
def test_a_clustered_bootstrap_says_both(name):
    df = _clustered(np.random.default_rng(0))
    est = BOOTSTRAP_FAMILIES[name](df, ci_bootstrap=30, cluster="fam")
    assert _about_an_interval(est.assumptions) == [
        "ci_via_percentile_bootstrap",
        "ci_via_pairs_cluster_bootstrap_on_fam",
    ]


# ============================================ the analytic routes


def test_an_influence_interval_asked_for_and_not_asked_for():
    """``ci_method='influence_function'`` is unchanged by ``ci_bootstrap``
    except in one respect — zero means no interval — which is exactly the
    thing the road name could not tell anyone."""
    df = _clustered(np.random.default_rng(1))
    silent = estimate_aipw_ate(df, treatment="A", outcome="Y",
                               adjustment=("Z",), ci_bootstrap=0,
                               cluster="fam", random_state=1)
    assert silent.ci_lower is None
    assert _about_an_interval(silent.assumptions) == []

    spoken_ = estimate_aipw_ate(df, treatment="A", outcome="Y",
                                adjustment=("Z",), cluster="fam",
                                random_state=1)
    assert spoken_.ci_lower is not None
    assert _about_an_interval(spoken_.assumptions) == [
        "ci_via_analytic_influence_function",
        "cluster_robust_influence_variance_on_fam",
    ]


def _survival_frame(n=4000, seed=11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fam = np.repeat(np.arange(n // 10), 10)
    x = rng.integers(0, 2, n)
    rate = np.where(x == 1, 0.25, 0.5)
    survival = rng.exponential(1.0 / rate)
    stop = rng.exponential(1.0 / 0.4, n)
    return pd.DataFrame({"x": x, "t": np.minimum(survival, stop),
                         "seen": (survival <= stop).astype(float),
                         "fam": fam})


def test_a_greenwood_interval_discloses_the_column_it_could_not_honour():
    """This route cannot cluster and takes the column anyway, to say so."""
    est = restricted_mean_survival(
        _survival_frame(), treatment="x", outcome="t",
        event_indicator="seen", horizon=2.0, cluster="fam")
    assert est.ci_lower is not None
    assert _about_an_interval(est.assumptions) == [
        "ci_not_cluster_robust_analytic_interval_ignores_fam"]


def test_a_greenwood_run_with_no_endpoints_discloses_nothing():
    """A level outside the quantile table leaves ``lower``/``upper`` unset.
    The column is still named and the route still cannot honour it — and
    there is no width for either fact to be about."""
    est = restricted_mean_survival(
        _survival_frame(), treatment="x", outcome="t",
        event_indicator="seen", horizon=2.0, cluster="fam", ci_level=0.80)
    assert est.ci_lower is None and est.ci_upper is None
    assert _about_an_interval(est.assumptions) == []


def _simex_frame(n=2000, seed=0, sigma2_u=0.25) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + 0.8 * x + 0.4 * z + rng.normal(0, 1.0, n)
    return pd.DataFrame({"w": x + rng.normal(0, np.sqrt(sigma2_u), n),
                         "y": y, "z": z,
                         "fam": np.repeat(np.arange(n // 10), 10)})


def _simex(**kw):
    return estimate_simex(_simex_frame(), treatment="w", outcome="y",
                          adjustment=("z",), error_variance=0.25,
                          outcome_model="linear", n_replicates=30,
                          random_state=3, **kw)


def test_a_simex_interval_carries_what_it_does_not_cover():
    """The ladder's width covers sampling error and not the extrapolation
    itself, which is a caveat and not an assumption about the world."""
    est = _simex()
    assert est.ci_lower is not None
    assert _about_an_interval(est.assumptions) == [
        "simex_interval_covers_sampling_not_extrapolation_error"]


def test_a_simex_run_that_ships_no_interval_carries_no_caveat_about_one():
    """A cluster column takes this route's interval away — every variance on
    the ladder is a model-based one — and the caveat used to be printed
    anyway, unconditionally, beside a point with no endpoints."""
    est = _simex(cluster="fam")
    assert est.ci_lower is None and est.no_interval_because is not None
    assert _about_an_interval(est.assumptions) == []


def test_a_curve_with_no_fitted_endpoints_is_not_a_curve_with_an_interval():
    """The reference dose is written as zero at zero width by construction,
    so counting it would let a curve whose every interval call failed still
    read as one that produced an interval."""
    ref = CurvePoint(x=0.0, effect=0.0, ci_lower=0.0, ci_upper=0.0)
    blind = CurvePoint(x=1.0, effect=0.4, ci_lower=None, ci_upper=None)
    seeing = CurvePoint(x=1.0, effect=0.4, ci_lower=0.1, ci_upper=0.7)
    assert not _an_estimated_interval_is_on_the_curve([ref, blind],
                                                      reference=0.0)
    assert _an_estimated_interval_is_on_the_curve([ref, seeing], reference=0.0)


def _two_endogenous(n=3000, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
    u = rng.standard_normal(n)
    a = 0.9 * z1 + u + 0.5 * rng.standard_normal(n)
    b = 0.9 * z2 + u + 0.5 * rng.standard_normal(n)
    y = 1.0 * a - 0.5 * b + u + 0.3 * rng.standard_normal(n)
    return pd.DataFrame({"a": a, "b": b, "y": y, "z1": z1, "z2": z2,
                         "fam": np.repeat(np.arange(n // 10), 10)})


def test_an_anderson_rubin_region_discloses_the_column_it_ignores():
    """The region is read off an F critical value computed from i.i.d.
    second moments. ``cluster`` reached this estimator, was checked for
    presence, was carried on the answer — and was told to nobody."""
    est = estimate_iv_vector(
        _two_endogenous(), treatments=("a", "b"), outcome="y",
        instruments=("z1", "z2"), cluster="fam")
    assert _about_an_interval(est.assumptions) == [
        "ci_not_cluster_robust_analytic_interval_ignores_fam"]

    plain = estimate_iv_vector(
        _two_endogenous(), treatments=("a", "b"), outcome="y",
        instruments=("z1", "z2"))
    assert _about_an_interval(plain.assumptions) == []


# ============================================ the source gate


#: The two modules that may emit a ``ci_via_`` id, because they are the
#: witnesses the families delegate to. ``dispatch`` re-declares the cluster
#: prefix as a constant it audits stamps against — a reading rather than an
#: emission, and pinned equal to the glossary's by a test of its own.
MAY_SAY_HOW_AN_INTERVAL_WAS_MADE = {"resample.py", "aipw.py", "dispatch.py"}

WITNESSES = {"declared_by", "influence_interval_declares"}


def _witness_calls_under_a_cluster_test(tree: ast.AST) -> list[int]:
    """Witness calls sitting under an ``if`` that reads ``cluster``.

    The defect's exact shape, and the one a new family would rebuild: the
    witness answers "did the loop run", and wrapping it in the old gate puts
    the caller's argument back in front of it — silencing every unclustered
    bootstrap again while looking, at the call site, entirely correct.
    """
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        reads = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        reads |= {n.attr for n in ast.walk(node.test)
                  if isinstance(n, ast.Attribute)}
        if "cluster" not in reads:
            continue
        for stmt in (*node.body, *node.orelse):
            for inner in ast.walk(stmt):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id in WITNESSES):
                    found.append(inner.lineno)
    return found


def _emitted_ci_via(tree: ast.AST) -> list[int]:
    """Lines writing a ``ci_via_`` id as a literal of their own."""
    found: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value for v in node.values
                           if isinstance(v, ast.Constant))
        else:
            continue
        if "ci_via_" in text:
            found.append(node.lineno)
    return found


def test_no_family_puts_the_callers_argument_in_front_of_the_witness():
    complaints = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line in _witness_calls_under_a_cluster_test(tree):
            complaints.append(f"{path.name}:{line}")
    assert complaints == []


def test_only_the_witnesses_say_how_an_interval_was_made():
    """A family that writes the sentence itself has re-created the thing the
    witnesses exist to hold in one place, and the next reading of "was there
    an interval" is free to differ from theirs."""
    complaints = []
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name in MAY_SAY_HOW_AN_INTERVAL_WAS_MADE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line in _emitted_ci_via(tree):
            complaints.append(f"{path.name}:{line}")
    assert complaints == []


BAD_GATE = """
def fit(cluster=None, draws=None):
    said = ()
    if cluster is not None:
        said += declared_by(draws, cluster=cluster)
    return said
"""

GOOD_GATE = """
def fit(cluster=None, draws=None):
    said = ()
    said += declared_by(draws, cluster=cluster)
    if cluster is not None:
        said += ("some_id_about_the_world",)
    return said
"""

BAD_LITERAL = """
def fit(cluster):
    return ("ci_via_percentile_bootstrap",)
"""

GOOD_LITERAL = """
def fit(cluster, draws):
    return declared_by(draws, cluster=cluster)
"""


def test_the_source_gate_says_no_to_the_shape_it_is_about():
    """Both sides of both gates. A gate that has never refused anything is a
    gate nobody has evidence about."""
    assert _witness_calls_under_a_cluster_test(ast.parse(BAD_GATE)) != []
    assert _witness_calls_under_a_cluster_test(ast.parse(GOOD_GATE)) == []
    assert _emitted_ci_via(ast.parse(BAD_LITERAL)) != []
    assert _emitted_ci_via(ast.parse(GOOD_LITERAL)) == []


# ============================================ end to end


def _program(cluster: str | None) -> dict:
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True}, "given": []}},
        ],
    }
    if cluster is not None:
        program["options"] = {"cluster": cluster}
    return program


def _ids(node) -> list[str]:
    """Every assumption id anywhere in one envelope."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "assumptions" and isinstance(value, list):
                out += [str(v) for v in value]
            else:
                out += _ids(value)
    elif isinstance(node, list):
        for value in node:
            out += _ids(value)
    return out


def test_a_real_clustered_run_with_no_interval_says_nothing_about_one():
    """One route answers, and everything it attached is read. ``ci_bootstrap
    = 0`` is this system's way to skip the interval, so on this program no
    block of any depth has endpoints for a sentence to describe."""
    df = _clustered(np.random.default_rng(2))
    result = kernel.estimate(_program("fam"), df,
                             ci_bootstrap=0, random_state=1)["results"][0]
    assert result["numeric_estimate"]["ci_lower"] is None
    assert [i for i in _ids(result) if i.startswith(ABOUT_AN_INTERVAL)] == []


def test_a_real_clustered_run_with_an_interval_says_how_it_was_made():
    df = _clustered(np.random.default_rng(2))
    result = kernel.estimate(_program("fam"), df,
                             ci_bootstrap=40, random_state=1)["results"][0]
    estimate = result["numeric_estimate"]
    assert estimate["ci_lower"] is not None
    assert _about_an_interval(estimate["assumptions"]) == [
        "ci_via_percentile_bootstrap",
        "ci_via_pairs_cluster_bootstrap_on_fam",
    ]


def test_a_real_unclustered_run_names_its_bootstrap_too():
    """The half nobody had noticed: no column, so under the old gate no
    sentence, and the interval arrived unattributed."""
    df = _clustered(np.random.default_rng(2))
    result = kernel.estimate(_program(None), df,
                             ci_bootstrap=40, random_state=1)["results"][0]
    assert _about_an_interval(result["numeric_estimate"]["assumptions"]) == [
        "ci_via_percentile_bootstrap"]
