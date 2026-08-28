"""A continuous proxy is not a discrete one with too many levels.

Before #451 a proximal query whose proxies were continuous was sent down the
one road there was: the matrix regime asked for a ``k×k`` channel, found three
thousand distinct floats, and filed ``proxy_coarsening_undeclared`` — which
asks the caller to say which of those floats are the same state of a variable
nobody observed. The errand cannot be run, and it is the wrong errand: the
continuous regime does not bin the proxy, it solves for a bridge function.

The reason there was one road is that ``latent_cardinality`` was a required
field of the query and carried two facts at once — how many states U is
assumed to have, and that a matrix is what gets inverted. Those coincide in
the discrete regime and come apart in the continuous one, where U's
cardinality is not assumed at all. So the query carries a ``channel`` with two
shapes now, and this file is about what the second one owes a reader.

What it owes is the penalty. ``E[h(W, X) | Z, X] = E[Y | Z, X]`` is a Fredholm
equation of the first kind: ill-posed, no numeric solution without a
regularisation term, and that term moves the answer by an amount nothing in
the data settles. So the term is declared (a field), attributed (the ledger
says whether the caller chose it or nobody did), re-run (a ladder of four
penalties travels with the answer), and gated (where it moved the number
further than sampling noise does, a gap says so).

The sharpest gate here is the one that doctors a ladder rung. Every other
figure on the envelope stays true, the point is the point the moments give,
and the only thing that changed is the report of what a lighter penalty would
have said — which is precisely the claim "you can trust this number, it does
not depend on λ". Re-solving the rung is the only thing that sees it.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import SemanticError
from themis.verifier import VerificationError

_STEP = "numeric_proximal_bridge_estimate"

#: The truth the sample is built around. Read by every oracle below.
_BETA = 1.5


# --- the corpus ---------------------------------------------------------------

def _var(p, **kw):
    out = {"kind": "variable", "predicate": p}
    out.update(kw)
    return out


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _bridge(dimension=2, instruments=2, basis="polynomial", ridge=None) -> dict:
    out = {"kind": "bridge_function", "basis": basis,
           "dimension": dimension, "instrument_dimension": instruments}
    if ridge is not None:
        out["ridge"] = ridge
    return out


def _program(channel: dict) -> dict:
    """Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y, with U unobserved."""
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x", domain=[True, False]), _var("y", scale="continuous"),
            _var("u"), _var("z", scale="continuous"),
            _var("w", scale="continuous"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": _atom("z"), "outcome_proxy": _atom("w"),
                "channel": channel,
            }},
        ],
    }


def _sample(n: int = 4000, seed: int = 11) -> pd.DataFrame:
    """A latent-confounded SCM whose bridge is known in closed form.

    ``U`` is standard normal and unobserved; ``Z`` and ``W`` are noisy linear
    readings of it; treatment depends on ``U``; the outcome is
    ``1.5·X + U + ε``. The outcome bridge is then ``h(w, x) = βx + (τ/γ)w``
    exactly — check it by substituting: ``E[h(W,x) | Z, X=x]`` and
    ``E[Y | Z, X=x]`` both come to ``βx + τ·E[U | Z, X=x]``, whatever that
    conditional expectation is and however X depends on U.

    So the truth is not an approximation this file happens to land near. It
    is ``β``, the bridge is IN the span of a degree-1 polynomial basis, and
    the ``w`` term cancels between the two arms — which is why the contrast
    comes out at β regardless of what W's mean is.
    """
    rng = np.random.default_rng(seed)
    u = rng.normal(size=n)
    x = rng.random(n) < 1 / (1 + np.exp(-0.8 * u))
    return pd.DataFrame({
        "x": x,
        "y": _BETA * x + 1.0 * u + rng.normal(scale=0.5, size=n),
        "z": 1.2 * u + rng.normal(scale=0.7, size=n),
        "w": 0.9 * u + rng.normal(scale=0.7, size=n),
    })


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return _sample()


def _run(program: dict, frame: pd.DataFrame) -> dict:
    return themis.estimate(program, frame, ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def answered(frame) -> dict:
    return _run(_program(_bridge()), frame)


# --- reading and doctoring the record -----------------------------------------

def _step(result: dict) -> dict:
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step
    raise AssertionError(f"no {_STEP} step in this derivation")


def _channel(step: dict) -> dict:
    return step["inputs"]["measurement_channel"]["items"]


def _doctored(result: dict):
    forged = copy.deepcopy(result)
    step = _step(forged)
    return forged, step, _channel(step)


def _refused(forged: dict, program: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program, forged)
    return str(raised.value)


def _gaps(result: dict, kind: str) -> list[dict]:
    report = result.get("data_gap_report") or {}
    return [g for g in report.get("gaps", []) if g["kind"] == kind]


def _ledger(result: dict) -> list[dict]:
    block = (result.get("extensions") or {}).get("assumption_ledger") or {}
    return list(block.get("assumptions") or ())


def _line(result: dict, assumption_id: str) -> dict | None:
    for entry in _ledger(result):
        if entry.get("id") == assumption_id:
            return entry
    return None


# --- the errand that could not be run -----------------------------------------

def test_a_continuous_proxy_used_to_be_asked_to_declare_its_own_grouping(frame):
    """The defect, still reachable by asking for the discrete regime.

    Kept as a test rather than deleted, because it is not a bug in the matrix
    estimator: a matrix regime on three thousand distinct floats SHOULD refuse.
    What was wrong was that this was the only road, and the gate for that is
    the next test.
    """
    out = _run(_program({"kind": "discrete_channel",
                         "latent_cardinality": 2}), frame)
    assert (out.get("numeric_estimate") or {}).get("point") is None
    assert _gaps(out, "proxy_coarsening_undeclared"), (
        "the discrete regime on continuous columns still reports what it "
        "always reported")


def test_the_same_columns_now_have_a_road_that_does_not_bin_them(answered):
    """The cut. One field on the query, and the errand is gone."""
    assert _gaps(answered, "proxy_coarsening_undeclared") == []
    assert answered["numeric_estimate"]["method"] == "proximal_bridge"
    assert answered["numeric_estimate"]["point"] is not None


# --- the oracle ---------------------------------------------------------------

def test_the_bridge_recovers_an_effect_the_naive_route_gets_wrong(
        answered, frame):
    """The denominator for everything else.

    The naive comparison is what a reader would get without a proximal route
    at all: regress Y on X and read the slope. U is unobserved and confounds
    both, so that slope is biased away from β — and the size of that bias is
    what the two proxies are being asked to remove.
    """
    naive = float(np.polyfit(frame.x.astype(float), frame.y, 1)[0])
    point = answered["numeric_estimate"]["point"]
    assert abs(naive - _BETA) > 0.3, (
        f"premise: the naive slope {naive} has to be visibly confounded, or "
        f"this sample does not test anything")
    assert abs(point - _BETA) < 0.1, (
        f"the bridge recovered {point}, truth {_BETA}, naive {naive}")


def test_a_second_basis_family_lands_on_the_same_effect(frame):
    """Two sieves, one answer. A cross-check on the machinery rather than on
    the theory: the hat basis on quantile knots and the polynomial basis have
    no code in common past the cross-moments, so agreeing to within a tenth
    is evidence the columns are being built rather than fitted to."""
    hats = _run(_program(_bridge(dimension=3, instruments=3,
                                 basis="piecewise_linear")), frame)
    assert abs(hats["numeric_estimate"]["point"] - _BETA) < 0.15


def test_the_two_arms_are_the_two_do_probabilities_and_their_difference(
        answered):
    ne = answered["numeric_estimate"]
    assert ne["point"] == pytest.approx(
        ne["do_prob_treated"] - ne["do_prob_control"], rel=1e-12)


# --- the penalty is a choice, and the ledger says whose ------------------------

def test_a_penalty_nobody_named_is_attributed_to_nobody(answered):
    """The default branch. The line exists — a run without one would be a run
    whose penalty reached no reader — and it is NOT the caller's."""
    line = _line(answered, "regularisation_lambda_defaulted_by_the_estimator")
    assert line is not None, [e.get("id") for e in _ledger(answered)]
    assert line["provenance"] == "default"
    assert _line(answered, "regularisation_lambda_chosen_by_the_caller") is None


