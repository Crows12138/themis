# -*- coding: utf-8 -*-
"""A rendering may reach the reader, and nothing else may read it.

``item.target`` is a probability rendered for a person: ``P(y=True|x=True)``.
Three passes used to take it back apart — two sniffing it for a value token
to pick a sample-size formula, one testing a mediator name against it as a
substring — so which formula ran was decided by how a sentence was spelled.
The statement the producer files with the ask says the same things exactly,
and says them in a shape no wording can move.

The gate here is the general form: inside the two species that hold both, the
reader's copy may only be handed to something that writes for the reader, and
the branches may only be taken on what the ask states.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from themis import gaps
from themis.output import data_gap_report as dgr
from themis.output import sample_size
from themis.runtime import investigation_pusher
from themis.types import (
    GapKind,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    MissingItem,
    MissingKind,
    Priority,
    QueryKind,
    ResultStatus,
)

_SOURCE = pathlib.Path(dgr.__file__).read_text(encoding="utf-8")
_TREE = ast.parse(_SOURCE)

#: Calls whose arguments are written for a person: the sentence they read,
#: the route they are offered, and the id that points back at the ask.
_FOR_THE_READER = frozenset({"_sentence", "_route", "GapProvenanceRef"})


def _function(name: str) -> ast.FunctionDef:
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from {dgr.__name__}")


def _sheltered(fn: ast.FunctionDef) -> set[int]:
    """Every node id under a call that writes for the reader."""
    out: set[int] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = (func.id if isinstance(func, ast.Name)
                  else func.attr if isinstance(func, ast.Attribute) else "")
        if called in _FOR_THE_READER:
            out.update(id(n) for n in ast.walk(node))
    return out


def _escapes(fn: ast.FunctionDef, reads) -> list[str]:
    """Uses of the rendering that go somewhere other than the reader."""
    sheltered = _sheltered(fn)
    return [
        f"{fn.name}:{node.lineno}"
        for node in ast.walk(fn)
        if reads(node)
        and isinstance(getattr(node, "ctx", None), ast.Load)
        and id(node) not in sheltered
    ]


def test_the_rendered_ask_reaches_the_reader_and_nothing_else():
    """``display`` is ``item.target`` stripped of its channel prefix, and
    it is the copy a person is shown. A branch that reads it is a kernel
    decision taken on a wording."""
    escaped = _escapes(
        _function("_species_missing_distribution"),
        lambda n: isinstance(n, ast.Name) and n.id == "display",
    )
    assert not escaped, (
        f"the reader's copy of the ask is read at {escaped}; the facts a "
        f"branch needs are stated by the ask itself — see "
        f"{dgr.__name__}.asked"
    )


def test_which_mediators_an_ask_touches_is_not_read_off_its_name():
    """The same rule where the substring test lived: a mediator is one of
    the variables the ask names, which its statement lists."""
    escaped = _escapes(
        _function("_classify_missing_mediator"),
        lambda n: (isinstance(n, ast.Attribute) and n.attr == "target"
                   and isinstance(n.value, ast.Name) and n.value.id == "item"),
    )
    assert not escaped, (
        f"the ask's rendered name is read at {escaped}; which variables it "
        f"is about is `asked(item.skeleton).variables`"
    )


@pytest.mark.parametrize("name", [
    "_distribution_signature",
    "_estimate_sample_size_for_distribution",
    "_estimate_sample_size_for_mediator",
])
def test_no_branch_here_is_offered_a_rendering_to_read(name):
    """Stated in the signature, so a future caller cannot hand one over.

    Each of these three took a rendered ``P(...)`` — one of them took both
    it and a value derived from it, which is how the same string came to
    be parsed twice per gap by two different rules."""
    sig = inspect.signature(getattr(dgr, name))
    assert [str(p.annotation) for p in sig.parameters.values()] == [
        "'Ask | None'"], f"{name}{sig}"


# ------------------------------- what the two readings disagree about

def _statement(predicate, value, given=()):
    return {
        "kind": "probability",
        "target": {"atom": {"predicate": predicate, "args": []},
                   "value": value},
        "given": [{"atom": {"predicate": p, "args": []}, "value": v}
                  for p, v in given],
        "value": None,
        "annotations": {"source": "TODO"},
    }


def _report(target, skeleton, extensions=None):
    request = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
            skeleton=skeleton,
        ),),
    )
    return dgr.compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(request,),
        framing_notes=(),
        extensions=extensions,
    )


def _the_distribution_gap(report):
    return next(
        g for g in report.gaps if g.kind is GapKind.MISSING_DISTRIBUTION)


def test_a_name_that_reads_binary_over_an_ask_that_is_not():
    """The name says ``=True`` and the ask says a blood pressure.

    Nothing renders this today; that is the point. The rendering is a
    reader-facing product and the spelling of a value in it is a question
    about language — a report that reached a formula through it would
    answer differently in another one."""
    gap = _the_distribution_gap(_report(
        "parameter:P(systolic_bp=True|salt=True)",
        _statement("systolic_bp", 140.0, [("salt", True)]),
    ))
    assert gap.required_data.min_sample_size == 150   # a mean, two arms
    assert gap.required_data.precision_target["said"]["d"] == "0.5"


def test_a_name_with_no_bar_over_an_ask_that_conditions():
    gap = _the_distribution_gap(_report(
        "parameter:P(y=True)",
        _statement("y", True, [("x", True)]),
    ))
    assert gap.signature == "conditional"
    assert gap.required_data.min_sample_size == 400   # two arms, not one


def test_a_mediator_is_matched_as_a_variable_and_not_as_a_substring():
    """``bmi`` is not the variable ``low_bmi``, and a substring test on the
    rendered name cannot tell them apart."""
    report = _report(
        "parameter:P(low_bmi=true|exercise=true)",
        _statement("low_bmi", True, [("exercise", True)]),
        extensions={"mediation_decomposition": {
            "mediator": "bmi", "mediator_valid": True}},
    )
    assert not [
        g for g in report.gaps if g.kind is GapKind.MISSING_MEDIATOR_DATA]


def test_a_mediator_that_is_the_variable_still_matches():
    """The other direction, so the test above cannot pass by matching
    nothing."""
    report = _report(
        "parameter:P(low_bmi=true|exercise=true)",
        _statement("low_bmi", True, [("exercise", True)]),
        extensions={"mediation_decomposition": {
            "mediator": "low_bmi", "mediator_valid": True}},
    )
    touched = [
        g for g in report.gaps if g.kind is GapKind.MISSING_MEDIATOR_DATA]
    assert len(touched) == 1
    assert touched[0].required_data.variables == ("low_bmi",)


# ------------------------- the ask and its statement are one object

def test_a_parameter_ask_is_built_holding_the_statement_that_settles_it():
    """One producer, one constructor, so coverage is not a property of
    every call site downstream remembering to carry a map."""
    from themis.runtime.numeric_estimator import ProbabilityKey
    from themis.types import Atom

    key = ProbabilityKey(
        target_atom=Atom(predicate="y", args=()),
        target_value=True,
        given=frozenset({(Atom(predicate="x", args=()), True)}),
    )
    item = dgr_scheduler()._missing_parameter_from_key(
        key, need=gaps.Need.THETA_ENTRY_MISSING, key="P(y=True|x=True)")
    assert item.skeleton is not None
    assert item.skeleton["target"]["value"] is True
    assert [g["value"] for g in item.skeleton["given"]] == [True]
    # And the pusher projects it the way it projects the species: no
    # second argument, so no call site that can omit one.
    pushed = investigation_pusher.push((item,))[0].items[0]
    assert pushed.skeleton == item.skeleton


def test_the_pusher_takes_nothing_but_the_items():
    """The map used to be rejoined here by each item's rendered name."""
    sig = inspect.signature(investigation_pusher.push)
    assert list(sig.parameters) == ["missing"]


