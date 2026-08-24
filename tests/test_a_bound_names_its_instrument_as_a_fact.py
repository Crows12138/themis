"""The instrument was a phrase, so the audit of it was a search.

A Balke-Pearl row prints a reference to a linear programme, because at a
general cardinality there is no closed form to print. That reference is a
sentence — and the instrument the polytope was fitted around lived
nowhere else on the row. So the rule that had to confirm it ran a regular
expression over the sentence.

Two things follow from that, and they are the two halves of this file.
A producer that reworded its sentence broke the audit, because the audit
was reading the wording. And a producer that fitted around the wrong
variable did not break it, because a sentence saying the right thing
about the wrong variable has the right shape. The row carries the
instrument as a field now: wording is free, and the name is checked
against what the graph can offer.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from referencing import Registry, Resource
import pytest

import themis
from tests.bounds_rows import row
from themis.verifier.bounds_rules import (
    _graph_instrument_candidates,
    verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError
from themis.input.syntactic_validator import validator_for


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "var", "name": "I"}]}


def _cause(frm, to):
    return {"kind": "cause", "forall": ["I"], "from": _atom(frm),
            "to": _atom(to)}


def _bp_program(extra_variables=(), extra_edges=()):
    """z → x → y with x ↔ y latent, plus whatever the case adds."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            *extra_variables,
            _cause("z", "x"),
            _cause("x", "y"),
            {"kind": "bidirected", "forall": ["I"],
             "left": _atom("x"), "right": _atom("y")},
            *extra_edges,
            {"kind": "query", "id": "bp",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


@pytest.fixture(scope="module")
def shipped():
    """The row the producer actually ships, and the programme behind it."""
    program = _bp_program()
    result = themis.run(program)["results"][0]
    return program, row(result, "balke_pearl_iv")


def _audit(program, bounds):
    verify_balke_pearl_iv_bounds_result(
        bounds, program=program,
        query_dict=program["statements"][-1]["query"],
    )


# --------------------------------------------------------- the fact is there


def test_the_producer_writes_the_instrument_down(shipped):
    program, bounds = shipped
    assert bounds["instrument"] == "z"


def test_the_sentence_no_longer_restates_it(shipped):
    """The same finding, one step further.

    The instrument lived inside the note, so the audit that had to confirm
    it read the sentence with a regular expression, and it was checked here
    by asserting the two agreed. They cannot disagree now for a stronger
    reason: the note has stopped naming it. A sentence restating a field
    beside it is a second record of that field, and what a note says is
    what nothing else on the row carries.
    """
    _, bounds = shipped
    assert bounds["instrument"] in bounds["lower_expression"]
    facts = [value for note in bounds["notes"]
             for value in (note.get("said") or {}).values()]
    assert facts and bounds["instrument"] not in facts


def test_the_envelope_carries_it(shipped):
    """A field the verifier reads has to survive the trip as JSON."""
    program, _ = shipped
    envelope = json.loads(json.dumps(themis.run(program)))
    shipped_row = row(envelope["results"][0], "balke_pearl_iv")
    assert shipped_row["instrument"] == "z"

    validator_for("query_result.schema.json").validate(envelope["results"][0])


# --------------------------------------------------- wording is the producer's

#: Same arm, same observables, same instrument; nothing else preserved.
#: The first of these is what the old rule refused — it opened on
#: "the smallest value" rather than on "min of P(", and the row was
#: rejected for how it read.
REWORDINGS = [
    pytest.param(
        "the smallest value P(y=true | do(x=true)) takes over the "
        "response-function polytope fitted to P(y, x | z)",
        id="no_canonical_opening"),
    pytest.param(
        "over the polytope fitted to P(y, x | z), the minimum of "
        "P(y=true | do(x=true))",
        id="facts_reordered"),
    pytest.param(
        "min{P(y=true | do(x=true)) : polytope fitted to P(y, x | z)}",
        id="set_builder"),
    pytest.param(
        "在拟合到 P(y, x | z) 的响应函数多面体上，P(y=true | do(x=true)) 的最小值",
        id="another_language"),
]


@pytest.mark.parametrize("sentence", REWORDINGS)
def test_the_same_bound_said_differently_is_the_same_bound(shipped, sentence):
    # Each of these fails the check that used to stand here, which is what
    # makes them counterexamples rather than cosmetic edits.
    assert not sentence.startswith("min of P(")
    program, bounds = shipped
    reworded = copy.deepcopy(bounds)
    reworded["lower_expression"] = sentence
    _audit(program, reworded)


# ------------------------------------------------------- the name is checked


def test_an_instrument_the_graph_cannot_offer_is_refused(shipped):
    """The tamper no amount of reading the sentence could catch.

    ``y`` is the outcome; the sentence is untouched and still says ``z``.
    An audit that recovers the instrument from the sentence recovers
    ``z``, agrees with itself, and passes.
    """
    program, bounds = shipped
    tampered = copy.deepcopy(bounds)
    tampered["instrument"] = "y"
    with pytest.raises(VerificationError, match="does not offer"):
        _audit(program, tampered)


def test_an_instrument_that_is_not_in_the_graph_at_all_is_refused(shipped):
    program, bounds = shipped
    tampered = copy.deepcopy(bounds)
    tampered["instrument"] = "nobody"
    with pytest.raises(VerificationError, match="does not offer"):
        _audit(program, tampered)


def test_a_variable_with_an_edge_into_the_outcome_is_refused():
    """Exclusion, read off the graph: w → x and w → y, so not an instrument.

    The graph offers ``z`` here and not ``w``, which is what makes this
    case a refusal rather than a tie.
    """
    program = _bp_program(
        extra_variables=({"kind": "variable", "predicate": "w",
                          "domain": [True, False]},),
        extra_edges=(_cause("w", "x"), _cause("w", "y")),
    )
    bounds = row(themis.run(program)["results"][0], "balke_pearl_iv")
    tampered = copy.deepcopy(bounds)
    tampered["instrument"] = "w"
    with pytest.raises(VerificationError, match="does not offer"):
        verify_balke_pearl_iv_bounds_result(
            tampered, program=program,
            query_dict=program["statements"][-1]["query"],
        )


def test_a_row_carrying_no_instrument_is_refused(shipped):
    program, bounds = shipped
    tampered = copy.deepcopy(bounds)
    del tampered["instrument"]
    with pytest.raises(VerificationError, match="must name the instrument"):
        _audit(program, tampered)


def test_a_sentence_that_drops_the_instrument_is_refused(shipped):
    """The rendering owes the reader the fact it renders.

    Not the other way round: this is refused because the reader would be
    shown a bound and not what it rests on, not because the rule needs
    the sentence in order to know.
    """
    program, bounds = shipped
    tampered = copy.deepcopy(bounds)
    tampered["lower_expression"] = "min of P(y=true | do(x=true))"
    with pytest.raises(VerificationError, match="must name the instrument"):
        _audit(program, tampered)


def test_an_estimand_that_is_not_the_arm_is_refused(shipped):
    """The field the canonical opening phrase was standing in for."""
    program, bounds = shipped
    tampered = copy.deepcopy(bounds)
    tampered["estimand"] = "ace"
    with pytest.raises(VerificationError, match="single arm"):
        _audit(program, tampered)


# ------------------------------------------- and checked no harder than that


def test_the_graph_condition_is_necessary_and_not_the_producers_choice():
    """Two candidates: the producer declines to guess, the rule does not care.

    The rule audits which variable was NAMED, and a graph offering two
    instruments forbids neither. Reading it as the producer's criterion
    would make the audit refuse a row for a reason that belongs to
    picking, which is not what this row claims to have done.
    """
    program = _bp_program(
        extra_variables=({"kind": "variable", "predicate": "z2",
                          "domain": [True, False]},),
        extra_edges=(_cause("z2", "x"),),
    )
    offered = _graph_instrument_candidates(program, treatment="x", outcome="y")
    assert offered == {"z", "z2"}

    query = program["statements"][-1]["query"]
    for named in sorted(offered):
        bounds = {
            "method": "balke_pearl_iv",
            "estimand": "arm_probability",
            "tightness": "sharp",
            "instrument": named,
            "lower_expression":
                f"min of P(y=true | do(x=true)) over P(y, x | {named})",
            "upper_expression":
                f"max of P(y=true | do(x=true)) over P(y, x | {named})",
            "assumptions": [
                "iv1_relevance",
                "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
                "iv3_independence_instrument_independent_of_unmeasured_"
                "confounders",
            ],
        }
        verify_balke_pearl_iv_bounds_result(
            bounds, program=program, query_dict=query)


def test_the_candidates_are_read_off_the_edges_and_nothing_else():
    """Relevance and exclusion, and not the declaration or the cardinality.

    A candidate with no declared domain is one the producer would refuse
    to build a response-function partition over. That refusal is the
    producer's, about the data it would need; the graph still offers the
    variable, and a rule auditing a name does not get to import the
    other question.
    """
    program = _bp_program(extra_edges=(_cause("undeclared", "x"),))
    assert _graph_instrument_candidates(
        program, treatment="x", outcome="y") == {"z", "undeclared"}
