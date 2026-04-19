"""Unit tests for MissingItem -> InvestigationRequest mapping."""
from __future__ import annotations

from themis.runtime.investigation_pusher import push
from themis.types import (
    InvestigationAction,
    MissingItem,
    MissingKind,
    Priority,
)


def _mk(kind: MissingKind, name: str = "x", reason: str | None = None) -> MissingItem:
    return MissingItem(kind=kind, name=name, priority=Priority.MEDIUM, reason=reason)


def test_parameter_becomes_validate_parameter():
    reqs = push((_mk(MissingKind.PARAMETER, "P(y|x)"),))
    assert reqs[0].action is InvestigationAction.VALIDATE_PARAMETER
    assert reqs[0].target == "P(y|x)"


def test_observation_becomes_collect_observation():
    reqs = push((_mk(MissingKind.OBSERVATION, "y(alice)"),))
    assert reqs[0].action is InvestigationAction.COLLECT_OBSERVATION


def test_sample_becomes_increase_sample():
    reqs = push((_mk(MissingKind.SAMPLE, "cohort_a"),))
    assert reqs[0].action is InvestigationAction.INCREASE_SAMPLE


def test_structure_becomes_run_experiment():
    reqs = push((_mk(MissingKind.STRUCTURE, "edge:x->y"),))
    assert reqs[0].action is InvestigationAction.RUN_EXPERIMENT


def test_reason_is_carried_into_note():
    reqs = push((_mk(MissingKind.PARAMETER, "p1", reason="need CPT"),))
    assert reqs[0].note == "need CPT"


def test_priority_passes_through():
    item = MissingItem(
        kind=MissingKind.PARAMETER, name="p", priority=Priority.HIGH
    )
    reqs = push((item,))
    assert reqs[0].priority is Priority.HIGH


def test_empty_input_empty_output():
    assert push(()) == ()


def test_multiple_items_preserve_order():
    items = (
        _mk(MissingKind.PARAMETER, "a"),
        _mk(MissingKind.OBSERVATION, "b"),
        _mk(MissingKind.SAMPLE, "c"),
    )
    reqs = push(items)
    assert [r.target for r in reqs] == ["a", "b", "c"]