def test_the_statement_has_one_author():
    """Two would be two answers to what an ask is, joined by a name."""
    scheduler_source = pathlib.Path(
        dgr_scheduler().__file__).read_text(encoding="utf-8")
    tree = ast.parse(scheduler_source)
    callers = {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_skeleton_for_parameter"
    }
    assert len(callers) == 1, f"called from lines {sorted(callers)}"


def dgr_scheduler():
    from themis.runtime import scheduler

    return scheduler


def test_an_ask_with_no_key_behind_it_carries_no_statement():
    """The one case that legitimately has none — a query-bound atom with
    no value resolved, which no probability statement would settle."""
    item = dgr_scheduler()._missing_parameter_from_key(
        None, need=gaps.Need.QUERY_BOUND_ATOM_UNRESOLVED)
    assert item.kind is MissingKind.PARAMETER
    assert item.skeleton is None
    assert isinstance(item, MissingItem)


def test_the_family_a_formula_belongs_to_is_a_word_and_not_two_flags():
    """A value that is neither a truth value nor a number is the absence
    of a family, not a third one, and two booleans could say it is both."""
    assert set(sample_size.Measured) == {
        sample_size.Measured.PROPORTION, sample_size.Measured.MEAN}
    assert dgr.asked(_statement("dose", "high")).measured is None
