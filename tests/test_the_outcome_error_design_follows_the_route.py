"""The outcome-error row prices the design that ANSWERS, not a design.

A declared σ²_v costs precision on a design, and which design decides three
separate things: which residual absorbs the noise, which conditioning set the
classical premise has to hold on, and whether the reported factor is exact or
a ceiling. So the row is only right if the design it selects is the one the
estimator ladder below it actually uses — which is why it selects on the same
facts, in the same order, and why these tests are all about the choice rather
than about the arithmetic (``tests/test_outcome_measurement_error.py`` owns
that).

The IV family is why the assessment is in two rows rather than one. Its
residual is taken around β̂, which IS the answer, so it cannot be priced
before the estimators run — while whether the DECLARATION can be true of the
sample at all must be settled before them, since that answer can stop the
query. The two halves sit on either side of the answer, and these tests pin
that each half sees the design the other did.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd

import themis
from themis.estimation.strategy import recording
from themis.input.syntactic_validator import validate_result
from themis import refusals

FRONTDOOR = (pathlib.Path(__file__).resolve().parents[1]
             / "themis" / "estimation" / "frontdoor.py")


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": []}


_QUERY = {
    "kind": "query", "id": "q",
    "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
    },
}

_DECLARED = {"y": {"error_variance": 0.5}}


def _program(*statements: dict) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [*statements, _QUERY],
    }


# --- the four shapes the guard has to tell apart ----------------------------


def _both_designs_program() -> dict:
    """c → x → m → y with c → y: back-door on {c} AND front-door on {m}.

    The one graph where the row's order is observable. Either design would
    produce a number here; only one of them produces THIS number.
    """
    return _program(
        {"kind": "variable", "predicate": "c", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y"},
        {"kind": "cause", "from": _atom("c"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
    )


def _both_designs_frame(n: int = 4000, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = rng.random(n) < 0.4
    x = rng.random(n) < (0.25 + 0.5 * c)
    m = rng.random(n) < (0.2 + 0.6 * x)
    y = 1.0 * m + 1.5 * c + rng.standard_normal(n)
    return pd.DataFrame({"c": c, "x": x, "m": m, "y": y})


def _front_door_program() -> dict:
    """x → m → y with x ↔ y latent: no adjustment set, one mediator."""
    return _program(
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    )


def _front_door_frame(n: int = 3000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = rng.random(n) < 1 / (1 + np.exp(-(2.0 * x.astype(float) - 1)))
    y = m.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _instrument_program() -> dict:
    """z → x → y with x ↔ y latent: no adjustment set, no mediator, one
    instrument — the design whose residual is defined around the answer."""
    return _program(
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "variable", "predicate": "z"},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    )


def _instrument_frame(n: int = 6000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    u = rng.standard_normal(n)
    x = 0.8 * z + u + rng.standard_normal(n)
    y_star = 0.5 * x + 2.0 * u + rng.standard_normal(n)
    return pd.DataFrame({"x": x, "y": y_star + rng.normal(0.0, 2.0, n), "z": z})


def _no_design_program() -> dict:
    """x → y with x ↔ y latent and nothing else: the bare bow arc. No
    adjustment set, no mediator, no instrument — a design outside the closed
    vocabulary, which the row has to LAND on rather than fall through."""
    return _program(
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    )


def _no_design_frame(n: int = 1500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    return pd.DataFrame({"x": x, "y": 1.0 * x + 2.0 * u + rng.standard_normal(n)})


def _continuous_mediator_frame(n: int = 3000, seed: int = 0) -> pd.DataFrame:
    """The front-door graph with M continuous — past the span the front-door
    outcome model can encode, and so past the span the assessment borrows."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = 0.8 * x.astype(float) + rng.standard_normal(n)
    return pd.DataFrame(
        {"x": x, "m": m, "y": 1.5 * m + 2.0 * u + rng.standard_normal(n)}
    )


def _estimate(program: dict, frame: pd.DataFrame, **kwargs) -> dict:
    return themis.estimate(
        program, frame, ci_bootstrap=0, measurement_error=_DECLARED, **kwargs,
    )["results"][0]


# --- the choice -------------------------------------------------------------


def test_a_graph_offering_two_designs_is_priced_on_the_one_that_answered():
    # The counterexample the front-door arm has to refuse: a graph that DOES
    # have a mediator satisfying the front-door criterion, where pricing the
    # front-door design would be arithmetically fine and still wrong — the
    # ladder answers on back-door, and the two designs condition on different
    # columns, so the same σ²_v buys a different factor on each.
    result = _estimate(_both_designs_program(), _both_designs_frame())

    assert result["numeric_estimate"]["method"].startswith("backdoor")
    block = result["outcome_error"]
    assert block["design_kind"] == "back_door"
    assert block["design_vars"] == ["x", "c"]
    assert not any("m" in name for name in block["design_vars"]), (
        "the mediator entered a design the estimator did not condition on"
    )


