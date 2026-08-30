"""One route table, two layers (Phase 17 slices 2-3).

The chains this table replaced encoded three things in their own shape:
priority (source line order), what each guard tested (anything in scope,
including output the pass had already written), and what each number was
an estimate of (nothing — it was prose in a docstring). Both layers
encoded all three, separately, and the copies drifted five measured times.

These tests pin the properties that make that drift impossible rather than
merely detectable: the order is one object both layers hold, a guard can
only see facts, and a route with an end nobody implemented fails at import.
"""
from __future__ import annotations

import ast
import builtins
import pathlib

import pytest

import themis
from themis import routing
from themis.estimation.claim import annotated, answered, blocked, passed
from themis.estimation.dispatch import _EFFECT_STRATEGIES
from themis.estimation.strategy import (
    EffectFacts,
    Estimand,
    Evaluation,
    Role,
    Strategy,
    check_table,
    recording,
    run_cascade,
)
from themis.runtime.scheduler import _EFFECT_IDENTIFICATION

_ROUTING = pathlib.Path(themis.__file__).parent / "routing.py"
_SCHEDULER = pathlib.Path(themis.__file__).parent / "runtime" / "scheduler.py"


def _noop(f, r, k):
    return passed("not_identified")


def _row(id_, precedence, *, guard=lambda f: True, role=Role.CLAIM,
         produces=Estimand.QUERY_EFFECT, run=_noop, defers=()) -> Strategy:
    return Strategy(
        route=routing.Route(
            id=id_, precedence=precedence, applies_when=guard,
            ends=routing.ESTIMATES,
        ),
        role=role, produces=produces, run=run,
        defers_to=frozenset(defers),
    )


# --- the order is data ---------------------------------------------------


def test_two_rows_may_not_share_a_precedence():
    """A tie would be broken by declaration order — the thing precedence
    exists to replace."""
    with pytest.raises(ValueError, match="share precedence"):
        check_table((_row("a", 10), _row("b", 10)))


def test_two_rows_may_not_share_an_id():
    with pytest.raises(ValueError, match="duplicate strategy id"):
        check_table((_row("a", 10), _row("a", 20)))


def test_the_table_is_offered_in_precedence_order_not_declaration_order():
    table = check_table((_row("late", 20), _row("early", 10)))
    assert [s.id for s in table] == ["early", "late"]


def test_the_axis_is_one_axis_and_this_is_it():
    """Every strategy in either layer, in the one order both run.

    Reordering has to be a deliberate edit to this list rather than a side
    effect of moving code. The bands are visible in it: below 10 sits a
    premise that decides whether the question is well posed at all, 10-50
    route on the shape of the question, 60-140 belong to the data, 150-190
    are the structural ladder, and 200 up is past the ladder entirely —
    those rows say something ABOUT the answer rather than competing to be
    it.
    """
    assert [r.id for r in routing.EFFECT_ROUTES] == [
        "feedback_loop",
        "longitudinal",
        "joint_intervention",
        "transport",
        "mediation_joint",
        "mediation_single",
        "selection_recovery",
        "measurement_correction_both_channels",
        "measurement_correction_outcome",
        "measurement_correction_exposure",
        "outcome_error_declaration",
        "simex",
        "regression_calibration",
        "dose_response_binary_fallback",
        "dose_response_curve",
        "doubly_robust",
        "backdoor",
        "frontdoor",
        "general_id",
        "iv_overidentified",
        "iv_wald",
        "outcome_error_precision_cost",
    ]


def test_the_rows_past_the_ladder_are_exactly_the_ones_that_do_not_compete():
    """``after_the_answer`` is not a second name for "annotates".

    Most annotating rows still run in the race — they have everything they
    need before it starts, and running them there keeps one pass over the
    table. A row lands past the ladder only when what it says needs the
    answer to exist first, which is a stronger claim than not competing, and
    the two must not drift into each other.
    """
    late = [r.id for r in routing.EFFECT_ROUTES if r.after_the_answer]
    assert late == ["outcome_error_precision_cost"]
    assert all(
        r.precedence > 190 for r in routing.EFFECT_ROUTES if r.after_the_answer
    ), "a row that runs after the answer is ordered after the ladder too"


