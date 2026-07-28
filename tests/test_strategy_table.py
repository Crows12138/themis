"""The estimation cascade's strategy table (Phase 17 slice 2).

The chain this table replaced encoded three things in its own shape:
priority (source line order), what each guard tested (anything in scope,
including output the pass had already written), and what each number was
an estimate of (nothing — it was prose in a docstring). Each of those had
drifted from the identification layer's separately written copy, and the
slice 0 audit found real defects in two of the three. These tests pin the
properties that make the drift detectable instead of invisible.
"""
from __future__ import annotations

import ast
import builtins
import pathlib

import pytest

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

_DISPATCH = pathlib.Path(
    __import__("themis").__file__
).parent / "estimation" / "dispatch.py"


def _noop(f, r, k):
    return passed("not_identified")


def _row(id_, precedence, *, guard=lambda f: True, role=Role.CLAIM,
         produces=Estimand.QUERY_EFFECT, run=_noop, defers=()) -> Strategy:
    return Strategy(
        id=id_, precedence=precedence, applies_when=guard,
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


def test_precedence_reproduces_the_order_the_hand_written_chain_had():
    """The behaviour-equivalence anchor for the migration: the table is a
    restatement of the chain, so any reordering has to be a deliberate edit
    to this list rather than a side effect of moving code."""
    assert [s.id for s in _EFFECT_STRATEGIES] == [
        "joint_intervention",
        "mediation_joint",
        "mediation_single",
        "transport",
        "selection_recovery",
        "measurement_correction_both_channels",
        "measurement_correction_outcome",
        "measurement_correction_exposure",
        "outcome_error_precision_cost",
        "regression_calibration",
        "dose_response_binary_fallback",
        "dose_response_curve",
        "doubly_robust",
        "backdoor",
        "frontdoor",
        "general_id",
        "iv_overidentified",
        "iv_wald",
    ]


def test_the_assumption_free_route_outranks_the_one_that_needs_assumptions():
    """Finding C in table form: general-ID answers the query's own estimand
    with no assumption, the Wald reports a complier contrast under
    monotonicity. Declaring an assumption must never demote the answer."""
    order = {s.id: s.precedence for s in _EFFECT_STRATEGIES}
    assert order["general_id"] < order["iv_wald"]
    assert order["general_id"] < order["iv_overidentified"]


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
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    allowed = set(dir(builtins))
    checked, offenders = 0, []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Strategy"
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
    assert checked == len(_EFFECT_STRATEGIES)
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
    """Measured across the full suite: 80 IV escalations and one transport
    over a named mediator. Nothing else hands a query to a row that answers
    a different question."""
    declared = {
        s.id: set(s.defers_to) for s in _EFFECT_STRATEGIES if s.defers_to
    }
    assert declared == {
        "mediation_single": {"transport"},
        "general_id": {"iv_overidentified", "iv_wald"},
    }


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
