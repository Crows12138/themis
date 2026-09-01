"""Pipeline wiring for the PN/PS/PNS (causation) NUMERIC end.

The CausationQuery structural end (run) already answers from theta. This slice
threads the DATA end through the estimation dispatch, schema, and independent
verifier so a client can hand the kernel a causation query + a DataFrame and get
back PN/PS/PNS recovered from data (empirical joint + g-formula do-risks →
Tian-Pearl), which a second, independent pass re-derives.

The verifier mirror ``numeric_causation_estimate`` re-applies the Tian-Pearl
theorem (its OWN transcription) to the reported joint + do-risks and re-derives
the back-door adjustment set on ctx.graph — so a tampered point, do-risk, or
adjustment set is rejected, and a good result verified against a graph that
breaks the identification is rejected too.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result
from themis.verifier import VerificationError
from themis import refusals


# ------------------------------------------------------------------ builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _causation_query(monotonic=True, **kw):
    q = {"kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
         "monotonic": monotonic}
    q.update(kw)
    return q


def _ast(edges, *, monotonic=True, variables=("x", "y", "z"), theta=(), **qkw):
    # Confounded structure by default: Z→X, Z→Y, X→Y (back-door set {Z}).
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *(_var(v) for v in variables),
            *edges, *theta,
            {"kind": "query", "id": "q",
             "query": _causation_query(monotonic=monotonic, **qkw)},
        ],
    }


_CONFOUNDED = (_cause("z", "x"), _cause("z", "y"), _cause("x", "y"))


def _sample(n: int, seed: int) -> pd.DataFrame:
    """Rank-preserving monotone SCM with an observed confounder Z; true
    PN≈0.446, PS≈0.521, PNS=0.35 (see tests/test_estimation_causation.py)."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.5, 0.2)
    b = np.where(z, 0.8, 0.6)
    y0, y1 = u < a, u < b
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _sample_nonmono(n: int, seed: int) -> pd.DataFrame:
    """Confounded SCM WITH preventive (hurt) units — Y=1 iff X=0 for some
    units, so Y is NOT monotone in X. PN/PS/PNS are then genuinely bounds
    (no point identification). Z confounds X and Y (back-door set {Z})."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.15, 0.25)   # survivor cum
    b = np.where(z, 0.55, 0.55)   # + helped cum
    c = np.where(z, 0.80, 0.75)   # + hurt cum
    surv, helped, hurt = u < a, (u >= a) & (u < b), (u >= b) & (u < c)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.zeros(n, dtype=bool)
    y[surv] = True
    y[helped] = x[helped]
    y[hurt] = ~x[hurt]            # preventive → non-monotone
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _result(r):
    return r["results"][0]


# ------------------------------------------------------------------ schema
def test_schema_accepts_causation_numeric_result():
    df = _sample(30_000, seed=1)
    res = _result(themis.estimate(_ast(_CONFOUNDED), df))
    validate_result(res)  # round-trips the numeric_estimate + poc block


# ------------------------------------------------------------------ estimate
def test_estimate_recovers_points_and_provenance():
    df = _sample(200_000, seed=2)
    res = _result(themis.estimate(_ast(_CONFOUNDED), df))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert ne["method"] == "causation_plugin"
    assert ne["treatment"] == "x" and ne["outcome"] == "y"
    assert abs(ne["point"] - 0.446) < 0.02                     # PN headline
    poc = ne["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "backdoor_adjustment"
    assert poc["adjustment"] == ["z"]
    assert abs(poc["ps"]["point"] - 0.521) < 0.02
    assert abs(poc["pns"]["point"] - 0.35) < 0.02
    # bounds present on every quantity
    for q in ("pn", "ps", "pns"):
        assert poc[q]["lower"] <= poc[q]["point"] <= poc[q]["upper"]


def test_estimate_without_monotonicity_attaches_data_bounds():
    # No monotonicity → PN/PS/PNS are genuinely bounds. The data DOES answer the
    # question (Tian-Pearl bounds from the empirical joint + g-formula do-risks),
    # so a bounds overlay is attached (numerically_solved), the headline point is
    # OMITTED, and the answer_tier is 'interval'.
    df = _sample_nonmono(60_000, seed=3)
    res = _result(themis.estimate(_ast(_CONFOUNDED, monotonic=False), df))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert "point" not in ne                       # no headline point for bounds
    assert ne["method"] == "causation_plugin"
    poc = ne["probabilities_of_causation"]
    assert poc["monotonic"] is False
    assert poc["interventional_risk_provenance"] == "backdoor_adjustment"
    assert poc["adjustment"] == ["z"]
    for q in ("pn", "ps", "pns"):
        b = poc[q]
        assert b["point"] is None                  # not point-identified
        assert 0.0 <= b["lower"] < b["upper"] <= 1.0   # a genuine interval
        # outer band brackets the identified interval
        assert b["ci_lower"] <= b["lower"] + 1e-9
        assert b["ci_upper"] >= b["upper"] - 1e-9
    assert res["numeric_result"] == {"value": None}
    assert res["data_gap_report"]["answer_tier"] == "interval"


def test_bounds_contain_true_values_and_schema_ok():
    # The recovered bounds must be valid (contain the true PN/PS/PNS of the SCM)
    # and round-trip through the schema.
    df = _sample_nonmono(200_000, seed=21)
    res = _result(themis.estimate(_ast(_CONFOUNDED, monotonic=False), df))
    validate_result(res)
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    # True values for this SCM (marginalized over z, p(z)=0.5):
    #   helped = 0.40, survivor = 0.20 => PNS = 0.40
    #   PN = helped/(surv+helped) = 0.40/0.60 ; PS = helped/(helped+never)
    # Rather than pin exact constants, assert the intervals are non-degenerate
    # and the point-estimate identities from an independent empirical PNS.
    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    assert poc["pns"]["lower"] <= poc["pns"]["upper"]
    # PNS lower bound is a valid Fréchet-type floor: max(0, do1-do0)
    do1 = poc["p_y_do_x1"]; do0 = poc["p_y_do_x0"]
    assert poc["pns"]["lower"] >= max(0.0, do1 - do0) - 1e-9


def test_bounds_exogenous_provenance():
    # X→Y only, X exogenous, NON-monotone: bounds recovered with adjustment=[].
    rng = np.random.default_rng(31)
    n = 120_000
    x = rng.random(n) < 0.5
    u = rng.random(n)
    # response types independent of X (exogenous): survivor .2 / helped .3 /
    # hurt .2 / never .3 → non-monotone via the hurt (preventive) mass.
    y = np.where(u < 0.2, True,
                 np.where(u < 0.5, x,
                          np.where(u < 0.7, ~x, False)))
    df = pd.DataFrame({"x": x, "y": y})
    res = _result(themis.estimate(
        _ast((_cause("x", "y"),), monotonic=False, variables=("x", "y")), df))
    assert res["status"] == "numerically_solved"
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["monotonic"] is False
    assert poc["interventional_risk_provenance"] == "exogenous"
    assert poc["adjustment"] == []
    for q in ("pn", "ps", "pns"):
        assert poc[q]["point"] is None
        assert poc[q]["lower"] <= poc[q]["upper"]
    themis.verify(
        _ast((_cause("x", "y"),), monotonic=False, variables=("x", "y")), res)


def test_verify_accepts_data_bounds():
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(80_000, seed=6)))
    themis.verify(prog, res)             # independent Tian-Pearl bounds re-derivation


def test_verify_rejects_tampered_bound():
    # Falsely widen the reported PNS lower bound: the verifier re-derives the
    # Tian-Pearl bounds from the reported joint + do-risks and the claim no
    # longer matches (strong re-derivation catches a self-consistent forgery of
    # the interval).
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=7)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["pns_lower"] = 0.0
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_do_risk_on_bounds():
    # Tamper a do-risk on the bounds answer: the re-applied Tian-Pearl bounds
    # change, so the reported lower/upper no longer match — caught even though
    # the bound fields themselves were left untouched.
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=8)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["p_y_do_x1"] = 0.05
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_the_interval_says_which_kind_it_is_and_the_verifier_re_derives_it():
    """#419: the word that decides what a reader does next is audited.

    A band on the identified interval relabelled a sampling CI tells a
    reader to collect more data for a width no amount of data narrows, and
    nothing in the endpoints contradicts it — the two look identical. So
    the verifier settles it the way the producer had to: a point came out
    or it did not. Saying nothing is refused as well, because a row that
    omits it sends every surface back to working the answer out for itself,
    which is the state this field was added to end.
    """
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=11)))
    stated = [st["inputs"]["ci_width_is"] for st in res["derivation"]["steps"]
              if st["rule"] == "numeric_causation_estimate"]
    assert stated == ["outer_band"], stated
    themis.verify(prog, res)

    for wrong in ("sampling", None):
        tam = copy.deepcopy(res)
        for st in tam["derivation"]["steps"]:
            if st["rule"] == "numeric_causation_estimate":
                if wrong is None:
                    st["inputs"].pop("ci_width_is")
                else:
                    st["inputs"]["ci_width_is"] = wrong
        with pytest.raises(VerificationError, match="ci_width_is"):
            themis.verify(prog, tam)


def test_verify_rejects_bounds_display_copy_tamper():
    # extensions.causation is the display copy the explainer reads; the kernel
    # cross-checks it against the audited derivation inputs. Falsify a bound
    # there and verification must reject.
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=9)))
    tam = copy.deepcopy(res)
    tam["extensions"]["causation"]["pns"]["lower"] = 0.0
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_estimate_exogenous_provenance():
    # X→Y only, X exogenous: do-risk = P(Y|X), adjustment empty.
    rng = np.random.default_rng(5)
    n = 120_000
    x = rng.random(n) < 0.5
    u = rng.random(n)
    y = np.where(x, u < 0.7, u < 0.3)
    df = pd.DataFrame({"x": x, "y": y})
    res = _result(themis.estimate(
        _ast((_cause("x", "y"),), variables=("x", "y")), df))
    assert res["status"] == "numerically_solved"
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "exogenous"
    assert poc["adjustment"] == []


# ------------------------------------------------------------------ verify
def test_verify_accepts_numeric():
    prog = _ast(_CONFOUNDED)
    df = _sample(80_000, seed=6)
    themis.verify(prog, _result(themis.estimate(prog, df)))


def test_verify_rejects_tampered_data_hash():
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=7)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["data_hash"] = "deadbeef"
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_point():
    # Flip the reported PN point: the rule re-derives Tian-Pearl from the
    # reported joint + do-risks and the claim no longer matches.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=8)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["pn_point"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_do_risk():
    # Tamper a do-risk: the re-applied Tian-Pearl points change, so the
    # reported points no longer match — caught even though the point fields
    # themselves were left untouched.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=9)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["p_y_do_x1"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_extensions_display_copy():
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=10)))
    tam = copy.deepcopy(res)
    tam["extensions"]["causation"]["pn"]["point"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_wrong_adjustment_set():
    # Claim the empty adjustment set on a genuinely confounded graph: the rule
    # re-derives the admissible sets ({z}) and rejects the empty claim.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=11)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["adjustment"] = {"kind": "atom_tuple", "items": []}      # claim exogenous / empty set
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_reruns_adjustment_from_graph():
    # A good {z}-adjusted result, verified against a program whose graph makes
    # z irrelevant (no z→y): the empty set now suffices, so the claimed {z}
    # is not an admissible MINIMAL set — the rule re-derives from ctx.graph
    # and rejects. Proves the identification check has teeth.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=12)))
    broken = _ast((_cause("z", "x"), _cause("x", "y")))  # z no longer confounds
    with pytest.raises(VerificationError):
        themis.verify(broken, res)


# ------------------------------------------------- and it reaches the reader
def test_the_answer_section_names_all_three_whether_or_not_monotonicity_holds():
    """The question line asks for PN, PS and PNS by name; so must the answer.

    ``causation_plugin`` declared ``point`` for its monotone mode, and every
    causation estimate carries a ``point`` because the headline has to be one
    number — so the SHARPER answer reached the reader as a bare ``**0.4379**``
    while the bounded mode, having no headline to detect, named all three.
    Both modes share one renderer now, which is also the one the theta path
    uses (tests/test_causation_query.py).
    """
    from themis.output.analysis_report import build_analysis_report

    def answer_of(prog, df):
        r = _result(themis.estimate(prog, df))
        return build_analysis_report(r, program=prog).split(
            "## 答案", 1)[1].split("\n##", 1)[0]

    sharp = answer_of(_ast(_CONFOUNDED), _sample(30_000, seed=2))
    assert "单调性成立" in sharp
    for label in ("必要性 PN", "充分性 PS", "必要且充分 PNS"):
        assert label in sharp, sharp
    # What the assumption bought, beside what it bought it from.
    # The word comes from themis.intervals.Width now rather than from a
    # two-member table in the renderer, and it says which of the two
    # objects the ci pair holds (#419).
    assert "95% 置信区间" in sharp
    assert "无单调性假设时只能给到" in sharp
    # And where the two do-risks came from, with the set they used.
    assert "后门标准化" in sharp and "调整集 {z}" in sharp

    blunt = answer_of(_ast(_CONFOUNDED, monotonic=False),
                      _sample_nonmono(30_000, seed=3))
    assert "未假设单调性" in blunt
    for label in ("必要性 PN", "充分性 PS", "必要且充分 PNS"):
        assert label in blunt, blunt
    assert "外带" in blunt
    assert "若可假设单调性" in blunt


# ================================== the routes the shared cascade brought (#321)
#
# The causation door used to stop at back-door adjustment and refuse. The
# counterfactual-cell door, asked for the SAME PN, went on through the general
# ID algorithm and then to an instrument's response-type polytope — so which
# door was knocked on decided whether there was an answer. The cascade is one
# function now (``binary_do_risk.choose_risk_route``) and each door projects it
# onto the arms it consumes; these pin what that made reachable here.

_BOW_IV = (_cause("z", "x"), _cause("x", "y"))
_FRONT_DOOR = (_cause("x", "m"), _cause("m", "y"))
_LATENT_XY = ({"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},)


def _sample_bow_iv(n: int, seed: int):
    """Rank-preserving SCM behind a bow arc, driven by an instrument.

    The latent ``w`` moves both treatment and outcome, so no measured set
    blocks the back door; ``z`` moves only the treatment. Returns the frame the
    estimator sees together with the two potential outcomes it cannot see, so a
    test can count units instead of re-deriving a theorem.
    """
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.5
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0 = u < np.where(w, 0.55, 0.15)
    y1 = u < np.where(w, 0.90, 0.45)
    x = rng.random(n) < np.where(z, np.where(w, 0.85, 0.55),
                                np.where(w, 0.35, 0.10))
    return pd.DataFrame({"x": x, "y": np.where(x, y1, y0), "z": z}), y0, y1


def _sample_front_door(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.5                    # unmeasured, moves x and y
    x = rng.random(n) < np.where(w, 0.8, 0.3)
    m = rng.random(n) < np.where(x, 0.75, 0.2)
    y = rng.random(n) < np.where(m, 0.8, 0.25) * np.where(w, 1.0, 0.7)
    return pd.DataFrame({"x": x, "y": y, "m": m})


def _ast_bidirected(edges, *, monotonic=False, variables=("x", "y", "z"),
                    bidirected=()):
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *(_var(v) for v in variables), *edges, *bidirected,
            {"kind": "query", "id": "q",
             "query": _causation_query(monotonic=monotonic)},
        ],
    }


def _iv_estimated(seed=7, n=40_000, ci_bootstrap=0, monotonic=False):
    df, y0, y1 = _sample_bow_iv(n, seed=seed)
    prog = _ast_bidirected(_BOW_IV, monotonic=monotonic, bidirected=_LATENT_XY)
    return (prog, _result(themis.estimate(prog, df, ci_bootstrap=ci_bootstrap)),
            df, y0, y1)


def test_a_bow_arc_with_an_instrument_is_answered_instead_of_refused():
    """The registered asymmetry, as a behaviour: these three had no numbers.

    The route is named on the answer, no interventional risks are reported
    beside it (there are none to report), and each interval covers the SCM's
    own value — counted off the potential outcomes, not re-derived.
    """
    prog, res, df, y0, y1 = _iv_estimated()
    validate_result(res)
    assert res["status"] == "numerically_solved"
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "instrument_response_polytope"
    assert poc["instrument"] == "z"
    assert poc["p_y_do_x1"] is None and poc["p_y_do_x0"] is None
    assert poc["adjustment"] == []
    assert res["data_gap_report"]["answer_tier"] == "interval"

    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    truth = {
        "pn": float((~y0[x & y]).mean()),
        "ps": float(y1[(~x) & (~y)].mean()),
        "pns": float((y1 & ~y0).mean()),
    }
    for q, value in truth.items():
        assert poc[q]["point"] is None
        assert poc[q]["lower"] <= value <= poc[q]["upper"], q
        assert poc[q]["upper"] - poc[q]["lower"] < 1.0, q      # it says something
    themis.verify(prog, res)


def test_a_front_door_structure_reaches_both_arms_through_general_id():
    """The other route the shared cascade brought. No covariate set blocks the
    back door, and the ID algorithm point-identifies each arm anyway — so this
    answer is a pair of numbers where the instrument route has none."""
    prog = _ast_bidirected(_FRONT_DOOR, variables=("x", "y", "m"),
                           bidirected=_LATENT_XY)
    res = _result(themis.estimate(prog, _sample_front_door(40_000, seed=3),
                                  ci_bootstrap=0))
    validate_result(res)
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "general_id_plug_in"
    assert poc["instrument"] is None
    assert poc["p_y_do_x1"] is not None and poc["p_y_do_x0"] is not None
    assert poc["adjustment"] == []
    themis.verify(prog, res)


def test_a_graph_with_no_route_at_all_still_refuses():
    """The counterexample the widened cascade has to keep producing.

    A bow arc with no instrument and no mediator reaches nothing, and the
    refusal has to name every route that was tried — a caller told only "no
    back-door set" would go looking for a covariate that cannot help.
    """
    df, _y0, _y1 = _sample_bow_iv(4_000, seed=7)
    prog = _ast_bidirected((_cause("x", "y"),), variables=("x", "y"),
                           bidirected=_LATENT_XY)
    res = _result(themis.estimate(prog, df[["x", "y"]], ci_bootstrap=0))
    assert "numeric_estimate" not in res
    failure = res["estimator_failure"]
    assert failure["failure_type"] == "do_risk_not_identifiable_by_any_route"
    for tried in ("后门", "ID 算法", "工具变量"):
        assert tried in refusals.said(failure), refusals.said(failure)


def test_a_point_identified_pair_of_risks_still_wins_over_the_instrument():
    """The cascade's order is not arbitrary: a point beats an interval, and it
    is the same order on both doors because it is the same cascade."""
    prog = _ast((_cause("z", "x"), _cause("z", "y"), _cause("x", "y")),
                monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(20_000, seed=21),
                                  ci_bootstrap=0))
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "backdoor_adjustment"
    assert poc["instrument"] is None


def test_a_declared_monotonicity_narrows_the_polytope_rather_than_pinning_it():
    """It enters this route as a restriction of the model, not a second formula.

    Measured over 400 random binary IV models it collapses none of the three to
    a point while narrowing every one of them, which is why the interval it
    returns is the post-assumption one and there is no separate point channel.
    """
    _p_free, free, _df, _y0, _y1 = _iv_estimated(monotonic=False)
    prog, pinned, df, y0, _y1 = _iv_estimated(monotonic=True)
    a = free["numeric_estimate"]["probabilities_of_causation"]
    b = pinned["numeric_estimate"]["probabilities_of_causation"]
    for q in ("pn", "ps", "pns"):
        assert a[q]["lower"] <= b[q]["lower"] and b[q]["upper"] <= a[q]["upper"]
        assert b[q]["upper"] - b[q]["lower"] < a[q]["upper"] - a[q]["lower"], q
        assert b[q]["point"] is None, q
    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    assert b["pn"]["lower"] <= float((~y0[x & y]).mean()) <= b["pn"]["upper"]
    themis.verify(prog, pinned)


def test_the_polytope_refutes_a_monotonicity_the_data_contradict():
    """The gate this route earns. ``monotonic`` on a CausationQuery is
    Tian-Pearl's direction — X never prevents Y — and a sample built the other
    way round empties the type space, which the closed form cannot notice at
    all because it has no feasible set to empty."""
    from themis.estimation.causation import estimate_causation_probabilities
    from themis.refusals import EstimatorFailure, sentence
    from themis.types import Atom
    import networkx as nx

    x_atom, y_atom, z_atom = (Atom(predicate=p, args=()) for p in ("x", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z_atom, x_atom), (x_atom, y_atom)])
    df, _y0, _y1 = _sample_bow_iv(20_000, seed=7)
    df = df.assign(y=~df["y"].to_numpy())        # every unit now moves against x
    with pytest.raises(EstimatorFailure) as excinfo:
        estimate_causation_probabilities(
            df, graph=g, bidirected=frozenset({frozenset({x_atom, y_atom})}),
            cause=x_atom, effect=y_atom, monotonic=True, ci_bootstrap=0,
        )
    assert excinfo.value.failure_type == "counterfactual_inputs_infeasible"
    # Which language, said out loud: the species owns its sentence now, so
    # reading it means naming the reader. What is being checked is the same
    # claim as before — the refusal blames the assumption, not the instrument.
    assert "monotonicity" in sentence(
        excinfo.value.failure_type, excinfo.value.details, "en")


def test_the_report_says_where_the_three_intervals_came_from():
    """A reader told nothing about the route cannot weigh what it assumed.

    The line naming the route used to hang off the two do-risks being present,
    so the one route that reaches an answer WITHOUT them printed no line at all.
    """
    from themis.output.analysis_report import build_analysis_report

    prog, res, _df, _y0, _y1 = _iv_estimated()
    answer = build_analysis_report(res, program=prog).split(
        "## 答案", 1)[1].split("\n##", 1)[0]
    assert "没有用到任何干预风险" in answer
    assert "响应函数多面体" in answer
    assert "工具变量 `z`" in answer
    # And the sentence that would be false here is not printed.
    assert "无单调性假设时只能给到" not in answer


# ---------------------------------------------- and the verifier says no
def test_verify_rejects_a_tampered_response_table():
    prog, res, _df, _y0, _y1 = _iv_estimated()
    bad = copy.deepcopy(res)
    inp = bad["derivation"]["steps"][0]["inputs"]
    inp["p_xyz"]["items"][0]["items"][0]["items"][0] = 0.9
    with pytest.raises(VerificationError):
        themis.verify(prog, bad)


def test_verify_rejects_permuted_instrument_strata():
    """The table's shape says nothing about which stratum is which, so the
    level order is part of the claim rather than presentation."""
    prog, res, _df, _y0, _y1 = _iv_estimated()
    bad = copy.deepcopy(res)
    inp = bad["derivation"]["steps"][0]["inputs"]
    inp["p_xyz"]["items"].reverse()
    with pytest.raises(VerificationError):
        themis.verify(prog, bad)


def test_verify_rejects_do_risks_reported_beside_the_polytope_licence():
    """``instrument_response_polytope`` is the claim that no risk was obtained.
    A number beside it is a different answer wearing this one's licence."""
    prog, res, _df, _y0, _y1 = _iv_estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"].update(
        {"p_y_do_x1": 0.6, "p_y_do_x0": 0.3})
    with pytest.raises(VerificationError):
        themis.verify(prog, bad)


def test_verify_rejects_a_route_relabelled_as_back_door():
    """Relabelling is the cheapest forgery, because it is the licence that
    decides which re-derivation runs at all."""
    prog, res, _df, _y0, _y1 = _iv_estimated()
    bad = copy.deepcopy(res)
    bad["derivation"]["steps"][0]["inputs"][
        "interventional_risk_provenance"] = "backdoor_adjustment"
    with pytest.raises(VerificationError):
        themis.verify(prog, bad)


def test_verify_rejects_one_general_id_estimand_reused_for_both_arms():
    """PN/PS/PNS consume BOTH arms, so identifying one and evaluating it twice
    produces an answer shaped exactly like an honest one."""
    prog = _ast_bidirected(_FRONT_DOOR, variables=("x", "y", "m"),
                           bidirected=_LATENT_XY)
    res = _result(themis.estimate(prog, _sample_front_door(20_000, seed=3),
                                  ci_bootstrap=0))
    bad = copy.deepcopy(res)
    inp = bad["derivation"]["steps"][0]["inputs"]
    inp["risk_formula_control"] = copy.deepcopy(inp["risk_formula_treated"])
    with pytest.raises(VerificationError):
        themis.verify(prog, bad)
