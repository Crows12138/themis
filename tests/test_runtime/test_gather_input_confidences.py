"""Slice 9: confidence collection per RFC §3.

Unit-level tests for ``scheduler._gather_input_confidences``. Exercise
the RFC's corner rules without relying on specific fixture strings.

Covered:
- Structural queries (cause / assoc / identify) always return ().
- Effect / probability dedupe probability slots by ProbabilityKey.
- RFC §3.1 slot min across multiple source statements.
- Missing annotations skip the slot (not None / 0 / 1 placeholder).
- RFC §3.2 observation participation: atom + value must both match
  an entry in q.given.
- RFC §3.2 intervention atoms never participate even when an
  ObservationStatement matches.
"""
from __future__ import annotations

from themis.runtime.scheduler import _gather_input_confidences
from themis.runtime.theta_builder import (
    build_observation_source_index,
    build_probability_source_index,
)
from themis.runtime.numeric_estimator import Theta, ProbabilityKey
from themis.types import (
    Annotation,
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityRefExpr,
    ProbabilityStatement,
    Program,
    QueryKind,
    QueryResult,
    QueryStatement,
    ResultStatus,
    ValuedAtom,
)


def atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _mk_prob_stmt(
    target: ValuedAtom,
    given: tuple[ValuedAtom, ...],
    value: float,
    confidence: float | None,
) -> ProbabilityStatement:
    annotation = (
        Annotation(confidence=confidence) if confidence is not None else None
    )
    return ProbabilityStatement(
        target=target, given=given, value=value, annotations=annotation
    )


def _mk_program(*statements) -> Program:
    return Program(version="0.1", objects=("a",), statements=tuple(statements))


def _mk_result(kind: QueryKind, formula=None) -> QueryResult:
    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=kind,
        query_id="q",
        formula=formula,
    )


# ------------------------------------------------------- structural queries

def test_cause_query_returns_empty():
    prog = _mk_program()
    stmt = QueryStatement(
        id="q", query=CauseQuery(from_atom=atom("x"), to_atom=atom("y"))
    )
    r = _mk_result(QueryKind.CAUSE)
    assert _gather_input_confidences(
        prog, stmt, r, theta=Theta(), prob_index={}, obs_index={}
    ) == ()


def test_assoc_query_returns_empty():
    prog = _mk_program()
    stmt = QueryStatement(
        id="q",
        query=CauseQuery(from_atom=atom("x"), to_atom=atom("y")),  # kind flag only
    )
    r = _mk_result(QueryKind.ASSOC)
    assert _gather_input_confidences(
        prog, stmt, r, theta=Theta(), prob_index={}, obs_index={}
    ) == ()


def test_identify_query_returns_empty():
    prog = _mk_program()
    stmt = QueryStatement(
        id="q",
        query=IdentifyQuery(
            target=atom("y"),
            intervention=Intervention(atom=atom("x"), value=True),
            given=(),
        ),
    )
    r = _mk_result(QueryKind.IDENTIFY)
    assert _gather_input_confidences(
        prog, stmt, r, theta=Theta(), prob_index={}, obs_index={}
    ) == ()


# ------------------------------------------------------- §3.1 slot min rule

def test_duplicate_sources_take_slot_min():
    """Two equivalent ProbabilityStatements (same key, same value) with
    different confidences → slot_conf = min(them)."""
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(),
    )
    s1 = _mk_prob_stmt(
        target=ValuedAtom(atom=y, value=True),
        given=(),
        value=0.5,
        confidence=0.9,
    )
    s2 = _mk_prob_stmt(
        target=ValuedAtom(atom=y, value=True),
        given=(),
        value=0.5,
        confidence=0.3,
    )
    prog = _mk_program(s1, s2)
    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True), given=()
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)
    prob_idx = build_probability_source_index((s1, s2))

    inputs = _gather_input_confidences(
        prog, stmt, r,
        theta=Theta(), prob_index=prob_idx, obs_index={},
    )
    assert inputs == (0.3,)