def test_a_row_past_the_ladder_may_not_produce_an_estimand():
    """The gate, and the input it must refuse.

    By the time such a row runs the query has been answered, so a row that
    produced an estimand there would be offering a second answer to a
    settled question — and ``precedence`` could not arbitrate, because the
    arbitration already happened.
    """
    late = routing.Route(
        id="late_claimer", precedence=900,
        applies_when=lambda f: True, ends=routing.ESTIMATES,
        after_the_answer=True,
    )
    with pytest.raises(ValueError, match="runs after the answer"):
        check_table((
            Strategy(
                route=late, role=Role.CLAIM, produces=Estimand.QUERY_EFFECT,
                run=lambda f, r, k: annotated(),
            ),
        ))


def test_both_layers_hold_the_same_route_object_not_a_copy():
    """The crux of slice 3. Two layers agreeing on an order used to be a
    property of two files that had to be compared by hand; three of the
    five measured defects were that comparison silently failing. Identity
    cannot fail silently."""
    identification = {r.id: r for r, _end in _EFFECT_IDENTIFICATION}
    estimation = {s.id: s.route for s in _EFFECT_STRATEGIES}
    shared = set(identification) & set(estimation)
    assert shared, "premise: the two layers implement some of the same rows"
    for route_id in shared:
        assert identification[route_id] is estimation[route_id], route_id


def test_the_shape_of_the_question_is_decided_before_the_graph_is_consulted():
    """A query naming both a mediator and a target population has ONE
    owner, and both layers now agree on which. While they disagreed, the
    estimation cascade could only reach transport by having mediation stand
    down first — a hand-off between different estimands, which is why it
    needed declaring."""
    order = {r.id: r.precedence for r in routing.EFFECT_ROUTES}
    assert order["transport"] < order["mediation_joint"]
    assert order["transport"] < order["mediation_single"]


def test_the_estimation_layer_runs_the_rows_it_has_a_numeric_end_for():
    assert [s.id for s in _EFFECT_STRATEGIES] == [
        "feedback_loop",
        "joint_intervention",
        "transport",
        "mediation_joint",
        "mediation_single",
        "selection_recovery",
        "measurement_correction_both_channels",
        "measurement_correction_outcome",
        "measurement_correction_exposure",
        "outcome_error_declaration",
        "simex",
        "regression_calibration",
        "dose_response_binary_fallback",
        "dose_response_curve",
        "doubly_robust",
        "backdoor",
        "frontdoor",
        "general_id",
        "iv_overidentified",
        "iv_wald",
        "outcome_error_precision_cost",
    ]


def test_the_assumption_free_route_outranks_the_one_that_needs_assumptions():
    """Finding C in table form: general-ID answers the query's own estimand
    with no assumption, the Wald reports a complier contrast under
    monotonicity. Declaring an assumption must never demote the answer."""
    order = {r.id: r.precedence for r in routing.EFFECT_ROUTES}
    assert order["general_id"] < order["iv_wald"]
    assert order["general_id"] < order["iv_overidentified"]


# --- a route the table promises is a route some layer runs ----------------


def test_a_route_whose_end_nobody_implemented_is_refused():
    """Finding D's shape, made impossible: the table promised conditional
    identification and the layer never ran it, because the branch sat inside
    the wrong copy of the ladder. A binding set that misses a route it
    declares cannot be loaded at all."""
    with pytest.raises(ValueError, match="no implementation for"):
        routing.bind(routing.End.IDENTIFICATION, {})


def test_an_implementation_for_a_route_the_table_does_not_send_here():
    """The other half: a handler nobody routes to is where a second
    dispatcher starts."""
    bindings = {r.id: object() for r in routing.EFFECT_ROUTES
                if routing.End.IDENTIFICATION in r.ends}
    bindings["doubly_robust"] = object()
    with pytest.raises(ValueError, match="second dispatcher"):
        routing.bind(routing.End.IDENTIFICATION, bindings)


def test_the_effect_dispatcher_reaches_its_strategies_only_through_the_table():
    """One dispatcher. ``_dispatch_effect`` used to name its strategies
    directly, twice over, and the two lists had diverged; a name in its body
    is a second routing decision no matter how it is spelled."""
    source = _SCHEDULER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    body = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_dispatch_effect"
    )
    named = {
        sub.id for sub in ast.walk(body)
        if isinstance(sub, ast.Name)
        and (sub.id.startswith("_identify_") or sub.id.startswith("_dispatch_"))
    }
    assert not named, named


