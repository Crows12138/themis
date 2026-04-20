"""End-to-end tests for slice 9: Theta-fed back-door effect queries
propagate probability-statement confidences into QueryResult.confidence
per the RFC §3 collection rules and the min composite rule.

The fixtures are constructed programmatically rather than on disk —
confidence annotations are orthogonal to the causal structure and
sprawling fixture files would duplicate numeric_backdoor.json minus
or plus a single field. Three scenarios:

1. Every probability statement annotated with 0.9 → confidence = 0.9.
2. Mixed 0.9 and 0.3 → confidence = 0.3 (RFC §7 weakest link).
3. No annotations → confidence = None (preserves v0.1.0 behaviour).
"""
from __future__ import annotations

import pytest

from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    Annotation,
    Atom,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    Intervention,
    ProbabilityStatement,
    Program,
    QueryStatement,
    ResultStatus,
    ValuedAtom,
    VarTerm,
)


def _atom(pred: str, obj: str = "alice") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _var_atom(pred: str) -> Atom:
    """Pattern atom of the form pred(X) used in forall-quantified cause
    and probability statements."""
    return Atom(predicate=pred, args=(VarTerm(name="X"),))


def _build_program(confidences: dict[str, float | None]) -> Program:
    """Build the same confounded scenario as numeric_backdoor.json:

        stress -> smokes, stress -> cancer, smokes -> cancer

    with four CPT entries + one effect query. ``confidences`` maps
    statement short-name ('cancer_given_stress_true',
    'cancer_given_stress_false', 'stress_true', 'stress_false') to
    annotation.confidence (or None to omit the annotation)."""

    def annot(key: str):
        c = confidences.get(key)
        return Annotation(confidence=c) if c is not None else None

    return Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(
                from_atom=_var_atom("stress"),
                to_atom=_var_atom("smokes"),
                forall=("X",),
            ),
            CauseStatement(
                from_atom=_var_atom("stress"),
                to_atom=_var_atom("cancer"),
                forall=("X",),
            ),
            CauseStatement(
                from_atom=_var_atom("smokes"),
                to_atom=_var_atom("cancer"),
                forall=("X",),
            ),
            ProbabilityStatement(
                target=ValuedAtom(atom=_var_atom("cancer"), value=True),
                given=(
                    ValuedAtom(atom=_var_atom("smokes"), value=False),
                    ValuedAtom(atom=_var_atom("stress"), value=True),
                ),
                value=0.3,
                forall=("X",),
                annotations=annot("cancer_given_stress_true"),
            ),
            ProbabilityStatement(
                target=ValuedAtom(atom=_var_atom("cancer"), value=True),
                given=(
                    ValuedAtom(atom=_var_atom("smokes"), value=False),
                    ValuedAtom(atom=_var_atom("stress"), value=False),
                ),
                value=0.1,
                forall=("X",),
                annotations=annot("cancer_given_stress_false"),
            ),
            ProbabilityStatement(
                target=ValuedAtom(atom=_var_atom("stress"), value=True),
                given=(),
                value=0.4,
                forall=("X",),
                annotations=annot("stress_true"),
            ),
            ProbabilityStatement(
                target=ValuedAtom(atom=_var_atom("stress"), value=False),
                given=(),
                value=0.6,
                forall=("X",),
                annotations=annot("stress_false"),
            ),
            QueryStatement(
                id="q",
                query=EffectQuery(
                    target=ValuedAtom(atom=_atom("cancer"), value=True),
                    intervention=Intervention(
                        atom=_atom("smokes"), value=False
                    ),
                    given=(),
                ),
            ),
        ),
    )


def _run(confidences):
    program = _build_program(confidences)
    graph = project(instantiate(program))
    return dispatch_all(program, graph)[0]


# ----------------------------------------------------- uniform annotation

def test_uniform_confidence_propagates_to_result():
    r = _run({
        "cancer_given_stress_true":  0.9,
        "cancer_given_stress_false": 0.9,
        "stress_true":               0.9,
        "stress_false":              0.9,
    })
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.numeric_result.value == pytest.approx(0.18)
    assert r.confidence == pytest.approx(0.9)


# ---------------------------------------------------- mixed: min wins

def test_mixed_confidence_takes_minimum():
    """Four slots with confidences 0.9, 0.3, 0.9, 0.9 → 0.3 (RFC §7)."""
    r = _run({
        "cancer_given_stress_true":  0.9,
        "cancer_given_stress_false": 0.3,
        "stress_true":               0.9,
        "stress_false":              0.9,
    })
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.confidence == pytest.approx(0.3)


# ------------------------------------------ no annotation → None preserved

def test_no_annotation_preserves_none_confidence():
    """Omitting annotations on every statement must leave
    QueryResult.confidence as None — this is the v0.1.0 tagged
    behaviour and must not shift under slice 9."""
    r = _run({
        "cancer_given_stress_true":  None,
        "cancer_given_stress_false": None,
        "stress_true":               None,
        "stress_false":              None,
    })
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.numeric_result.value == pytest.approx(0.18)
    assert r.confidence is None


# --------------------- partial: one annotated slot, rest unannotated

def test_partial_annotation_only_contributes_annotated_slots():
    """Only one slot annotated at 0.7; the other slots don't have
    annotations, so they're excluded per RFC §3.1. The composite
    equals the single annotated slot's confidence."""
    r = _run({
        "cancer_given_stress_true":  0.7,
        "cancer_given_stress_false": None,
        "stress_true":               None,
        "stress_false":              None,
    })
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.confidence == pytest.approx(0.7)
