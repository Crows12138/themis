"""A user says exercise and mood affect each other. A DAG cannot hold that.

What used to happen: the LLM wrote `reciprocal_causation` into
`extensions.ambiguities`, the kernel echoed the string back, and then
answered the one direction that had been drawn — with the same confidence
as any other back-door estimate.

The root cause was not a missing handler. It was that **the declaration
carried no referent**: `{"kind": "reciprocal_causation", "description":
"运动和心情互相影响"}` names no atoms, so no handler could be written for
it. Hence a first-class statement.

The statement adds no edge — the graph stays a DAG — and what it does is
WITHDRAW. Under a loop the treatment is not exogenous, and adjustment
cannot fix that: controlling for a covariate blocks a path, and a feedback
the treatment is part of is not a path to block. The front-door escape is
gone one step down, because every mediator on an X-to-Y path is inside the
loop.

One route survives, and only on one shape. `Y = bX + u` beside
`X = gY + dZ + v` reduces to `Cov(Z,Y)/Cov(Z,X) = b` (Haavelmo 1943), so an
instrument still identifies the coefficient of X in the Y equation —
under linearity, which is what keeps d-separation valid on a cyclic graph
(Spirtes 1995, UAI-11). Without linearity a cyclic SCM need not have a
solution or a unique interventional distribution at all (Bongers, Forré,
Peters & Mooij 2021, Ann. Statist. 49(5):2885-2915), which is why the
premise is stated to the reader rather than assumed.

The oracle below is that system, simulated. Its point is not that the new
number is close to the truth but that **the old one is not**: the
adjustment answer and the truth differ by more than any noise here, and
which of the two Themis reports turns on one statement in the program.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import gaps, routing
from themis.input.semantic_validator import SemanticError
from themis.verifier import VerificationError

#: The system, written down before it is measured.
BETA, GAMMA, DELTA = 1.5, 0.4, 2.0


def _atom(predicate, *, time=None):
    out = {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}
    if time is not None:
        out["time_index"] = {"kind": "relative", "value": time}
    return out


def _program(*statements, treatment="x", outcome="y"):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *statements,
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom(treatment), "value": True},
                "target": {"atom": _atom(outcome), "value": True},
                "given": [],
            }},
        ],
    }


def _simultaneous(*, loop: bool, instrument: bool = True):
    """Z -> X -> Y, with X and Y declared to move each other."""
    statements = [
        {"kind": "variable", "predicate": "x", "scale": "continuous"},
        {"kind": "variable", "predicate": "y", "scale": "continuous"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
    ]
    if instrument:
        statements[:0] = [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
        ]
        statements.append(
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")})
    if loop:
        statements.append(
            {"kind": "feedback", "left": _atom("x"), "right": _atom("y")})
    return _program(*statements)


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    """Draws from the two-equation system, through its reduced form."""
    rng = np.random.default_rng(0)
    n = 6000
    u, v = rng.standard_normal(n), rng.standard_normal(n)
    z = (rng.random(n) < 0.5).astype(float)
    denom = 1.0 - BETA * GAMMA
    return pd.DataFrame({
        "z": z > 0.5,
        "x": (DELTA * z + v + GAMMA * u) / denom,
        "y": (BETA * DELTA * z + BETA * v + u) / denom,
    })


def _answer(program, frame):
    out = themis.estimate(program, frame, ci_bootstrap=0)
    return out["results"][0]


def _refused(program, frame) -> str:
    with pytest.raises(SemanticError) as raised:
        themis.estimate(program, frame, ci_bootstrap=0)
    return str(raised.value)


def _gap(result, kind):
    for entry in (result.get("data_gap_report") or {}).get("gaps", []):
        if entry.get("kind") == kind:
            return entry
    raise AssertionError(
        f"no {kind} gap; got "
        f"{[g.get('kind') for g in (result.get('data_gap_report') or {}).get('gaps', [])]}"
    )


# --- the oracle ---------------------------------------------------------------

def test_one_statement_decides_which_of_two_numbers_is_reported(frame):
    """The whole feature, as one comparison.

    Same data, same graph, same query. With the loop undeclared the answer
    is the adjustment number, which the simultaneity biases away from the
    truth. With it declared the answer is the Wald ratio, which is the
    truth. Neither number is noisy enough for the difference to be one.
    """
    silent = _answer(_simultaneous(loop=False), frame)
    declared = _answer(_simultaneous(loop=True), frame)

    assert silent["numeric_estimate"]["method"] == "backdoor_linear"
    assert declared["numeric_estimate"]["method"].startswith("iv_")

    biased = silent["numeric_estimate"]["point"]
    recovered = declared["numeric_estimate"]["point"]
    assert recovered == pytest.approx(BETA, abs=0.02)
    assert abs(biased - BETA) > 0.05
    assert abs(biased - recovered) > 0.05


def test_the_recovered_number_is_the_wald_ratio_and_nothing_else(frame):
    """Not "close to the truth" — the exact statistic, so that a future
    estimator change cannot pass this by being differently approximate."""
    z = frame["z"].to_numpy()
    hand = ((frame["y"][z].mean() - frame["y"][~z].mean())
            / (frame["x"][z].mean() - frame["x"][~z].mean()))
    point = _answer(_simultaneous(loop=True), frame)["numeric_estimate"]["point"]
    assert point == pytest.approx(hand, rel=1e-9)


def test_the_answer_says_which_routes_the_loop_took_away(frame):
    """A reader looking at an instrumental-variable estimate on a graph
    whose back-door set is plainly sitting there must be able to learn that
    the set was withdrawn rather than overlooked."""
    block = _answer(_simultaneous(loop=True), frame)["extensions"]["feedback_loop"]
    assert block["reduction"] == "simultaneous_equations"
    assert set(block["withdrew"]) == {"backdoor", "frontdoor", "general_id"}
    assert {block["left"], block["right"]} == {"x(me)", "y(me)"}


def test_the_reader_is_told_the_quantity_changed(frame):
    """A structural coefficient and an interventional contrast are the same
    number of digits, so the substitution has to be said, in both
    languages."""
    gap = _gap(_answer(_simultaneous(loop=True), frame),
               "iv_identification_assumption_required")
    for lang, needle in (("zh", "结构系数"), ("en", "structural coefficient")):
        assert needle in gaps.described(gap, lang)


def test_a_declared_loop_is_not_a_declared_common_cause(frame):
    """The distinction the whole statement exists for.

    `bidirected` says an unobserved common cause; `feedback` says both
    directions are causal. They coincide on one thing — the treatment is
    not exogenous — and on nothing else, so they must not be one statement.
    Here the arithmetic even agrees, and the ESTIMANDS still differ: one is
    a complier contrast, the other the outcome equation's coefficient.
    """
    latent = _simultaneous(loop=False)
    latent["statements"].insert(-1, {
        "kind": "bidirected", "left": _atom("x"), "right": _atom("y")})

    confounded = _answer(latent, frame)
    looped = _answer(_simultaneous(loop=True), frame)
    assert confounded["numeric_estimate"]["point"] == pytest.approx(
        looped["numeric_estimate"]["point"], rel=1e-9)
    assert "feedback_loop" not in (confounded.get("extensions") or {})
    assert "feedback_loop" in looped["extensions"]


# --- what the loop does to a query it does not reach --------------------------

def test_a_loop_that_reaches_neither_end_leaves_the_query_alone(frame):
    """Otherwise the declaration would be too expensive to make, and a
    reader would learn to leave it out — which is the silence this exists
    to end."""
    apart = _simultaneous(loop=False)
    apart["statements"].insert(-1, {
        "kind": "variable", "predicate": "p", "scale": "continuous"})
    apart["statements"].insert(-1, {
        "kind": "variable", "predicate": "q", "scale": "continuous"})
    apart["statements"].insert(-1, {
        "kind": "cause", "from": _atom("y"), "to": _atom("p")})
    apart["statements"].insert(-1, {
        "kind": "feedback", "left": _atom("p"), "right": _atom("q")})

    data = frame.assign(p=frame["y"] * 0.5, q=frame["y"] * 0.25)
    result = _answer(apart, data)
    assert result["numeric_estimate"]["method"] == "backdoor_linear"
    assert "feedback_loop" not in (result.get("extensions") or {})


def test_a_loop_on_the_path_but_not_between_the_two_ends_refuses(frame):
    """The shape with no remedy, and the honesty is in not offering one.

    The two-equation algebra is about TWO equations. Borrowing it for a
    loop between the treatment and a mediator would be inventing a result,
    so this says what it is instead: a cyclic model need not define the
    quantity at all.
    """
    through = _program(
        {"kind": "variable", "predicate": "x", "scale": "continuous"},
        {"kind": "variable", "predicate": "m", "scale": "continuous"},
        {"kind": "variable", "predicate": "y", "scale": "continuous"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "feedback", "left": _atom("m"), "right": _atom("y")},
    )
    data = frame.assign(m=frame["x"] * 0.5 + 1.0)
    result = _answer(through, data)

    assert result["status"] == "needs_investigation"
    assert result.get("numeric_estimate") is None
    gap = _gap(result, "feedback_loop_reaches_the_estimand")
    assert gap["severity"] == "blocking"
    for lang, needle in (("zh", "有环的模型可能根本没有解"),
                         ("en", "need not have a solution")):
        assert needle in gaps.described(gap, lang)


def test_with_no_instrument_the_gap_names_the_one_thing_that_would_close_it(
        frame):
    """The distance travelled from an echoed string: a blocking gap whose
    routes a reader can act on, in their own language."""
    result = _answer(_simultaneous(loop=True, instrument=False),
                     frame.drop(columns=["z"]))
    assert result["status"] == "needs_investigation"
    assert result.get("numeric_estimate") is None

    gap = _gap(result, "missing_iv_candidate")
    assert gap["severity"] == "blocking"
    ways = {way["route"] for way in gap["alternative_paths"]}
    assert {"name_an_instrument_for_the_treatment",
            "resolve_the_loop_in_time",
            "withdraw_the_declared_loop"} <= ways
    for lang in ("zh", "en"):
        assert gaps.described(gap, lang).strip()
        for way in gap["alternative_paths"]:
            assert gaps.went(way, lang).strip()


# --- what the program will not say --------------------------------------------

def test_a_loop_across_two_time_steps_is_refused(frame):
    """The gate worth having, and it hands the reader a stronger model than
    the one they wrote.

    `a` at t moving `b` at t+1 moving `a` at t+2 is three ordinary edges in
    an acyclic graph. Declaring it here instead throws away the resolution
    that makes the effect identifiable WITHOUT an instrument.
    """
    lagged = _simultaneous(loop=False)
    lagged["statements"].insert(-1, {
        "kind": "feedback",
        "left": _atom("x", time=-1), "right": _atom("y")})
    said = _refused(lagged, frame)
    assert "not a cycle" in said
    assert "identifiable without an instrument" in said


def test_a_loop_with_one_end_is_refused(frame):
    same = _simultaneous(loop=False)
    same["statements"].insert(-1, {
        "kind": "feedback", "left": _atom("x"), "right": _atom("x")})
    assert "both ends name" in _refused(same, frame)


# --- what the audit says no to ------------------------------------------------

def test_a_withdrawal_citing_a_loop_nobody_declared_is_refused(frame):
    """The forgery this licence exists to stop.

    Every other structural licence says an estimand IS reachable; this one
    says a set of them are NOT, and that is worth forging: it replaces a
    correct back-door answer with an instrumental-variable one resting on
    linearity. So the loop is re-derived from the PROGRAM, and a step that
    cites one the statements do not carry cannot vouch for itself.
    """
    program = _simultaneous(loop=True)
    result = _answer(program, frame)
    stripped = copy.deepcopy(program)
    stripped["statements"] = [s for s in stripped["statements"]
                              if s["kind"] != "feedback"]
    with pytest.raises(VerificationError, match="declares no feedback loop"):
        themis.verify(stripped, result)


def test_a_withdrawal_by_a_loop_that_touches_neither_end_is_refused(frame):
    """The other half: a loop the program really declares, cited on a query
    it cannot influence.

    Both loops are in the same program and the graph is the same either
    way, so what is being tested is the reach rule alone — a step that
    points at the wrong one of two real declarations. Nothing was
    withdrawn, so nothing licensed the escalation.
    """
    program = _simultaneous(loop=True)
    for predicate in ("p", "q"):
        program["statements"].insert(-1, {
            "kind": "variable", "predicate": predicate, "scale": "continuous"})
    program["statements"].insert(-1, {
        "kind": "cause", "from": _atom("p"), "to": _atom("q")})
    program["statements"].insert(-1, {
        "kind": "feedback", "left": _atom("p"), "right": _atom("q")})

    data = frame.assign(p=frame["x"] * 0.0 + 1.0, q=frame["x"] * 0.0 + 2.0)
    result = _answer(program, data)
    themis.verify(program, result)

    doctored = copy.deepcopy(result)
    for step in doctored["derivation"]["steps"]:
        if step["rule"] == "feedback_loop_withdraws_adjustment":
            step["inputs"]["left"] = {"kind": "atom", **_atom("p")}
            step["inputs"]["right"] = {"kind": "atom", **_atom("q")}
    with pytest.raises(VerificationError, match="influence neither"):
        themis.verify(program, doctored)


def test_the_truthful_answer_verifies(frame):
    """The denominator. A rule that refused everything would refuse both
    forgeries above and mean nothing by it."""
    program = _simultaneous(loop=True)
    themis.verify(program, _answer(program, frame))


# --- the table -----------------------------------------------------------------

def test_the_loop_row_outranks_every_row_that_computes_from_a_dag():
    """Precedence is not a preference here. Every row below computes an
    estimand from a DAG; this row is the statement that the DAG is missing
    an edge it cannot hold."""
    loop = routing.route("feedback_loop")
    assert all(loop.precedence < other.precedence
               for other in routing.EFFECT_ROUTES if other.id != loop.id)
    assert loop.triggered_by == "feedback"


def test_the_loop_row_declares_what_it_takes_the_query_away_from():
    """A displacement nobody can see is indistinguishable from an error,
    which is what `displaces` is for."""
    assert routing.route("feedback_loop").displaces == frozenset({
        "joint_intervention", "transport",
        "mediation_joint", "mediation_single",
    })