def test_missing_annotation_skips_slot():
    """A slot whose sources all lack annotation.confidence contributes
    nothing — not None, not 0, not 1."""
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(),
    )
    s = _mk_prob_stmt(
        target=ValuedAtom(atom=y, value=True),
        given=(),
        value=0.5,
        confidence=None,
    )
    prog = _mk_program(s)
    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True), given=()
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)
    prob_idx = build_probability_source_index((s,))

    inputs = _gather_input_confidences(
        prog, stmt, r,
        theta=Theta(), prob_index=prob_idx, obs_index={},
    )
    assert inputs == ()


def test_mixed_annotated_and_unannotated_sources():
    """If any source has a confidence annotation, slot_conf is min
    over the annotated ones; unannotated sources are ignored."""
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True), given=()
    )
    s_conf = _mk_prob_stmt(
        target=ValuedAtom(atom=y, value=True),
        given=(), value=0.5, confidence=0.7,
    )
    s_no_conf = _mk_prob_stmt(
        target=ValuedAtom(atom=y, value=True),
        given=(), value=0.5, confidence=None,
    )
    prob_idx = build_probability_source_index((s_conf, s_no_conf))

    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True), given=()
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)

    inputs = _gather_input_confidences(
        _mk_program(s_conf, s_no_conf), stmt, r,
        theta=Theta(), prob_index=prob_idx, obs_index={},
    )
    assert inputs == (0.7,)


# ------------------------------------------------ §3.2 observation matching

def test_observation_matching_both_atom_and_value_participates():
    z = atom("z")
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=z, value=True),),
    )
    # No probability sources — only observation.
    obs = ObservationStatement(
        atom=z, value=True, annotations=Annotation(confidence=0.8),
    )
    obs_idx = build_observation_source_index((obs,))

    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=z, value=True),),
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)

    inputs = _gather_input_confidences(
        _mk_program(obs), stmt, r,
        theta=Theta(), prob_index={}, obs_index=obs_idx,
    )
    assert inputs == (0.8,)


def test_observation_value_mismatch_is_ignored():
    """Observation z=False does not participate in a query whose
    given entry is z=True."""
    z = atom("z")
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=z, value=True),),
    )
    obs_false = ObservationStatement(
        atom=z, value=False, annotations=Annotation(confidence=0.9),
    )
    obs_idx = build_observation_source_index((obs_false,))

    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=z, value=True),),
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)

    inputs = _gather_input_confidences(
        _mk_program(obs_false), stmt, r,
        theta=Theta(), prob_index={}, obs_index=obs_idx,
    )
    assert inputs == ()


def test_observation_atom_not_in_given_is_ignored():
    """Observation on an atom the query never conditioned on contributes
    nothing, even if present in the program."""
    z = atom("z")
    w = atom("w")
    y = atom("y")
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=z, value=True),),
    )
    obs_w = ObservationStatement(
        atom=w, value=True, annotations=Annotation(confidence=0.95),
    )
    obs_idx = build_observation_source_index((obs_w,))

    stmt = QueryStatement(
        id="q",
        query=ProbabilityQuery(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=z, value=True),),
        ),
    )
    r = _mk_result(QueryKind.PROBABILITY, formula=formula)

    inputs = _gather_input_confidences(
        _mk_program(obs_w), stmt, r,
        theta=Theta(), prob_index={}, obs_index=obs_idx,
    )
    assert inputs == ()


def test_intervention_atom_never_participates():
    """RFC §3.2 exclusion: do(X=x) + ObservationStatement(X, x, ...) →
    the observation still does not participate. The intervention atom
    is not inspected for observation slots."""
    x = atom("x")
    y = atom("y")
    # Formula shape for a direct effect (empty adjustment set).
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=False),),
    )
    obs_on_x = ObservationStatement(
        atom=x, value=False, annotations=Annotation(confidence=0.99),
    )
    obs_idx = build_observation_source_index((obs_on_x,))

    # Effect query: given=[] so intervention is the only x reference.
    stmt = QueryStatement(
        id="q",
        query=EffectQuery(
            target=ValuedAtom(atom=y, value=True),
            intervention=Intervention(atom=x, value=False),
            given=(),
        ),
    )
    r = _mk_result(QueryKind.EFFECT, formula=formula)

    inputs = _gather_input_confidences(
        _mk_program(obs_on_x), stmt, r,
        theta=Theta(), prob_index={}, obs_index=obs_idx,
    )
    # Intervention x=False is NOT in q.given, so the observation is
    # ignored even though it matches (x, False) exactly.
    assert inputs == ()