def test_a_penalty_the_caller_named_is_attributed_to_them(frame):
    """The other branch, and the distinction the ledger is for: the same
    arithmetic under two authors is not the same claim."""
    out = _run(_program(_bridge(ridge=0.5)), frame)
    line = _line(out, "regularisation_lambda_chosen_by_the_caller")
    assert line is not None, [e.get("id") for e in _ledger(out)]
    assert line["provenance"] == "caller_chose"


def test_the_sieve_is_the_callers_choice_in_either_branch(answered):
    """Where the bridge is assumed to live has no default at all — unlike the
    penalty beside it — so this line is the caller's on every run."""
    line = _line(answered, "the_bridge_lies_in_the_span_of_the_declared_sieve")
    assert line is not None
    assert line["provenance"] == "caller_chose"


# --- the gate on the penalty ---------------------------------------------------

def test_a_penalty_that_moves_the_answer_more_than_noise_does_is_reported(
        frame):
    """The finding this cut exists to be able to state.

    λ=0.5 is a legitimate thing for a caller to write and the estimator runs
    it without complaint — the number that comes back is a real number, and
    it is a quarter of an effect away from the one the data gives. That is
    the shape of an ill-posed problem, and the reader is told.
    """
    heavy = _run(_program(_bridge(ridge=0.5)), frame)
    found = _gaps(heavy, "regularisation_is_moving_the_answer")
    assert found, "a penalty doing the work has to reach the reader"
    assert found[0]["severity"] == "important"
    assert abs(heavy["numeric_estimate"]["point"] - _BETA) > 0.15, (
        "premise: this penalty has to actually move the answer")