def test_the_front_door_query_is_priced_on_the_mediator_it_was_answered_through():
    # Same fact from the other side: with no adjustment set the row must not
    # fall back to the bare exposure, which is the design the previous
    # revision priced everything on.
    result = _estimate(_front_door_program(), _front_door_frame())

    numeric = result["numeric_estimate"]
    assert numeric["method"].startswith("frontdoor")
    block = result["outcome_error"]
    assert block["design_kind"] == "front_door"
    # One drop-first indicator per non-reference level, over the SAME mediator
    # set the estimator standardised across. Two records of that set would be
    # free to name different columns.
    assert block["design_vars"] == ["x", "m=True"]
    assert list(numeric["mediators"]) == ["m"]


def test_the_front_door_premise_about_the_unmeasured_confounder_is_declared():
    # The front-door graph POSITS an X-Y confounder. If the error depends on
    # it the point moves rather than the interval, and no data can say
    # whether it does — so the claim has to be on the record as a claim.
    block = _estimate(_front_door_program(), _front_door_frame())["outcome_error"]

    assert (
        "outcome_error_independent_of_the_front_door_latent_confounder_on_y"
        in block["assumptions"]
    )


def test_the_back_door_design_declares_no_latent_confounder_premise():
    # And it is a premise of the DESIGN, not of the channel: adding it
    # everywhere would put an unfalsifiable claim on the ledger of a query
    # that never made it.
    block = _estimate(_both_designs_program(), _both_designs_frame())["outcome_error"]

    assert not any("latent_confounder" in a for a in block["assumptions"])


# --- the design the row cannot price, and the one it has no name for --------


def test_the_instrument_design_is_priced_around_the_coefficient_that_shipped():
    # The gate this is really about. β̂ is the coefficient the structural
    # residual is taken around, and it IS the answer — so the assessment
    # cannot be made until the answer exists, and is made where it does. A
    # residual taken around an OLS projection instead would be a smaller
    # number about a model nobody fitted, wearing the IV name; a β̂
    # recomputed here would be a second copy of the shipped one.
    result = _estimate(_instrument_program(), _instrument_frame())

    block = result["outcome_error"]
    assert block["design_kind"] == "instrumental_variable"
    assert block["sufficient_statistics"]["design_coefficients"][0] == (
        result["numeric_estimate"]["point"]
    )
    # the instrument names the premise and is not a column of the design
    assert "z" not in block["design_vars"]
    assert any(
        "instrument_z" in a for a in block["assumptions"]
    ), block["assumptions"]
    assert result.get("estimator_failure") is None
    validate_result(result)


def test_a_continuous_mediator_is_priced_on_the_route_that_answered_it():
    """The fork the front door now has, followed on both sides of the answer.

    This used to be the one exit that recorded nothing: a mediator with no
    level set refused here about a COLUMN rather than about the declared
    variance, and the row stayed silent on the ground that the estimator two
    rows down would say the same thing in its own name. It no longer does —
    the front door answers such a query through its second plug-in — so a row
    that still refused would be pricing a design nobody was going to fit,
    and a row that still stayed silent would drop the assessment without
    saying it had.

    What must hold instead is the file's whole subject one route further
    along: the mediator enters the priced design the way the outcome model
    that answered read it, as a quantity and not as indicators over levels
    it does not have.
    """
    frame = _continuous_mediator_frame()
    quiet = themis.estimate(
        _front_door_program(), frame, ci_bootstrap=0,
    )["results"][0]
    declared = _estimate(_front_door_program(), frame)

    assert "estimator_failure" not in quiet
    assert quiet["numeric_estimate"]["method"] == "frontdoor_empirical_linear"
    block = declared["outcome_error"]
    assert block["design_kind"] == "front_door"
    assert block["design_vars"] == ["x", "m"], (
        "the mediator was expanded into indicators the outcome model that "
        "answered never fitted"
    )
    assert declared["numeric_estimate"]["point"] == (
        quiet["numeric_estimate"]["point"]
    ), "declaring an outcome error moved the point it only prices"


def test_a_design_outside_the_vocabulary_lands_rather_than_naming_an_instrument():
    # The fourth-design case, and the counterexample for the refusal text:
    # with no instrument the row must not borrow the IV sentence. It reaches
    # the same exit by a different route and has to say so — which is now the
    # species' own sentence rather than three composed at this exit, so what
    # the test holds is that the sentence names all three routes and that the
    # facts it turns on are this row's.
    result = _estimate(_no_design_program(), _no_design_frame())

    assert result.get("outcome_error") is None
    failure = result["estimator_failure"]
    assert failure["estimator"] == "outcome_measurement_error"
    assert failure["failure_type"] == "no_design_to_split_around"
    assert set(failure["details"]) == {"exposure", "outcome"}
    for tried in ("后门", "前门", "工具变量"):
        assert tried in refusals.said(failure), refusals.said(failure)
    validate_result(result)


