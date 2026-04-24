"""Phase 5 §T / S.T.4: existing dispatchers reuse the time-expanded graph.

This slice is intentionally narrow: the goal is to prove that once
``Atom.time_index`` is part of node identity, the existing
``cause / assoc / identify / effect / probability`` pipeline can run on
the projected graph without any temporal-specialized scheduler branch.
"""
from __future__ import annotations

import pytest

from themis.input.syntactic_validator import validate_result
from themis.output.explainer import explain
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    AssocQuery,
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ProbabilityQuery,
    ProbabilityRefExpr,
    ProbabilityStatement,
    Program,
    QueryKind,
    QueryStatement,
    RelativeTimeIndex,
    ResultStatus,
    ValuedAtom,
)


def _const(name: str) -> ConstTerm:
    return ConstTerm(name=name)


def _atom(predicate: str, t: int | None = None) -> Atom:
    return Atom(
        predicate=predicate,
        args=(_const("me"),),
        time_index=None if t is None else RelativeTimeIndex(value=t),
    )


def _valued(predicate: str, value: bool, t: int | None = None) -> ValuedAtom:
    return ValuedAtom(atom=_atom(predicate, t), value=value)


@pytest.fixture(scope="module")
def temporal_results():
    """One tiny temporal program covering all existing query families."""
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            # exercise@t-1 affects energy@t and mood@t
            CauseStatement(from_atom=_atom("exercise", -1), to_atom=_atom("energy", 0)),
            CauseStatement(from_atom=_atom("exercise", -1), to_atom=_atom("mood", 0)),
            # energy@t then affects mood@t+1
            CauseStatement(from_atom=_atom("energy", 0), to_atom=_atom("mood", 1)),
            ProbabilityStatement(
                target=_valued("exercise", True, -1),
                given=(),
                value=0.6,
            ),
            ProbabilityStatement(
                target=_valued("exercise", False, -1),
                given=(),
                value=0.4,
            ),
            ProbabilityStatement(
                target=_valued("energy", True, 0),
                given=(_valued("exercise", True, -1),),
                value=0.8,
            ),
            ProbabilityStatement(
                target=_valued("energy", False, 0),
                given=(_valued("exercise", True, -1),),
                value=0.2,
            ),
            ProbabilityStatement(
                target=_valued("energy", True, 0),
                given=(_valued("exercise", False, -1),),
                value=0.3,
            ),
            ProbabilityStatement(
                target=_valued("energy", False, 0),
                given=(_valued("exercise", False, -1),),
                value=0.7,
            ),
            QueryStatement(
                id="q_cause_temporal",
                query=CauseQuery(
                    from_atom=_atom("exercise", -1),
                    to_atom=_atom("energy", 0),
                ),
            ),
            QueryStatement(
                id="q_assoc_temporal",
                query=AssocQuery(
                    left=_atom("exercise", -1),
                    right=_atom("mood", 1),
                    given=(),
                ),
            ),
            QueryStatement(
                id="q_identify_temporal",
                query=IdentifyQuery(
                    target=_atom("energy", 0),
                    intervention=Intervention(atom=_atom("exercise", -1), value=True),
                    given=(),
                ),
            ),
            QueryStatement(
                id="q_effect_temporal",
                query=EffectQuery(
                    target=_valued("energy", True, 0),
                    intervention=Intervention(atom=_atom("exercise", -1), value=True),
                    given=(),
                ),
            ),
            QueryStatement(
                id="q_probability_temporal",
                query=ProbabilityQuery(
                    target=_valued("exercise", True, -1),
                    given=(),
                ),
            ),
        ),
    )
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    return program, graph, results


def _find_stmt(program: Program, query_id: str) -> QueryStatement:
    for stmt in program.statements:
        if isinstance(stmt, QueryStatement) and stmt.id == query_id:
            return stmt
    raise AssertionError(f"query {query_id!r} not found")


def test_temporal_cause_dispatch_reuses_existing_solver(temporal_results):
    _, _, results = temporal_results
    r = results["q_cause_temporal"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.CAUSE
    assert r.structural_result is not None
    assert r.structural_result.value is True
    assert r.structural_result.supporting_paths == (
        ("exercise(me)@t-1", "energy(me)@t"),
    )


def test_temporal_assoc_dispatch_reuses_existing_solver(temporal_results):
    _, _, results = temporal_results
    r = results["q_assoc_temporal"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.ASSOC
    assert r.structural_result is not None
    assert r.structural_result.value is True
    assert r.structural_result.supporting_paths == (
        ("exercise(me)@t-1", "energy(me)@t", "mood(me)@t+1"),
    )


def test_temporal_identify_reuses_empty_adjustment_path(temporal_results):
    _, _, results = temporal_results
    r = results["q_identify_temporal"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.IDENTIFY
    assert r.structural_result is not None
    assert r.structural_result.value is True
    assert isinstance(r.formula, ProbabilityRefExpr)
    assert r.formula.target.atom == _atom("energy", 0)
    assert r.formula.given == (_valued("exercise", True, -1),)


def test_temporal_effect_reuses_numeric_dispatch(temporal_results):
    _, _, results = temporal_results
    r = results["q_effect_temporal"]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.query_kind is QueryKind.EFFECT
    assert r.numeric_result is not None
    assert r.numeric_result.value == pytest.approx(0.8)
    assert isinstance(r.formula, ProbabilityRefExpr)
    assert r.formula.target == _valued("energy", True, 0)


def test_temporal_probability_reuses_numeric_dispatch(temporal_results):
    _, _, results = temporal_results
    r = results["q_probability_temporal"]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.query_kind is QueryKind.PROBABILITY
    assert r.numeric_result is not None
    assert r.numeric_result.value == pytest.approx(0.6)
    assert isinstance(r.formula, ProbabilityRefExpr)
    assert r.formula.target == _valued("exercise", True, -1)


def test_temporal_results_validate_and_explanations_render_time_suffixes(
    temporal_results,
):
    program, _, results = temporal_results

    for qid, r in results.items():
        payload = to_dict(r)
        validate_result(payload)
        assert payload["query_id"] == qid

    cause_text = explain(results["q_cause_temporal"])
    assert "exercise(me)@t-1 -> energy(me)@t" in cause_text

    effect_stmt = _find_stmt(program, "q_effect_temporal")
    effect_text = explain(results["q_effect_temporal"], stmt=effect_stmt)
    assert "energy(me)@t" in effect_text
    assert "exercise(me)@t-1" in effect_text
    assert "0.8" in effect_text
