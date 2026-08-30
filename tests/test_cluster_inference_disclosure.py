"""The unit of independence: honoured, recorded, and auditable.

MEASURED DEFECT (2026-07-28). A full static accounting of ``dispatch`` found
22 functions that produce a numeric answer, of which 21 handed the resolved
cluster column to their estimator and one did not:
``_maybe_estimate_longitudinal``. The runtime oracle confirmed the
consequence — ``themis.estimate(prog, df, cluster="clinic")`` on a
longitudinal program returned an interval bit-for-bit identical to the i.i.d.
one (0.809918 for the g-formula, 0.917301 for IPW-MSM) and the string
``"clinic"`` appeared nowhere in the envelope. The user declared a cluster
structure; Themis dropped it without a trace and shipped an anti-conservative
interval.

Threading one more argument fixes that one estimator and leaves the DEFAULT
intact: the 23rd producer drops it just as silently. What made the drop
invisible is that the run-level fact — which column this run resolved — was
never recorded anywhere. ``numeric_estimate.bootstrap`` is a per-estimate
claim written by hand at each call site, so "nobody named a cluster column"
and "a column was named and this estimator dropped it" are the same envelope.

So the fix is in three parts, and this file pins all three:

- the g-methods honour the column (and the interval that results is the one
  that covers — the i.i.d. one does not);
- ``estimation_context.cluster`` records what the run resolved, once, before
  any branch consumes it;
- a verifier holds that against what each estimator declares it did, so an
  interval that stays silent about a named cluster column is rejected rather
  than shipped.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.longitudinal import (
    estimate_longitudinal_gformula,
    estimate_longitudinal_ipw_msm,
)
from themis.language import spoken
from themis.verifier.errors import VerificationError


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


# --- longitudinal DGP ---------------------------------------------------------
#
# The first treatment is assigned AT THE CLINIC and the clinic also shifts Y,
# so the A0 half of the strategy contrast has effective sample size G, not n.
# That is the case i.i.d. row resampling cannot see. Truth is unchanged by the
# clinic effect (it averages to zero):
#     E[Y_{a0,a1}] = 2·a0 + 3·a1 + 1.5·E[L1 | do(a0)] = 3.5·a0 + 3·a1
#     ψ = E[Y_{1,1}] − E[Y_{0,0}] = 6.5

TRUE_STRATEGY_EFFECT = 6.5


def _clustered_dgp(rng, *, G=30, per=20, clinic_sd=2.0):
    n = G * per
    clinic = np.repeat(np.arange(G), per)
    u = rng.normal(0, clinic_sd, G)[clinic]
    L0 = rng.normal(0, 1, n)
    A0 = rng.integers(0, 2, G)[clinic].astype(bool)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.8 * L1 - 0.4)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + u + rng.normal(0, 1, n)
    return pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1, "Y": Y,
                         "clinic": clinic})


_LONG_KW = dict(treatments=("A0", "A1"),
                confounders_by_time=(("L0",), ("L1",)),
                outcome="Y", random_state=11)

_ESTIMATORS = {
    "gformula": (estimate_longitudinal_gformula, {"n_sim": 1500}),
    "ipw_msm": (estimate_longitudinal_ipw_msm, {}),
}


# ============================================== the g-methods honour the column


@pytest.mark.parametrize("name", sorted(_ESTIMATORS))
def test_iid_undercovers_and_the_cluster_interval_covers(name):
    """The reason the cluster draw exists. Across repeated samples the i.i.d.
    95% interval covers the true strategy effect well below nominal, while the
    cluster interval is near nominal — and decisively wider."""
    fn, extra = _ESTIMATORS[name]
    reps = 10
    iid_hits = clu_hits = 0
    iid_widths, clu_widths = [], []
    for s in range(reps):
        df = _clustered_dgp(np.random.default_rng(500 + s))
        iid = fn(df, **_LONG_KW, **extra, ci_bootstrap=80)
        clu = fn(df, **_LONG_KW, **extra, ci_bootstrap=80, cluster="clinic")
        iid_hits += iid.ci_lower <= TRUE_STRATEGY_EFFECT <= iid.ci_upper
        clu_hits += clu.ci_lower <= TRUE_STRATEGY_EFFECT <= clu.ci_upper
        iid_widths.append(iid.ci_upper - iid.ci_lower)
        clu_widths.append(clu.ci_upper - clu.ci_lower)

    assert iid_hits <= 8, f"i.i.d. coverage {iid_hits}/{reps} unexpectedly high"
    assert clu_hits > iid_hits
    assert clu_hits >= 9
    assert np.mean(clu_widths) > 1.5 * np.mean(iid_widths)


@pytest.mark.parametrize("name", sorted(_ESTIMATORS))
def test_the_estimator_reports_the_column_it_resampled(name):
    fn, extra = _ESTIMATORS[name]
    df = _clustered_dgp(np.random.default_rng(3))
    clu = fn(df, **_LONG_KW, **extra, ci_bootstrap=40, cluster="clinic")
    assert clu.cluster == "clinic"
    assert "ci_via_pairs_cluster_bootstrap_on_clinic" in clu.assumptions


@pytest.mark.parametrize("name", sorted(_ESTIMATORS))
def test_no_cluster_column_is_byte_identical_to_before(name):
    """The i.i.d. path must consume the rng exactly as it did, so every
    existing longitudinal result is unmoved."""
    fn, extra = _ESTIMATORS[name]
    df = _clustered_dgp(np.random.default_rng(4))
    a = fn(df, **_LONG_KW, **extra, ci_bootstrap=40)
    b = fn(df, **_LONG_KW, **extra, ci_bootstrap=40, cluster=None)
    assert (a.point, a.ci_lower, a.ci_upper) == (b.point, b.ci_lower, b.ci_upper)
    assert a.assumptions == b.assumptions
    assert a.cluster is None


@pytest.mark.parametrize("name", sorted(_ESTIMATORS))
def test_the_cluster_column_stays_out_of_the_model_and_the_hash(name):
    """A cluster id is a variance concern, not a causal-model variable: it
    must not change the point, and must not change the data fingerprint."""
    fn, extra = _ESTIMATORS[name]
    df = _clustered_dgp(np.random.default_rng(5))
    with_col = fn(df, **_LONG_KW, **extra, ci_bootstrap=0, cluster="clinic")
    without = fn(df.drop(columns=["clinic"]), **_LONG_KW, **extra, ci_bootstrap=0)
    assert with_col.point == without.point
    assert with_col.data_hash == without.data_hash


# ================================================ the run records what it chose


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "subj"}]}


def _long_program(estimator="gformula", *, options_cluster=None):
    options = {"longitudinal": {
        "estimator": estimator, "treatments": ["A0", "A1"],
        "confounders_by_time": [["L0"], ["L1"]], "outcome": "Y",
        "strategy_treated": 1, "strategy_control": 0,
        "n_sim": 1000, "ci_bootstrap": 40,
    }}
    if options_cluster is not None:
        options["cluster"] = options_cluster
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "subj"}]},
        "options": options,
        "statements": [
            {"kind": "variable", "predicate": "L0"},
            {"kind": "variable", "predicate": "A0", "domain": [True, False]},
            {"kind": "variable", "predicate": "L1"},
            {"kind": "variable", "predicate": "A1", "domain": [True, False]},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": _atom("A0"), "to": _atom("L1")},
            {"kind": "cause", "from": _atom("L1"), "to": _atom("A1")},
            {"kind": "cause", "from": _atom("L1"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("A0"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("A1"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("L0"), "to": _atom("A0")},
            {"kind": "cause", "from": _atom("L0"), "to": _atom("Y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "target": {"atom": _atom("Y"), "value": True},
                "intervention": {"atom": _atom("A1"), "value": True},
                "given": []}},
        ],
    }


@pytest.fixture(scope="module")
def long_frame():
    return _clustered_dgp(np.random.default_rng(8))


def test_the_run_records_the_cluster_column_it_resolved(long_frame):
    out = themis.estimate(_long_program(), long_frame, cluster="clinic")
    result = out["results"][0]
    assert result["estimation_context"]["cluster"] == "clinic"


def test_the_program_option_is_recorded_the_same_way(long_frame):
    out = themis.estimate(_long_program(options_cluster="clinic"), long_frame)
    assert out["results"][0]["estimation_context"]["cluster"] == "clinic"


def test_a_run_that_named_no_cluster_records_none(long_frame):
    out = themis.estimate(_long_program(), long_frame.drop(columns=["clinic"]))
    assert "cluster" not in out["results"][0]["estimation_context"]


@pytest.mark.parametrize("estimator", ["gformula", "ipw_msm"])
def test_the_longitudinal_answer_now_names_the_cluster_column(long_frame,
                                                              estimator):
    """The measured defect, end to end: the column reaches the estimator, the
    interval moves, and the envelope says so."""
    prog = _long_program(estimator)
    plain = themis.estimate(prog, long_frame)["results"][0]
    clus = themis.estimate(prog, long_frame, cluster="clinic")["results"][0]

    p, c = plain["numeric_estimate"], clus["numeric_estimate"]
    # Under cluster-level treatment the honest interval is the WIDER one;
    # equality here was the defect (the column never reached the estimator).
    assert (c["ci_upper"] - c["ci_lower"]) > 1.5 * (p["ci_upper"] - p["ci_lower"])
    assert c["bootstrap"]["kind"] == "cluster"
    assert c["bootstrap"]["cluster_column"] == "clinic"
    assert "ci_via_pairs_cluster_bootstrap_on_clinic" in c["assumptions"]
    # The i.i.d. run now SAYS i.i.d. rather than leaving it to the block's
    # absence, which is what let a second fact — how many draws survived —
    # have nowhere to go.
    assert p["bootstrap"]["kind"] == "iid"
    assert "cluster_column" not in p["bootstrap"]


@pytest.mark.parametrize("estimator", ["gformula", "ipw_msm"])
def test_the_cluster_declaration_reaches_the_disclosure_surface(long_frame,
                                                                estimator):
    """The ledger is what the report and the rendering bridge lead with, so a
    declaration that stops at ``numeric_estimate.assumptions`` is still
    invisible to a reader."""
    clus = themis.estimate(_long_program(estimator), long_frame,
                           cluster="clinic")["results"][0]
    ledger = (clus.get("extensions") or {}).get("assumption_ledger")
    assert ledger is not None
    entry = next(e for e in ledger["assumptions"]
                 if "clinic" in (e.get("id") or ""))
    # How the interval was computed cannot invalidate the identification.
    assert entry["severity"] == "confidence_only"
    assert "clinic" in spoken(entry["claim"])


# ======================================= every family, not just the fixed one


def _v(p, **kw):
    return {"kind": "variable", "predicate": p, **kw}


def _c(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _cross_program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "subj"}]},
            "statements": statements}


_EFFECT_Q = {"kind": "query", "id": "q", "query": {
    "kind": "effect", "intervention": {"atom": _atom("x"), "value": True},
    "target": {"atom": _atom("y"), "value": True}, "given": []}}

_BACKDOOR = _cross_program([_v("x"), _v("y"), _v("z"),
                            _c("x", "y"), _c("z", "x"), _c("z", "y"), _EFFECT_Q])
_FRONTDOOR = _cross_program([
    _v("x"), _v("m"), _v("y"), _c("x", "m"), _c("m", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")}, _EFFECT_Q])
_IV = _cross_program([
    _v("z"), _v("x"), _v("y"), _c("z", "x"), _c("x", "y"),
    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")}, _EFFECT_Q])
_MEDIATION = _cross_program([
    _v("x"), _v("m"), _v("y"), _c("x", "m"), _c("m", "y"), _c("x", "y"),
    {"kind": "query", "id": "q", "query": {
        "kind": "effect", "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True}, "given": [],
        "mediator": _atom("m")}}])


@pytest.fixture(scope="module")
def cross_frame():
    rng = np.random.default_rng(6)
    G, per = 40, 25
    n = G * per
    clinic = np.repeat(np.arange(G), per)
    u = rng.normal(0, 1.5, G)[clinic]
    z = rng.integers(0, 2, n)
    lat = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.25 + 0.3 * z + 0.2 * lat).astype(int)
    m = (rng.random(n) < 0.2 + 0.5 * x).astype(int)
    y = 0.4 * x + 0.5 * m + 0.3 * z + 0.6 * lat + u + rng.normal(0, 0.4, n)
    return pd.DataFrame({"x": x, "y": y, "z": z, "m": m, "clinic": clinic})


_CROSS_BATTERY = {
    "backdoor": _BACKDOOR,
    "frontdoor": _FRONTDOOR,
    "iv": _IV,
    "mediation": _MEDIATION,
}


@pytest.mark.parametrize("name", sorted(_CROSS_BATTERY))
def test_every_family_under_a_clustered_run_names_the_column(name, cross_frame):
    """The invariant the verifier enforces, checked directly on real output —
    this is what catches the next producer that forgets to thread the column."""
    out = themis.estimate(_CROSS_BATTERY[name], cross_frame,
                          cluster="clinic", ci_bootstrap=20)
    for result in out["results"]:
        estimate = result.get("numeric_estimate")
        if not estimate or estimate.get("ci_lower") is None:
            continue
        assert any("clinic" in a for a in estimate.get("assumptions") or ()), (
            f"{name}: the {estimate.get('method')!r} interval says nothing "
            f"about the cluster column"
        )


# ============================================================ the verifier


@pytest.fixture(scope="module")
def clustered_result(long_frame):
    out = themis.estimate(_long_program(), long_frame, cluster="clinic")
    return out["results"][0]


@pytest.mark.parametrize("name", sorted(_CROSS_BATTERY))
def test_verify_accepts_an_honest_clustered_run(name, cross_frame):
    out = themis.estimate(_CROSS_BATTERY[name], cross_frame,
                          cluster="clinic", ci_bootstrap=20)
    for result in out["results"]:
        themis.verify_cluster_inference(result)


def test_verify_accepts_the_honest_longitudinal_answer(clustered_result):
    themis.verify_cluster_inference(clustered_result)


def _tamper(result, mutate):
    clone = copy.deepcopy(result)
    mutate(clone)
    return clone


def test_an_interval_silent_about_the_cluster_column_is_rejected(
        clustered_result):
    """The measured defect itself, as the verifier sees it."""
    def drop(r):
        ne = r["numeric_estimate"]
        ne["assumptions"] = [a for a in ne["assumptions"] if "clinic" not in a]
        ne.pop("bootstrap", None)

    with pytest.raises(VerificationError, match="never mention it"):
        themis.verify_cluster_inference(_tamper(clustered_result, drop))


def test_a_stamp_the_estimator_never_corroborated_is_rejected(
        clustered_result):
    """The bootstrap block is written by dispatch; the assumptions are the
    estimator's own report. A stamp with no report behind it is dispatch
    asserting cluster-robustness that never happened."""
    def strip_declaration(r):
        ne = r["numeric_estimate"]
        ne["assumptions"] = [a for a in ne["assumptions"] if "clinic" not in a]

    with pytest.raises(VerificationError, match="unattributed"):
        themis.verify_cluster_inference(
            _tamper(clustered_result, strip_declaration))


def test_a_stamp_naming_a_different_column_is_rejected(clustered_result):
    def rename(r):
        r["numeric_estimate"]["bootstrap"]["cluster_column"] = "ward"

    with pytest.raises(VerificationError, match="but the run resolved"):
        themis.verify_cluster_inference(_tamper(clustered_result, rename))


def test_a_stamp_with_no_run_level_cluster_is_rejected(clustered_result):
    def forget_run_level(r):
        r["estimation_context"].pop("cluster")

    with pytest.raises(VerificationError, match="no run-level basis"):
        themis.verify_cluster_inference(
            _tamper(clustered_result, forget_run_level))


def test_an_estimator_that_declares_it_did_not_cluster_is_accepted(
        clustered_result):
    """Honest non-robustness is a disclosure, not a defect: an analytic
    interval that cannot cluster passes by saying so."""
    def declare_instead(r):
        ne = r["numeric_estimate"]
        ne.pop("bootstrap", None)
        ne["assumptions"] = [
            a for a in ne["assumptions"] if "clinic" not in a
        ] + ["ci_not_cluster_robust_analytic_interval_ignores_clinic"]

    themis.verify_cluster_inference(_tamper(clustered_result, declare_instead))


def test_an_answer_with_no_interval_owes_nothing(clustered_result):
    def drop_interval(r):
        ne = r["numeric_estimate"]
        ne["ci_lower"] = ne["ci_upper"] = None
        ne["assumptions"] = [a for a in ne["assumptions"] if "clinic" not in a]
        ne.pop("bootstrap", None)

    themis.verify_cluster_inference(_tamper(clustered_result, drop_interval))


def test_verify_runs_the_cluster_audit_on_the_main_path(clustered_result,
                                                        long_frame):
    """Not only the standalone entry: the tampered result must be caught by
    ``themis.verify`` too, or the audit is off the path callers use.

    The tamper retargets the bootstrap stamp rather than deleting a
    declaration, so no other audit surface is disturbed and the rejection can
    only have come from the cluster rule."""
    prog = _long_program()

    def retarget(r):
        r["numeric_estimate"]["bootstrap"]["cluster_column"] = "ward"

    themis.verify(prog, clustered_result)
    with pytest.raises(VerificationError, match="but the run resolved"):
        themis.verify(prog, _tamper(clustered_result, retarget))
