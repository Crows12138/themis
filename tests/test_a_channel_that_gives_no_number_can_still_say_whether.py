"""When the proxies cannot restore an effect, they can still refute the null.

Miao, Geng & Tchetgen Tchetgen 2018 §4. Formula (5) recovers ``P(y | do(x))``
by inverting a ``k×k`` channel between the two proxies, which needs both of
them to present ``k`` levels and needs the result to be invertible. Where that
fails, the effect is not point-identified — and the *causal null* ``X ⊥ Y | U``
is still testable, because under it the stacked outcome means are confined to
the ``k``-dimensional space the latent's states span. ``ij`` numbers claimed to
lie in ``k`` dimensions is an over-identifying restriction with ``ij − k``
degrees of freedom, and that is what is tested.

Three claims are pinned here and they are not the same claim.

**That the test works.** A test is only worth reporting if it keeps its size
and has power, and neither is provable by reading the code — so both are
measured. The size check is the sharper of the two: Theorem 2 as printed
weights by the covariance of ``q̂`` alone, and because ``q̂`` and ``Q̂`` are
averages over the same rows, that weight leaves the first-stage error in
``Q̂`` uncarried. Measured, it rejects a true null 12–15% of the time at a
nominal 5%, and does not improve as the sample grows. The ceiling asserted
below is loose enough to survive Monte Carlo noise and tight enough that the
printed form fails it.

**That the run reaches it, and only from the right places.** Three refusal
species mean the channel is too thin, and each hands over; every other species
still refuses, including the graph-level one — the test assumes model (f)
exactly as the point estimate does, so a diagram that does not certify is a
diagram in which the test means nothing either. The asymmetry between the two
proxies is load-bearing and is checked directly: ``W`` sets the length of γ and
must fold to ``k``, while ``Z``'s levels are spent as moments and are used at
whatever resolution they come in.

**That the reader cannot mistake what they were handed.** A p-value given to
someone who asked how much is read as a small effect unless something says
otherwise. The answer shape, the gap, the tier and both languages' wording are
each checked for saying so.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.proximal import estimate_proximal_ate
# Aliased on import: the producer's entry point is named for what it does,
# and pytest would otherwise collect it as a test of its own and call it with
# no arguments.
from themis.estimation.proximal_null_test import (
    solve_null_test, test_causal_null as run_the_test,
)
from themis.output.analysis_report import build_analysis_report
from themis.refusals import EstimatorFailure, Refusal
from themis.types import Atom, DiscreteChannel, ProxyCoarsening
from themis.verifier import VerificationError

_STEP = "numeric_proximal_null_test"
_K = 3

#: The channel P(W | U). Rows are states of U, columns levels of W. Diagonally
#: dominant, so it inverts — which matters: every refusal below has to come
#: from the thing it names rather than from a proxy that carries nothing.
_PW = np.array([[0.70, 0.20, 0.10],
                [0.15, 0.70, 0.15],
                [0.10, 0.25, 0.65]])
#: P(Z = 1 | U) for the BINARY Z — two levels against three states of U, which
#: is the coarse proxy formula (5) cannot use and §4 can.
_PZ_COARSE = np.array([0.75, 0.45, 0.25])
#: The same proxy recorded at three levels, which formula (5) can use.
_PZ_FINE = np.array([[0.70, 0.20, 0.10],
                     [0.20, 0.60, 0.20],
                     [0.10, 0.25, 0.65]])


def _draw(rng: np.random.Generator, rows: np.ndarray, u: np.ndarray):
    """One categorical draw per row against its own row of ``rows``."""
    return (rng.random((len(u), 1)) > rows.cumsum(axis=1)[u]).sum(axis=1)


def _sample(n: int, effect: float, seed: int, *, fine_z: bool = False,
            arms: int = 2, split_w: bool = False) -> pd.DataFrame:
    """A model-(f) SCM where U is unobserved and the effect is ``effect``.

    ``effect`` enters the outcome's logit linearly in X, so ``effect == 0`` is
    the null EXACTLY — X is absent from Y's equation — rather than a small
    number standing in for zero. That is what makes the size measurement below
    a measurement rather than an approximation.
    """
    rng = np.random.default_rng(seed)
    u = rng.integers(0, _K, n)
    w = _draw(rng, _PW, u)
    if split_w:
        # The SAME proxy recorded twice as finely: the extra bit is a fair
        # coin, so it carries nothing about U and the declared fold below
        # recovers exactly the three-level proxy.
        w = w * 2 + (rng.random(n) < 0.5)
    z = (_draw(rng, _PZ_FINE, u) if fine_z
         else (rng.random(n) < _PZ_COARSE[u]).astype(int))
    px = 1 / (1 + np.exp(-(0.8 * (u - 1) + 0.6 * (z - z.mean()))))
    x = (rng.random(n) < px).astype(int)
    if arms > 2:
        x = x + (rng.random(n) < 0.4).astype(int)
    y = (rng.random(n) < 1 / (1 + np.exp(
        -(1.0 * (u - 1) + effect * x)))).astype(int)
    return pd.DataFrame({"x": x, "z": z, "w": w, "y": y})


# --- the query, as a program and as arguments ---------------------------------

def _atom(p: str) -> Atom:
    return Atom(predicate=p, args=())


X, Y, U, Z, W = (_atom("x"), _atom("y"), _atom("u"), _atom("z"), _atom("w"))


def _graph():
    import networkx as nx

    g = nx.DiGraph()
    g.add_nodes_from([X, Y, U, Z, W])
    g.add_edges_from([(U, X), (U, Y), (U, Z), (U, W), (Z, X), (W, Y), (X, Y)])
    return g


def _estimate(df: pd.DataFrame, *, k: int = _K, coarsening=None):
    return estimate_proximal_ate(
        df, graph=_graph(), treatment=X, outcome=Y, latent=U,
        treatment_proxy=(Z,), outcome_proxy=(W,), outcome_success=1,
        channel=DiscreteChannel(latent_cardinality=k,
                                proxy_coarsening=coarsening),
        ci_bootstrap=0)


def _var(p, domain=None):
    return {"kind": "variable", "predicate": p,
            "domain": [True, False] if domain is None else domain}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _program(*, k: int = _K, w_levels=(0, 1, 2), z_levels=(0, 1)) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x"), _var("y"), _var("u"),
            _var("z", list(z_levels)), _var("w", list(w_levels)),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": {"predicate": "x", "args": []},
                "outcome": {"predicate": "y", "args": []},
                "latent": {"predicate": "u", "args": []},
                "treatment_proxy": [{"predicate": "z", "args": []}],
                "outcome_proxy": [{"predicate": "w", "args": []}],
                "channel": {"kind": "discrete_channel",
                            "latent_cardinality": k},
            }},
        ],
    }


@pytest.fixture(scope="module")
def answered() -> tuple[dict, dict]:
    """One run under the null and one under a large effect, end to end."""
    out = {}
    for label, effect in (("null", 0.0), ("effect", 1.2)):
        program = _program()
        envelope = themis.estimate(
            program, _sample(30_000, effect, 7), ci_bootstrap=0)
        out[label] = envelope["results"][0]
    return out


# --- D1 prong 1: the test keeps its size and has power ------------------------

def test_a_true_null_is_rejected_at_about_the_nominal_rate():
    """The measurement the whole module rests on.

    A test that over-rejects is worse than no test: it manufactures evidence
    of causation out of a sample where there is none, in exactly the setting
    a reader turned to it because nothing else was available. The ceiling
    here is 9% against a nominal 5% — loose for 400 trials, and far under the
    12–15% that Theorem 2's printed weight produces on these same draws.
    """
    hits = 0
    trials = 400
    for seed in range(trials):
        got = run_the_test(_sample(4_000, 0.0, seed),
                               xcol="x", ycol="y", zcol="z", wcol="w")
        assert got.degrees_of_freedom == 1        # i=2, j=2, k=3 → ij − k
        hits += got.p_value < 0.05
    assert 0.01 <= hits / trials <= 0.09, hits / trials


def test_an_effect_that_is_there_is_found():
    """Size without power is a test that never says anything."""
    hits = 0
    trials = 120
    for seed in range(trials):
        got = run_the_test(_sample(4_000, 0.8, seed + 500),
                               xcol="x", ycol="y", zcol="z", wcol="w")
        hits += got.p_value < 0.05
    assert hits / trials >= 0.80, hits / trials


def test_more_treatment_levels_buy_degrees_of_freedom():
    """``ij ≥ k + 1`` is the requirement, and ``i`` pays it as well as ``j``.

    The paper's own point: a coarse Z can be afforded with a polytomous X.
    Three arms against a binary Z give ij = 6 and r = 3, where two arms gave
    r = 1 — so a treatment with more levels is not merely tolerated by the
    test, it is what makes the test sharper.
    """
    got = run_the_test(_sample(30_000, 0.0, 3, arms=3),
                           xcol="x", ycol="y", zcol="z", wcol="w")
    assert got.degrees_of_freedom == 3
    assert len(got.coefficients) == _K


# --- D1 prong 2: which runs reach it ------------------------------------------

@pytest.mark.parametrize("kwargs,blocked", [
    # Z shows two levels against three states of U: no square channel.
    ({}, Refusal.PROXY_CARDINALITY_MISMATCH),
    # The channel is fine and the contrast is not: three arms, no pair.
    ({"fine_z": True, "arms": 3}, Refusal.TREATMENT_NOT_BINARY),
])
def test_a_channel_too_thin_for_a_number_hands_over_to_the_test(
        kwargs, blocked):
    got = _estimate(_sample(30_000, 0.0, 7, **kwargs))
    assert got.method == "proximal_null_test"
    assert got.point is None
    assert got.do_prob_treated is None and got.do_prob_control is None
    assert got.channel["point_blocked_by"] == blocked.value
    assert got.no_effect_test["degrees_of_freedom"] >= 1


def test_the_point_estimate_still_runs_where_the_channel_inverts():
    """The counterexample the handover has to leave alone.

    A fallback that swallowed the working case would trade every number in
    this regime for a p-value, and nothing downstream would report the loss.
    """
    got = _estimate(_sample(30_000, 1.2, 7, fine_z=True))
    assert got.method == "proximal_matrix"
    assert got.point is not None
    assert got.no_effect_test is None


def test_a_graph_that_does_not_identify_still_refuses():
    """The species that must NOT hand over.

    Model (f) is what licenses the decomposition the null is read off, so a
    diagram that fails its criteria is one in which the test means nothing
    either. Handing over here would answer a question the graph forbids.
    """
    import networkx as nx

    g = _graph()
    g.add_edge(Z, Y)              # breaks Z ⊥ Y | (U, X)
    with pytest.raises(EstimatorFailure) as caught:
        estimate_proximal_ate(
            _sample(4_000, 0.0, 1), graph=g, treatment=X, outcome=Y,
            latent=U, treatment_proxy=(Z,), outcome_proxy=(W,),
            outcome_success=1,
            channel=DiscreteChannel(latent_cardinality=_K), ci_bootstrap=0)
    assert caught.value.failure_type == Refusal.NOT_IDENTIFIABLE_PROXIMAL


def test_a_coarse_outcome_proxy_keeps_its_refusal():
    """The two proxies fail differently, and only one of them hands over.

    ``W`` sets the length of γ: the null reads ``q = Qᵀγ`` with one
    coefficient per state of ``U``, and ``P(W | U)`` inverts only when ``W``
    has as many levels as ``U``. So a ``W`` that does not fold to ``k`` keeps
    the refusal — which names the field that would fix it, and fixing it is
    what the test needs anyway.
    """
    df = _sample(30_000, 0.0, 7, split_w=True)        # W at six levels
    with pytest.raises(EstimatorFailure) as caught:
        _estimate(df)
    assert caught.value.failure_type == Refusal.PROXY_CARDINALITY_MISMATCH


def test_a_treatment_proxy_that_is_too_FINE_keeps_its_refusal():
    """``PROXY_CARDINALITY_MISMATCH`` covers two opposite situations.

    Too coarse and no declaration reaches a number, so the test is the
    strongest thing left. Too fine and a point estimate is one
    ``proxy_coarsening`` away — handing back a p-value there would trade a
    reachable number for a weaker answer, and would take the errand that
    reaches the number off the page with it.
    """
    df = _sample(30_000, 1.2, 7)
    df["z"] = np.arange(len(df)) % 4            # Z at four levels, k = 3
    with pytest.raises(EstimatorFailure) as caught:
        _estimate(df)
    assert caught.value.failure_type == Refusal.PROXY_CARDINALITY_MISMATCH
    # And the errand survives: declaring the fold reaches the number.
    got = _estimate(df, coarsening=ProxyCoarsening(
        treatment_proxy=((0, 1), (2,), (3,)),
        outcome_proxy=((0,), (1,), (2,)),
    ))
    assert got.method == "proximal_matrix" and got.point is not None


def test_a_test_that_cannot_run_returns_the_refusal_it_was_offered_for():
    """The fallback is an OFFER, and a failed offer leaves what was true.

    Here the channel is exactly singular AND the frame is far too thin for
    the test's cells. Letting the test's own complaint out would replace the
    finding the caller asked about — the channel will not invert — with a
    fact about a fallback they never requested.
    """
    import itertools

    rows = []
    for x, z, w in itertools.product([False, True], repeat=3):
        rows.extend({"x": x, "y": bool(x and w), "z": z, "w": w}
                    for _ in range(8))
    with pytest.raises(EstimatorFailure) as caught:
        _estimate(pd.DataFrame(rows), k=2)
    assert caught.value.failure_type == Refusal.RANK_CONDITION_VIOLATED


def test_a_declared_fold_on_the_outcome_proxy_is_used_by_the_test():
    """And once the fold is declared, the test runs on the folded proxy.

    Checked by its consequence rather than by reading the record back: the
    fold changes how many coefficients there are and how many degrees of
    freedom are left, so a fold that was ignored would show up as γ of length
    six against the declared three.
    """
    df = _sample(30_000, 0.0, 7, fine_z=True, arms=3, split_w=True)
    got = _estimate(df, coarsening=ProxyCoarsening(
        treatment_proxy=((0,), (1,), (2,)),
        outcome_proxy=((0, 1), (2, 3), (4, 5)),
    ))
    assert got.method == "proximal_null_test"
    assert len(got.no_effect_test["coefficients"]) == _K
    assert got.no_effect_test["degrees_of_freedom"] == 3 * 3 - _K
    # The unfolded proxy would have solved for six coefficients and left
    # three degrees of freedom — a different test, on a different channel.
    raw = run_the_test(df, xcol="x", ycol="y", zcol="z", wcol="w")
    assert len(raw.coefficients) == 6 and raw.degrees_of_freedom == 3


# --- the two refusals the test raises on its own ------------------------------

def test_a_channel_with_nothing_left_over_cannot_be_tested():
    """``ij ≥ k + 1`` or there is no restriction to test.

    Two arms and a binary Z against a FOUR-state latent leaves ij = 4 and
    k = 4: γ can fit any four numbers exactly, so the residual is zero by
    construction and a statistic computed from it would be zero whatever the
    data said. Refusing is the only honest reading — a test with no degrees
    of freedom is not a test that passed.
    """
    df = _sample(30_000, 0.0, 7)
    # W at four levels: its lowest is split by a fair coin and the other two
    # shift up, so the proxy takes as many values as there are cells.
    df["w"] = np.where(df["w"] == 0, df.index % 2, df["w"] + 1)
    with pytest.raises(EstimatorFailure) as caught:
        run_the_test(df, xcol="x", ycol="y", zcol="z", wcol="w")
    assert (caught.value.failure_type
            == Refusal.NO_DEGREES_OF_FREEDOM_TO_TEST_THE_NULL)
    assert caught.value.details["moments"] == 4
    assert caught.value.details["unknowns"] == 4


def test_a_proxy_that_repeats_itself_leaves_the_stack_rank_deficient():
    """The stacked channel has to have an independent row per state of U.

    Here ``W``'s levels 1 and 2 take exactly equal shares of every cell — the
    proxy reports three values and separates two states — so the stack cannot
    be solved for three coefficients. That is a different finding from "too
    few levels", and the refusal says so rather than reporting coefficients
    fitted to a channel that does not determine them.

    Built row by row rather than sampled, and that is the counterexample's
    whole point: exact collinearity is what this gate is for. Draw the same
    structure at random and the two columns differ by sampling noise, the
    numerical rank comes back full, and nothing fires — which is why the
    condition-number gate exists beside this one and catches the near case.
    """
    rows = []
    for i, x in enumerate((0, 1, 2)):
        for j, z in enumerate((0, 1)):
            leading = 40 + 10 * i + 20 * j
            for level, count in ((0, leading), (1, 30), (2, 30)):
                rows.extend((x, z, level, r % 2) for r in range(count))
    df = pd.DataFrame(rows, columns=["x", "z", "w", "y"])
    with pytest.raises(EstimatorFailure) as caught:
        run_the_test(df, xcol="x", ycol="y", zcol="z", wcol="w")
    assert (caught.value.failure_type
            == Refusal.STACKED_CHANNEL_IS_RANK_DEFICIENT)
    assert caught.value.details["needed"] == _K


def test_a_cell_with_almost_no_rows_is_refused_rather_than_averaged():
    df = _sample(4_000, 0.0, 7)
    keep = ~((df["x"] == 1) & (df["z"] == 1))
    thin = pd.concat([df[keep], df[~keep].head(5)], ignore_index=True)
    with pytest.raises(EstimatorFailure) as caught:
        run_the_test(thin, xcol="x", ycol="y", zcol="z", wcol="w")
    assert caught.value.failure_type == Refusal.INSUFFICIENT_SUPPORT


# --- D1 prong 3: the envelope, and the verifier that re-runs it ---------------

def test_the_envelope_carries_the_test_and_no_effect_size(answered):
    ne = answered["null"]["numeric_estimate"]
    assert ne["method"] == "proximal_null_test"
    for absent in ("point", "ci_lower", "ci_upper",
                   "do_prob_treated", "do_prob_control"):
        assert absent not in ne, absent
    test = ne["no_effect_test"]
    assert set(test) == {"statistic", "degrees_of_freedom", "p_value",
                         "coefficients"}
    assert test["statistic"] >= 0
    assert 0.0 <= test["p_value"] <= 1.0
    assert len(test["coefficients"]) == _K


def test_the_two_runs_disagree_about_the_null(answered):
    assert answered["null"]["numeric_estimate"]["no_effect_test"][
        "p_value"] > 0.05
    assert answered["effect"]["numeric_estimate"]["no_effect_test"][
        "p_value"] < 0.001


def test_the_recorded_cells_re_derive_the_statistic(answered):
    """The verifier's own arithmetic, run here against the producer's.

    The cells are the sufficient statistics, so this is the identity the
    verifier rests on: nothing about the statistic is taken on trust.
    """
    for run in answered.values():
        step = _step(run)
        cells = step["inputs"]["measurement_channel"]["items"]["cells"]
        statistic, rank, _ = solve_null_test(_plain(cells))
        test = run["numeric_estimate"]["no_effect_test"]
        n = run["numeric_estimate"]["sample_size"]
        assert statistic * n == pytest.approx(test["statistic"])
        assert len(_plain(cells)) - rank == test["degrees_of_freedom"]


def test_the_envelope_verifies(answered):
    for run in answered.values():
        themis.verify(_program(), run)
        themis.audit(_program(), run)


def _step(result: dict) -> dict:
    steps = result["derivation"]["steps"]
    (step,) = [s for s in steps if s["rule"] == _STEP]
    return step


def _plain(serialised) -> tuple[dict, ...]:
    """The cells as the solver takes them, out of the tagged wire form."""
    def value(v):
        if isinstance(v, dict) and v.get("kind") in ("tuple", "value_tuple"):
            return tuple(value(i) for i in v["items"])
        if isinstance(v, dict) and v.get("kind") == "dict":
            return {k: value(i) for k, i in v["items"].items()}
        return v
    return tuple(value(c) for c in serialised["items"])


@pytest.mark.parametrize("key,forged", [
    ("statistic", 0.001),
    ("degrees_of_freedom", 4),
    ("p_value", 0.999),
])
def test_a_moved_answer_is_caught(answered, key, forged):
    """Each reported number is re-derived, so each can be disagreed with.

    ``p_value`` matters most and is the one a metadata audit would have let
    through: it is a number in [0, 1] with no shape to be wrong, so nothing
    but recomputing it from the cells can tell a real one from a written one.
    """
    run = copy.deepcopy(answered["effect"])
    _step(run)["inputs"]["no_effect_test"]["items"][key] = forged
    with pytest.raises(VerificationError):
        themis.verify(_program(), run)


def test_a_moved_cell_is_caught(answered):
    """The sharpest gate: the ANSWER is untouched and a cell has moved.

    Every number the producer reported still agrees with every other number
    it reported. Only re-solving the test from the cells sees it — which is
    why the cells travel and the statistic is not merely audited.
    """
    run = copy.deepcopy(answered["effect"])
    cells = _step(run)["inputs"]["measurement_channel"]["items"]["cells"]
    first = cells["items"][0]["items"]
    # Moved together, so the cell still holds E[Y²] ≥ E[Y]² and its parts
    # still sum to its whole: the arithmetic gates pass and only re-solving
    # the test sees the change.
    first["mean_y"] += 0.05
    first["mean_y_w"]["items"][0] += 0.05
    first["mean_yy"] += 0.20
    with pytest.raises(VerificationError, match="re-solving the null"):
        themis.verify(_program(), run)


def test_a_cell_that_stopped_being_a_distribution_is_caught(answered):
    """The cells are checked against each other before they are solved.

    A producer who moved P(W) to move the statistic has to leave a cell whose
    probabilities do not sum to one, and that is caught without solving
    anything — which is what keeps the re-derivation from being handed a
    table it would faithfully reproduce a wrong answer from.
    """
    run = copy.deepcopy(answered["null"])
    cells = _step(run)["inputs"]["measurement_channel"]["items"]["cells"]
    cells["items"][0]["items"]["p_w"]["items"][0] += 0.2
    with pytest.raises(VerificationError, match="P\\(W\\) sums to"):
        themis.verify(_program(), run)


# --- D1 prong 4: what the reader is told --------------------------------------

def test_the_gap_says_the_question_shrank(answered):
    (gap,) = [g for g in answered["null"]["data_gap_report"]["gaps"]
              if g["kind"] == "answer_is_a_test_not_an_effect_size"]
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "point_estimate"
    assert {s["sentence"] for s in gap["describes"]} == {
        "the_proxies_show_fewer_states_than_the_latent_has",
        "a_test_of_the_null_is_what_is_left",
    }
    assert [r["route"] for r in gap["alternative_paths"]] == [
        "enrich_a_proxy_to_get_a_number"]


def test_the_tier_does_not_promise_a_number(answered):
    """A run that produced an answer is reconciled to ``point`` unless it
    says otherwise, and this one has to say otherwise: there is no point and
    no interval, so the strongest answer on the estimand's own scale is none.
    """
    assert answered["null"]["data_gap_report"]["answer_tier"] == "none"


def test_a_polytomous_treatment_is_sent_to_the_bridge_channel():
    """The other branch of the gap, and it points somewhere Themis can go.

    Where the arms are what blocked the number, the errand is not a better
    proxy — the channel is fine — it is a channel that answers with a curve.
    """
    envelope = themis.estimate(
        _program(z_levels=(0, 1, 2)),
        _sample(30_000, 0.0, 7, fine_z=True, arms=3), ci_bootstrap=0)
    result = envelope["results"][0]
    (gap,) = [g for g in result["data_gap_report"]["gaps"]
              if g["kind"] == "answer_is_a_test_not_an_effect_size"]
    assert {s["sentence"] for s in gap["describes"]} == {
        "the_discrete_contrast_needs_two_arms",
        "a_test_of_the_null_is_what_is_left",
    }
    assert [r["route"] for r in gap["alternative_paths"]] == [
        "use_a_bridge_channel_for_more_than_two_arms"]


@pytest.mark.parametrize("lang,shape,rejected,survived", [
    ("zh", "有没有效应", "**拒绝**", "**没有拒绝**"),
    ("en", "test of whether there is an effect at all",
     "**rejects** no-effect", "does **not** reject no-effect"),
])
def test_both_readers_are_told_what_they_are_holding(
        answered, lang, shape, rejected, survived):
    """The two verdicts are not each other's negation, and the report says so.

    Rejecting establishes that an effect exists; failing to reject
    establishes nothing. A reader handed only "p = 0.12" supplies "so there
    is no effect" themselves, which is the misreading this shape exists to
    prevent — so the surviving-null wording is checked for saying what it
    does not establish, not merely for reporting the number.
    """
    under_null = build_analysis_report(answered["null"], lang=lang)
    under_effect = build_analysis_report(answered["effect"], lang=lang)
    for text in (under_null, under_effect):
        assert shape in text
    assert survived in under_null and rejected not in under_null
    assert rejected in under_effect and survived not in under_effect
    # The p-value the envelope carries is the p-value the reader is shown.
    for text, run in ((under_null, "null"), (under_effect, "effect")):
        p = answered[run]["numeric_estimate"]["no_effect_test"]["p_value"]
        assert f"{p:.4g}" in text


def test_no_reader_is_shown_an_effect_size(answered):
    """Nothing on the page offers a magnitude, in either language.

    The point-estimate vocabulary is what a surface reaches for when it finds
    a number and does not ask what kind — so its absence is the check that
    the shape travelled, rather than the renderer happening to be right.
    """
    for lang, forbidden in (
        ("zh", ("效应量为", "点估计为", "置信区间")),
        ("en", ("the effect is estimated at", "confidence interval")),
    ):
        text = build_analysis_report(answered["null"], lang=lang)
        for phrase in forbidden:
            assert phrase not in text, (lang, phrase)