# --- the guard cannot see this layer's own output -------------------------


def test_facts_do_not_expose_the_result():
    """Not a convention against reading it — the attribute is not there."""
    assert not hasattr(EffectFacts, "result")
    assert "result" not in EffectFacts.__init__.__code__.co_varnames


def test_every_guard_is_a_pure_function_of_the_facts():
    """A guard may read facts and call builtins, nothing else.

    The estimation layer's longitudinal guard used to test a method name
    an earlier pass had left behind, so renaming the method would have
    rerouted queries in silence. A guard that can only see its argument
    cannot develop that kind of dependency.
    """
    tree = ast.parse(_ROUTING.read_text(encoding="utf-8"))
    allowed = set(dir(builtins))
    checked, offenders = 0, []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Route"
        ):
            continue
        guard = next(
            (kw.value for kw in node.keywords if kw.arg == "applies_when"),
            None,
        )
        assert isinstance(guard, ast.Lambda), "guards must be inline lambdas"
        checked += 1
        param = guard.args.args[0].arg
        for sub in ast.walk(guard.body):
            if isinstance(sub, ast.Name) and sub.id not in allowed | {param}:
                offenders.append((node.lineno, sub.id))
    assert checked == len(routing.EFFECT_ROUTES)
    assert not offenders, offenders


# --- role and estimand are declared, and the driver holds them to it ------


def test_an_annotating_row_produces_no_estimand():
    with pytest.raises(ValueError, match="annotating strategy produces no"):
        _row("a", 10, role=Role.ANNOTATE, produces=Estimand.QUERY_EFFECT)


def test_a_claiming_row_must_name_the_estimand_it_produces():
    with pytest.raises(ValueError, match="must name the estimand"):
        _row("a", 10, role=Role.CLAIM, produces=Estimand.NONE)


def test_an_annotation_that_answers_the_query_is_rejected():
    """The finding-B shape: something that was supposed to comment beside
    the answer supplies one instead, for a different estimand."""
    table = check_table((
        _row("rogue", 10, role=Role.ANNOTATE, produces=Estimand.NONE,
             run=lambda f, r, k: answered()),
    ))
    with pytest.raises(AssertionError, match="declared as annotating"):
        run_cascade(table, None, {}, None, query_id="q1")


def test_every_claiming_row_in_the_real_table_names_a_real_estimand():
    for s in _EFFECT_STRATEGIES:
        assert isinstance(s.produces, Estimand)
        assert (s.produces is Estimand.NONE) == (s.role is Role.ANNOTATE), s.id


# --- one evaluation, four readings ---------------------------------------