def test_a_stabilising_penalty_is_not_reported_as_moving_anything(answered):
    """The counterexample the gate needs, and the reason the criterion is the
    BEND rather than the ladder's spread: a well-posed sieve at a tiny λ has
    the same ladder as a badly-posed one at the same λ, and condemning it
    would make the warning mean nothing."""
    assert _gaps(answered, "regularisation_is_moving_the_answer") == []


def test_the_finding_names_three_things_the_reader_can_do(frame):
    heavy = _run(_program(_bridge(ridge=0.5)), frame)
    routes = [r["route"]
              for r in _gaps(heavy, "regularisation_is_moving_the_answer")[0]
              ["alternative_paths"]]
    assert routes == ["name_a_lighter_penalty", "thin_the_sieve",
                      "read_the_penalty_ladder_as_the_answer"]


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_finding_reaches_a_reader_of_either_language(frame, lang):
    heavy = _run(_program(_bridge(ridge=0.5)), frame)
    report = themis.build_analysis_report(heavy, lang=lang)
    assert "λ" in report or "lambda" in report.lower()
    for fragment in ({"zh": ("不适定", "正则化")}
                     if lang == "zh" else
                     {"en": ("ill-posed", "regularisation")})[lang]:
        assert fragment in report, (lang, fragment)


# --- what the query may not say ------------------------------------------------

def test_fewer_moments_than_unknowns_is_refused_at_the_door(frame):
    """Not an ill-conditioned solve — an under-determined one. Refused where
    the program is read, because it is malformed rather than unlucky."""
    with pytest.raises(SemanticError, match="under-determined"):
        _run(_program(_bridge(dimension=4, instruments=2)), frame)


def test_a_sieve_the_data_cannot_tell_apart_is_refused_rather_than_solved(
        frame):
    """The other end. A polynomial basis of this degree on 4000 rows has
    columns the sample does not distinguish, and the estimator says so
    instead of returning whatever the penalty picks."""
    out = _run(_program(_bridge(dimension=14, instruments=14)), frame)
    assert (out.get("numeric_estimate") or {}).get("point") is None
    failure = out.get("estimator_failure") or {}
    assert failure.get("failure_type") in (
        "singular_design", "bridge_ill_posed_at_this_penalty"), failure
    # And it says WHICH solve gave out, not merely that one did — the two
    # blocks fail for different reasons and a caller thins a different thing.
    assert failure.get("details", {}).get("design") in (
        "bridge_instrument_moments", "bridge_outcome_moments"), failure


# --- the answer is re-derived, not described -----------------------------------

def test_a_truthful_estimate_verifies(answered, frame):
    """The denominator for the counterexamples below: an untouched envelope
    passes, so a refusal downstream is about what was moved."""
    themis.verify(_program(_bridge()), answered)


def test_the_record_is_moments_and_not_the_coefficients_they_solve_to(
        answered):
    """Why this channel can be checked at all.

    Recording θ would be recording the answer, and a reader checking the
    answer against itself learns nothing. What travels is second moments of
    the data — which have identities of their own, and from which θ at ANY
    penalty is re-derivable without the data.
    """
    channel = _channel(_step(answered))
    assert "theta" not in channel and "coefficients" not in channel
    for arm in ("treated", "control"):
        block = channel[arm]["items"]
        assert set(block) == {"n", "s_aa", "s_ab", "s_ay", "s_bb", "s_by", "yy"}


def test_a_forged_point_is_refused(answered, frame):
    forged, step, _ = _doctored(answered)
    step["inputs"]["point"] = 0.42
    assert "re-solving the bridge" in _refused(forged, _program(_bridge()))


def test_a_forged_do_arm_is_refused(answered, frame):
    forged, step, _ = _doctored(answered)
    step["inputs"]["do_prob_treated"] += 0.3
    assert "do_prob_treated" in _refused(forged, _program(_bridge()))


def test_a_cross_moment_block_moved_is_refused(answered, frame):
    """The first stage is taken again here, so a moved moment moves θ.

    ``s_ay`` and not ``s_ab`` on purpose: it enters ``c`` and leaves ``G``
    alone, so the recorded scale, the ladder's penalties and the condition
    numbers all still check out and the ONLY thing that fails is the answer.
    Moving ``s_ab`` would be caught too, one identity earlier, and would
    therefore not show that the solve itself is re-run.
    """
    forged, _, channel = _doctored(answered)
    moments = channel["treated"]["items"]["s_ay"]["items"]
    moments[0] = moments[0] + 0.05
    assert "re-solving the bridge" in _refused(forged, _program(_bridge()))


