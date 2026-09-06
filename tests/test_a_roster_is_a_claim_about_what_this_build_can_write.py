"""A roster held to a corpus is a statement about that corpus.

Two rosters in ``gap_claim_rules`` sort a statement's slots into names and
non-names, and between them they decide what either rule in that module
asks about: the name rule skips a slot it does not find in the first, and
the copy rule reads only what it finds in the second. A slot in NEITHER is
therefore silent twice over — not refused wrongly, which would be loud, but
unasked, which is not.

Their coverage was held to the keys the ANSWER SHAPES produce. That is a
claim about the shapes, and its range is where its author was standing:
eighteen slots this package can write were in neither roster, none of them
reachable by any answer the corpus contains. They are bound to the
STATEMENTS now, at import, and this file says what that binding covers and
what it does not.

What it does not cover is worth as much as what it does. A gap report also
carries statements out of vocabularies that live in the output layer, which
no verifier may import — so the binding inside the rule reaches what
``themis.gaps`` declares and no further, and the shortfall is a number
here rather than a silence there.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from themis import gaps as _gaps
from themis.kernel import _premises_of
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import (
    _COPIED_FROM,
    _NAMES,
    _NOT_NAMES,
    _slots_of,
    every_said_mapping,
    slots_the_statements_declare,
    verify_gap_quotes,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every slot the corpus actually shows, with the statement it sits in.
SHOWN = sorted({
    (statement or "", key)
    for pair in SHAPES.values()
    for _where, statement, said in every_said_mapping(
        (pair["result"] or {}).get("data_gap_report") or {})
    for key in said
})


# ------------------------------------------------------- what binds, binds


def test_every_slot_a_statement_declares_is_classified_exactly_once():
    """The binding itself, asserted where it can be argued with.

    It runs at import, so a failure here is a failure to import the
    package at all; stated again as a test because an import-time check
    says nothing about WHICH slot when it passes, and the size of the
    space it covers is the point.
    """
    space = slots_the_statements_declare()
    assert len(space) == 90, len(space)
    assert not space - set(_NAMES) - set(_NOT_NAMES)
    assert not set(_NAMES) & set(_NOT_NAMES)


def test_a_literal_brace_declares_no_slot():
    """``{{`` is how a template writes a brace, and one of them looks like
    a variable.

    ``P(y_x, y'_{{x'}})`` reaches a reader as ``P(y_x, y'_{x'})`` and asks
    for nothing. Read without stripping the escapes, the space above
    demands a classification for a slot no statement has — and the way
    that demand gets satisfied is by widening a roster, which is the
    opposite of what a roster is for.
    """
    assert _slots_of("P(y_x, y'_{{x'}})") == set()
    assert _slots_of("{variable} ⊥ {{{extras}}} | {{{conditioning}}}") == {
        "variable", "extras", "conditioning"}


def test_the_shape_of_an_argument_is_not_a_roster_entry():
    """What the bug above had already cost, kept as the guard against it.

    One statement shows a caller the shape of an argument —
    ``misclassification={{<name>: {{confusion_matrix, states}}}}`` — which
    reaches a reader as literal braces. Read as slots, those words look
    like four the rosters must classify, and four of them were classified,
    which is a roster widening to satisfy a demand a bug had made. Neither
    the corpus nor the space has any of them, so the entries spoke for
    nothing.
    """
    phantoms = {"confusion_matrix", "validation_counts", "error_variance",
                "structure", "x"}
    assert not phantoms & slots_the_statements_declare()
    assert not phantoms & {key for _statement, key in SHOWN}
    assert not phantoms & set(_NAMES)
    assert not phantoms & set(_NOT_NAMES)


def test_every_slot_the_corpus_shows_is_classified():
    """The claim this file replaces, kept because it is still true and
    still worth measuring: the shapes exercise slots the binding reaches
    and slots it does not."""
    unclassified = sorted(
        {key for _statement, key in SHOWN}
        - set(_NAMES) - set(_NOT_NAMES))
    assert not unclassified, unclassified


def test_what_the_binding_cannot_reach_is_a_number_rather_than_a_silence():
    """The shortfall, written down so it can shrink.

    A gap report carries statements out of vocabularies the output layer
    ships — how much data to collect, what a framing field is called —
    and no verifier may import that layer. So the binding covers what
    ``themis.gaps`` declares, the corpus shows slots beyond it, and the
    two numbers are here beside each other. Every one of those is
    classified all the same, by the test above; what is missing is the
    guarantee, not the coverage.
    """
    space = slots_the_statements_declare()
    beyond = sorted({key for _statement, key in SHOWN} - space)
    assert len(beyond) == 19, beyond
    assert not set(beyond) - set(_NAMES) - set(_NOT_NAMES)


# --------------------------------------- a slot's meaning is its sentence's


def test_one_slot_answers_differently_in_two_statements():
    """``target`` is the instance the module's own prose predicted.

    Under the statement about transporting an answer it is a population,
    and the program declares every population there is. Under the three
    about a dose-response curve and a collider it is a variable. A table
    with one answer per slot NAME is right about one of those.
    """
    transported = _COPIED_FROM.get(
        ("transport_rests_on_s_admissibility", "target"))
    assert transported is not None
    assert _COPIED_FROM.get(
        ("the_question_asks_for_a_dose_response_curve", "target")) is None
    assert _COPIED_FROM.get((None, "target")) is None

    seen = {statement for statement, key in SHOWN if key == "target"}
    assert "transport_rests_on_s_admissibility" in seen
    # Four statements and one that has no name of its own. A nameless
    # statement resolves to the general entry by construction — the pair
    # it is looked up under IS the wildcard — which is what a slot in a
    # statement that declares nothing about itself should get.
    assert len(seen) == 5, sorted(seen)
    assert "" in seen


def test_a_population_this_program_does_not_declare_is_refused():
    """And the same word, in the statement that is not about a population,
    is left to the rule whose question it is."""
    refused = passed = 0
    for name, pair in SHAPES.items():
        for where, statement, said in every_said_mapping(
                (pair["result"] or {}).get("data_gap_report") or {}):
            if "target" not in said:
                continue
            forged = json.loads(json.dumps(pair["result"]))
            node = forged["data_gap_report"]
            for step in where.split("."):
                node = node[int(step)] if step.isdigit() else node[step]
            node["target"] = "a_population_nobody_declared"
            context = _premises_of(pair["program"], pair["result"])[3]
            try:
                verify_gap_quotes(forged, context)
            except VerificationError:
                refused += 1
            else:
                passed += 1
    assert (refused, passed) == (11, 22), (refused, passed)


# ----------------------------------------------- the rosters, each measured


@pytest.mark.parametrize("key,count", [
    ("methods", 73), ("field", 19), ("population", 16), ("source", 10),
    ("kind", 11), ("target", 11),
])
def test_each_new_roster_speaks_for_the_sites_it_claims(key, count):
    """Per slot, so a narrowing shows up as a number rather than as a
    quiet pass. ``target`` counts only the statement whose answer it is."""
    seen = 0
    for pair in SHAPES.values():
        for _where, statement, said in every_said_mapping(
                (pair["result"] or {}).get("data_gap_report") or {}):
            if key not in said:
                continue
            entry = (_COPIED_FROM.get((statement, key))
                     or _COPIED_FROM.get((None, key)))
            if entry is not None:
                seen += 1
    assert seen == count, seen


def test_the_statement_index_is_what_says_which_tables_hold_statements():
    """Derived rather than listed, and the difference is the whole point.

    A list of table names is the same kind of claim as a roster: a table
    added beside the others would be outside the space while looking like
    it was inside it. ``BY_SENTENCE`` and ``BY_NAME`` are what say which
    members a report's statements can be.
    """
    known = {str(member) for member in _gaps.BY_SENTENCE.values()}
    known |= {str(member) for member in _gaps.BY_NAME.values()}
    assert len(known) == 125, len(known)
    shown = {statement for statement, _key in SHOWN if statement}
    # And the fifteen the index does not know, which is the same shortfall
    # the slot count above measures, seen from the statement side: how
    # much data to collect, what a framing field is called, why a fit was
    # refused. Their vocabularies live in the output layer.
    assert len(shown - known) == 15, sorted(shown - known)[:8]