def test_the_two_readings_of_one_mediator_are_told_apart_by_the_column():
    # The fork has to be taken on the DATA and not on the graph: these two
    # frames carry the same front-door graph and differ only in what the
    # mediator column holds, and the design has to follow the column. A row
    # that read the graph would price both the same way, and one of the two
    # would be a design nobody fitted.
    program = _program(
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    )
    rng = np.random.default_rng(2)
    n = 2000
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = 1.5 * x.astype(float) + rng.standard_normal(n)
    continuum = pd.DataFrame(
        {"x": x, "m": m, "y": m + 2.0 * u + rng.standard_normal(n)}
    )
    levelled = continuum.assign(m=(continuum["m"] > 0.75).astype(float))
    levelled["y"] = (levelled["m"] + 2.0 * u
                     + rng.standard_normal(n))

    priced_continuum = _estimate(program, continuum)["outcome_error"]
    priced_levels = _estimate(program, levelled)["outcome_error"]

    assert priced_continuum["design_vars"] == ["x", "m"]
    assert priced_levels["design_vars"] == ["x", "m=True"]


def test_a_mediator_with_too_many_levels_takes_the_same_fork():
    # The other half of what used to be the span check, and the reason the
    # fork asks about the SET rather than about one column's dtype. "Not
    # discrete" and "more levels than the sum can be taken over" were two
    # facts about a mediator and one fact about which plug-in can answer,
    # and a fork written for whichever of them came first would send this
    # frame — integer-valued, so the first is false about it — down a road
    # that enumerates a hundred strata.
    program = _program(
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
    )
    rng = np.random.default_rng(5)
    n = 2000
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = rng.integers(0, 100, size=n).astype(float)
    frame = pd.DataFrame(
        {"x": x, "m": m, "y": m + 2.0 * u + rng.standard_normal(n)}
    )

    silent = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    declared = _estimate(program, frame)

    assert silent["numeric_estimate"]["method"] == "frontdoor_empirical_linear"
    assert declared["outcome_error"]["design_vars"] == ["x", "m"]


def test_the_fork_is_asked_before_the_levels_are_taken_and_by_both_callers():
    """One question, asked where it can still be a decision.

    Read off the source rather than exercised, because what this holds is
    structural: the reader that takes a mediator's levels must not also
    judge them. While it judged, the judgement happened at the moment the
    levels were wanted — one step past the point where anything could be
    done about the answer — and every caller inherited a refusal it had to
    decide whether to own. Asked one step earlier the same fact routes, and
    the two callers that expand a mediator ask it themselves.
    """
    tree = ast.parse(FRONTDOOR.read_text(encoding="utf-8"))
    (reader,) = [node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "mediator_levels"]
    assert not [
        node for node in ast.walk(reader)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name) and node.value.id == "Refusal"
    ], "the levels reader judges the levels again"

    design = (pathlib.Path(__file__).resolve().parents[1]
              / "themis" / "estimation" / "outcome_error.py")
    build = [node for node in ast.walk(ast.parse(design.read_text("utf-8")))
             if isinstance(node, ast.FunctionDef) and node.name == "_build_design"]
    (build,) = build
    assert "exactly_summable" in {
        node.func.id for node in ast.walk(build)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }, "the priced design decides how to read a mediator on its own"


# --- what the row must never do, on any of the four -------------------------


def test_no_design_costs_the_caller_the_number_they_would_have_had():
    # The row annotates. Declaring what you know about your outcome may cost
    # you an assessment on a design nobody has built a split for; it may not
    # cost you the estimate, on any design.
    for program, frame in (
        (_both_designs_program(), _both_designs_frame()),
        (_front_door_program(), _front_door_frame()),
        (_instrument_program(), _instrument_frame()),
    ):
        silent = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
        declared = themis.estimate(
            program, frame, ci_bootstrap=0, measurement_error=_DECLARED,
        )["results"][0]

        assert silent["numeric_estimate"] is not None
        assert declared["numeric_estimate"] is not None
        assert declared["numeric_estimate"]["point"] == silent["numeric_estimate"]["point"]
        assert declared["numeric_estimate"]["method"] == silent["numeric_estimate"]["method"]
        assert declared["status"] == silent["status"]


def test_the_row_annotates_every_design_and_claims_none():
    # Selecting a design is not the same as owning the query, and the cascade
    # is the only place that distinction is observable.
    for program, frame in (
        (_both_designs_program(), _both_designs_frame()),
        (_front_door_program(), _front_door_frame()),
        (_instrument_program(), _instrument_frame()),
        (_no_design_program(), _no_design_frame()),
    ):
        with recording() as evaluations:
            themis.estimate(
                program, frame, ci_bootstrap=0, measurement_error=_DECLARED,
            )
        (evaluation,) = evaluations
        assert evaluation.fired is None or evaluation.fired[0] != (
            "outcome_error_precision_cost"
        )
        assert "outcome_error_precision_cost" not in dict(evaluation.declined)
