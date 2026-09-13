"""Which layer an assumption holds up, and whether anyone can check it.

A ledger line tells a reader two things about the assumption itself:
``layer`` — which part of the answer stops being true without it — and
``testable`` — whether there is anything they could go and do about it.
Neither is a fact about the run. The same id means the same two things in
every answer, and one table declares them for all of them.

Nothing had ever asked. Every ledger line's ``testable`` could be rewritten
and every door said yes, on 106 answers carrying a ledger between them, and
a reader acts on that field: it is the difference between a premise they can
go and test and one they can only accept.

**The reason it had never been asked was where the table lived.** The
declaration sat under ``themis/output/``, and no verifier module may import
the output layer — so the only statement of what an assumption ID means was
one an audit was forbidden to read, and the audit said so in its own
docstring: re-stating the table would be transcription rather than
verification, and it was right about that.

What an assumption ID means is not the output layer's to say. It is the same
kind of fact as what a status word claims, it is keyed on a name, and it sits
beside the two vocabularies it classifies into — which were already in
``themis.ledger``. So the module moved out of ``output``, and the audit reads
a declaration instead of a producer.

The same table settles a third thing, and says so in its own header: who can
overrule an assumption "is a property of the assumption". ``provenance`` is
that answer — withdraw it, choose again, or nothing — for every layer but the
functional form, and the audit read the first two columns of the row and not
the third. It had been left to the checks that ask whether the answer records
a caller's input, and those only ask of a line that CLAIMS one; a line
relabelled ``inherent`` claims nothing, so a premise the caller supplied could
reach a reader as one nobody can withdraw. Measured before the audit read it:
430 named lines outside the functional form, every one agreeing with the
declaration.

The range is the table's own: it is keyed on the assumption's NAME, so a line
naming none is not one it can be right or wrong about. Those come from the
two proposal channels, and which they are is pinned in
``test_a_ledger_line_says_the_assumption_it_is``. The third column's range is
one layer narrower: who settled a SHAPE is the run's fact, the glossary
refuses to answer for it, and the line is held to the mechanism block instead.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

from themis.assumption_glossary import answerable, declares
from themis.verifier.assumption_ledger_rules import (
    _check_each_line_is_the_assumption_it_names,
)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _ledger(name: str) -> list:
    result = SHAPES[name]["result"] or {}
    return (((result.get("extensions") or {}).get("assumption_ledger") or {})
            .get("assumptions") or [])


LEDGERS = [name for name in sorted(SHAPES) if _ledger(name)]

#: One line that names an assumption, and one that names none. Taken by the
#: property rather than by row name: which sample sits under a given name is
#: a fact about the collection, not about either kind of line.
NAMED = next((name, i) for name in LEDGERS
             for i, e in enumerate(_ledger(name))
             if isinstance(e, dict) and isinstance(e.get("id"), str))
UNNAMED = next(((name, i) for name in LEDGERS
                for i, e in enumerate(_ledger(name))
                if isinstance(e, dict) and "id" not in e), None)

#: The layer whose provenance is the run's rather than the id's.
SHAPE = "functional_form"


def _named_lines():
    """``(name, i, id, declared layer)`` for every line naming an assumption."""
    for name in LEDGERS:
        for i, entry in enumerate(_ledger(name)):
            ident = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(ident, str) and ident:
                yield name, i, ident, str(declares(ident)[0])


#: A named line nobody can overrule, one somebody can, and a shape line whose
#: provenance the run settles — by property, for the reason given above.
NOBODY_CAN = next((name, i) for name, i, ident, layer in _named_lines()
                  if layer != SHAPE and str(answerable(ident)) == "inherent")
SOMEBODY_CAN = next((name, i) for name, i, ident, layer in _named_lines()
                    if layer != SHAPE
                    and str(answerable(ident)) != "inherent")
SHAPE_LINE = next((name, i) for name, i, _ident, layer in _named_lines()
                  if layer == SHAPE)


def test_every_line_that_names_an_assumption_says_what_that_name_means():
    """The honest half, counted rather than sampled.

    A floor rather than an equality on the count: what this guards is that
    the shape has not moved out from under it, and a corpus that grows a
    ledger is not that.
    """
    checked = 0
    for name in LEDGERS:
        for i, entry in enumerate(_ledger(name)):
            assumption_id = entry.get("id")
            if not isinstance(assumption_id, str) or not assumption_id:
                continue
            layer, testable = declares(assumption_id)
            assert entry.get("layer") == str(layer), (name, i, assumption_id)
            assert entry.get("testable") == testable, (name, i, assumption_id)
            checked += 1
    assert len(LEDGERS) >= 100, len(LEDGERS)
    assert checked >= 500, checked


@pytest.mark.parametrize("name", LEDGERS)
def test_an_honest_ledger_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    _check_each_line_is_the_assumption_it_names(_ledger(name))


def test_a_testability_the_assumption_does_not_have_is_refused():
    """The counterexample. A reader decides from this field whether there
    is anything they could go and do."""
    name, i = NAMED
    entries = copy.deepcopy(_ledger(name))
    entries[i]["testable"] = not entries[i]["testable"]
    with pytest.raises(VerificationError, match="testability"):
        _check_each_line_is_the_assumption_it_names(entries)


def test_a_layer_the_assumption_does_not_hold_up_is_refused():
    """The other one. A line moved to a milder layer reads as a milder
    assumption and is ranked as one."""
    name, i = NAMED
    entries = copy.deepcopy(_ledger(name))
    entries[i]["layer"] = "confidence"
    with pytest.raises(VerificationError, match="holds up"):
        _check_each_line_is_the_assumption_it_names(entries)


def test_a_named_line_that_says_nothing_about_testability_is_refused():
    """Silence is not the third state. The declaration answers for every
    name, so a named line that omits the field leaves the reader guessing at
    something the system knows."""
    name, i = NAMED
    entries = copy.deepcopy(_ledger(name))
    del entries[i]["testable"]
    with pytest.raises(VerificationError, match="testability"):
        _check_each_line_is_the_assumption_it_names(entries)


def test_a_line_that_names_no_assumption_is_outside_this():
    """The range, exercised rather than described.

    A declared silence is only a declaration if the same edit goes through
    where the declaration cannot reach. Asked with the edit that is refused
    two tests above.
    """
    assert UNNAMED is not None, "no corpus ledger line names nothing"
    name, i = UNNAMED
    entries = copy.deepcopy(_ledger(name))
    entries[i]["testable"] = not entries[i]["testable"]
    _check_each_line_is_the_assumption_it_names(entries)


def test_the_declaration_answers_for_a_name_nobody_declared():
    """Total, so the audit has no branch that quietly reaches nothing.

    An id no row matches is an identification assumption the data cannot
    answer — the same fallback the reader's side gets, for the same reason:
    a disclosure surface must not drop what nobody classified.
    """
    layer, testable = declares("an_assumption_nobody_ever_wrote_down")
    assert str(layer) == "identification"
    assert testable is False


def test_the_audit_reads_the_declaration_and_not_the_assembler():
    """The independence pin, as it now stands.

    What an audit must not read is the thing it audits: the ledger is
    assembled in ``themis.output.result_orchestrator``, and an audit
    importing it would agree with it by construction. The glossary is not
    that — it is the contract's statement of what a name means, and reading
    it is what ``status_rules`` does with ``STATUS_CLAIMS``.
    """
    import themis.verifier.assumption_ledger_rules as rules

    tree = ast.parse(inspect.getsource(rules))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            root = "themis" if node.level == 2 else "themis.verifier"
            imported.add(f"{root}.{node.module}" if node.module else root)
        elif isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}

    assert "themis.assumption_glossary" in imported, sorted(imported)
    offending = sorted(m for m in imported if m.startswith("themis.output"))
    assert not offending, (
        f"the ledger audit imports {offending}; the assembler it audits is "
        f"themis.output.result_orchestrator, and an audit that reads the "
        f"output layer agrees with the producer by construction"
    )


# -------------------------------------------- the third thing an id settles


def test_every_named_line_outside_the_shape_says_who_can_overrule_it():
    """The honest half of the third column, counted rather than sampled.

    A floor, for the reason the first count in this file is one.
    """
    checked = 0
    for name, i, ident, layer in _named_lines():
        if layer == SHAPE:
            continue
        assert _ledger(name)[i].get("provenance") == str(answerable(ident)), (
            name, i, ident)
        checked += 1
    assert checked >= 400, checked


def test_a_lever_taken_away_is_refused():
    """The direction nothing asked. The record-reading checks look only at
    a line that claims a caller's input, and ``inherent`` claims none — so
    a premise the caller supplied could be told to the reader as one nobody
    can withdraw."""
    name, i = SOMEBODY_CAN
    entries = copy.deepcopy(_ledger(name))
    entries[i]["provenance"] = "inherent"
    with pytest.raises(VerificationError, match="who can overrule"):
        _check_each_line_is_the_assumption_it_names(entries)


@pytest.mark.parametrize("member", ["caller_asserted", "caller_chose",
                                    "default"])
def test_a_lever_handed_over_that_is_not_there_is_refused(member):
    """The other direction. The record-reading checks catch it only when the
    answer carries no record of any caller input at all; a run where the
    caller supplied something else walks it through."""
    name, i = NOBODY_CAN
    entries = copy.deepcopy(_ledger(name))
    entries[i]["provenance"] = member
    with pytest.raises(VerificationError, match="who can overrule"):
        _check_each_line_is_the_assumption_it_names(entries)


@pytest.mark.parametrize("member", ["inherent", "default", "caller_asserted",
                                    "caller_chose"])
def test_a_shape_line_is_not_asked_who_settled_it_here(member):
    """The third column's range, exercised rather than described.

    Who fixed a shape is the run's fact: the glossary raises rather than
    answer, and the line is held to the mechanism block by the check that
    reads that block. Asking here would either crash or hold the line to a
    value true of one family and false of the next.
    """
    name, i = SHAPE_LINE
    entries = copy.deepcopy(_ledger(name))
    entries[i]["provenance"] = member
    _check_each_line_is_the_assumption_it_names(entries)


def test_a_line_that_names_no_assumption_is_outside_the_third_column_too():
    """Keyed on the name, like the other two."""
    assert UNNAMED is not None, "no corpus ledger line names nothing"
    name, i = UNNAMED
    entries = copy.deepcopy(_ledger(name))
    entries[i]["provenance"] = (
        "llm_proposal" if entries[i].get("provenance") == "discovery"
        else "discovery")
    _check_each_line_is_the_assumption_it_names(entries)