def test_the_first_claim_wins_and_stops_the_offer():
    reached = []
    table = check_table((
        _row("first", 10, run=lambda f, r, k: (reached.append("first"), answered())[1]),
        _row("second", 20, run=lambda f, r, k: (reached.append("second"), answered())[1]),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert reached == ["first"]
    assert ev.fired == ("first", Estimand.QUERY_EFFECT)
    assert ev.answered


def test_a_block_stops_the_offer_without_an_answer():
    """The state the old bool could not express, now visible in the
    evaluation: nobody answered, and the record says who owned it."""
    reached = []
    table = check_table((
        _row("owner", 10, run=lambda f, r, k: blocked("not_identified")),
        _row("later", 20, run=lambda f, r, k: (reached.append("later"), answered())[1]),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert reached == []
    assert not ev.answered
    assert ev.declined == (("owner", "not_identified"),)


def test_a_pass_keeps_the_query_in_flight_and_is_remembered():
    table = check_table((
        _row("passer", 10,
             run=lambda f, r, k: passed("identification_chose_another_strategy")),
        _row("answerer", 20, run=lambda f, r, k: answered()),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert ev.fired == ("answerer", Estimand.QUERY_EFFECT)
    assert ev.passed_by == (
        ("passer", Estimand.QUERY_EFFECT,
         "identification_chose_another_strategy"),
    )


def test_a_guard_that_does_not_hold_explains_reachability():
    table = check_table((
        _row("skipped", 10, guard=lambda f: False),
        _row("ran", 20, run=lambda f, r, k: answered()),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert ev.considered == ("skipped",)


def test_an_annotation_is_recorded_and_the_query_continues():
    table = check_table((
        _row("note", 10, role=Role.ANNOTATE, produces=Estimand.NONE,
             run=lambda f, r, k: annotated()),
        _row("answerer", 20, run=lambda f, r, k: answered()),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert ev.annotated == ("note",)
    assert ev.passed_by == ()
    assert ev.answered


# --- the invariant slice 1 could state but not check ----------------------


def test_an_undeclared_substitution_is_rejected():
    """The invariant slice 1 could state but not enforce: passing a query
    on is only legitimate when whoever answers next answers the same
    question. This is the shape of both measured defects — a query comes
    back with a number for something it did not ask."""
    table = check_table((
        _row("assumption_free", 10, produces=Estimand.QUERY_EFFECT,
             run=lambda f, r, k: passed("not_identified")),
        _row("under_assumption", 20, produces=Estimand.COMPLIER_EFFECT,
             run=lambda f, r, k: answered()),
    ))
    with pytest.raises(AssertionError, match="different estimand"):
        run_cascade(table, None, {}, None, query_id="q1")


def test_a_declared_substitution_is_allowed_and_surfaced():
    """A ladder may substitute — the IV fall-back does, 80 times across
    this suite — but only where the table says so, and the pair stays
    visible in the evaluation afterwards."""
    table = check_table((
        _row("assumption_free", 10, produces=Estimand.QUERY_EFFECT,
             defers={"under_assumption"},
             run=lambda f, r, k: passed("not_identified")),
        _row("under_assumption", 20, produces=Estimand.COMPLIER_EFFECT,
             run=lambda f, r, k: answered()),
    ))
    ev = run_cascade(table, None, {}, None, query_id="q1")
    assert ev.substitutions == (
        ("assumption_free", "under_assumption",
         Estimand.QUERY_EFFECT, Estimand.COMPLIER_EFFECT),
    )


def test_a_row_may_only_defer_to_one_that_has_not_had_its_turn():
    with pytest.raises(ValueError, match="outranks it"):
        check_table((
            _row("early", 10, defers={"never"}),
            _row("never", 5),
        ))


def test_a_row_may_not_defer_to_a_strategy_that_does_not_exist():
    with pytest.raises(ValueError, match="unknown strategy"):
        check_table((_row("a", 10, defers={"ghost"}),))


def test_the_real_table_declares_exactly_the_substitutions_it_takes():
    """One remains: the IV escalation, measured 80 times across this suite.

    There were two. The other — mediation standing down so transport could
    answer — was an artefact of the two layers ordering those rows
    differently, and one shared order retired it. A substitution that only
    exists because two copies disagreed is not a ladder.
    """
    declared = {
        s.id: set(s.defers_to) for s in _EFFECT_STRATEGIES if s.defers_to
    }
    assert declared == {"general_id": {"iv_overidentified", "iv_wald"}}


def test_a_pass_answered_by_the_same_estimand_is_not_a_substitution():
    table = check_table((
        _row("a", 10, run=lambda f, r, k: passed("design_unavailable")),
        _row("b", 20, run=lambda f, r, k: answered()),
    ))
    assert run_cascade(table, None, {}, None, query_id="q1").substitutions == ()


def test_an_unanswered_query_has_no_substitutions():
    table = check_table((
        _row("a", 10, run=lambda f, r, k: passed("design_unavailable")),
    ))
    assert run_cascade(table, None, {}, None, query_id="q1").substitutions == ()


# --- the recorder --------------------------------------------------------


def test_recording_collects_every_evaluation_in_the_block():
    table = check_table((_row("a", 10, run=lambda f, r, k: answered()),))
    with recording() as seen:
        run_cascade(table, None, {}, None, query_id="q1")
        run_cascade(table, None, {}, None, query_id="q2")
    assert [e.query_id for e in seen] == ["q1", "q2"]


def test_recording_stops_at_the_end_of_the_block():
    table = check_table((_row("a", 10, run=lambda f, r, k: answered()),))
    with recording() as seen:
        pass
    run_cascade(table, None, {}, None, query_id="q1")
    assert seen == []


def test_evaluations_are_immutable():
    with pytest.raises(Exception):
        Evaluation(query_id="q1").query_id = "q2"  # type: ignore[misc]