def test_a_first_stage_moment_moved_is_caught_one_identity_earlier(
        answered, frame):
    """Its sibling, and the reason the scale is checked at all.

    ``s_ab`` enters ``G``, so moving it moves tr(G)/d — and the default
    penalty and every ladder rung are fractions of that. A pass that read
    the recorded scale instead of re-deriving it would accept this and then
    re-solve at the doctored channel's own penalties, which is checking the
    forgery against itself.
    """
    forged, _, channel = _doctored(answered)
    row = channel["treated"]["items"]["s_ab"]["items"][0]["items"]
    row[0] = row[0] + 0.05
    assert "tr(G)/d" in _refused(forged, _program(_bridge()))


def test_an_asymmetric_second_moment_matrix_is_refused(answered, frame):
    """``AᵀA/n`` is symmetric for every design there is, so a table that is
    not is not a design — caught before any arithmetic rests on it."""
    forged, _, channel = _doctored(answered)
    rows = channel["treated"]["items"]["s_aa"]["items"]
    rows[0]["items"][1] = rows[0]["items"][1] + 1.0
    assert "not symmetric" in _refused(forged, _program(_bridge()))


def test_a_channel_from_another_sample_is_refused(answered, frame):
    forged, _, channel = _doctored(answered)
    channel["n_total"] = channel["n_total"] + 1
    assert "not the same sample" in _refused(forged, _program(_bridge()))


def test_a_sieve_other_than_the_one_asked_for_is_refused(answered, frame):
    """The tie to the QUERY. Everything else here is the record agreeing with
    itself, which a record of a different sieve would also do."""
    forged, _, channel = _doctored(answered)
    channel["w_basis"]["items"]["family"] = "piecewise_linear"
    assert "the bridge is assumed to lie among" in _refused(
        forged, _program(_bridge()))


def test_a_penalty_that_does_not_follow_from_the_declaration_is_refused(
        answered, frame):
    """λ is not free-floating: with nothing declared it is a fixed fraction
    of the problem's own scale, and that scale is re-derived from the same
    moments the answer came out of."""
    forged, _, channel = _doctored(answered)
    channel["ridge"] = channel["ridge"] * 3
    assert "where the declaration and the recorded scale give" in _refused(
        forged, _program(_bridge()))


def test_claiming_the_caller_chose_a_penalty_they_did_not_is_refused(
        answered, frame):
    """Who chose λ is what the ledger attributes, so it is not the producer's
    to restate differently — a run that flipped this flag would launder its
    own default into the reader's choice."""
    forged, _, channel = _doctored(answered)
    channel["ridge_was_declared"] = True
    assert "who chose" in _refused(forged, _program(_bridge()))


def test_a_ladder_rung_rewritten_to_look_stable_is_refused(frame):
    """The sharpest one, and the reason the ladder is re-walked.

    Take the run where the penalty IS doing the work, and rewrite the
    least-penalised rung to agree with the point. Nothing else changes: the
    moments are the moments, the point is what they give at the λ in force,
    every arithmetic identity between the recorded figures still holds. What
    the doctored envelope now says is "a lighter penalty gives the same
    answer" — the one claim that would make the warning unnecessary, and the
    one claim no amount of internal consistency can check.
    """
    program = _program(_bridge(ridge=0.5))
    heavy = _run(program, frame)
    forged, _, channel = _doctored(heavy)
    point = _step(forged)["inputs"]["point"]
    for rung in channel["penalty_ladder"]["items"]:
        rung["items"]["point"] = point
    assert "re-solving at" in _refused(forged, program)


def test_a_rung_reported_as_unsolvable_where_it_solves_is_refused(
        answered, frame):
    """The other direction on the same field. An unsolved rung is the
    STRONGER claim — this problem is so ill-posed that a lighter penalty has
    no solution — and manufacturing one would manufacture the warning that
    excuses the number."""
    forged, _, channel = _doctored(answered)
    channel["penalty_ladder"]["items"][0]["items"]["point"] = None
    assert "the recorded moments solve there" in _refused(
        forged, _program(_bridge()))


def test_a_ladder_on_penalties_of_its_own_choosing_is_refused(
        answered, frame):
    """The rungs are fractions of the problem's own scale, fixed by the
    estimator. A ladder that moved them would measure a different problem and
    report the spread of that one."""
    forged, _, channel = _doctored(answered)
    rung = channel["penalty_ladder"]["items"][3]["items"]
    rung["fraction"] = 1e-3
    assert "a ladder with rungs of its own choosing" in _refused(
        forged, _program(_bridge()))
