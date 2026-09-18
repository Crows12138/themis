"""A descriptor is a function of the question, so it is rebuilt and not sampled.

``verify_proximal_estimand`` says in its own first paragraph what it is
for: identifiability is re-derived from the QUERY's roles, so a block
naming different ones describes a study nobody ran. Its second paragraph
said "what is checkable here is the whole of it, because every field is
the query restated" -- and the code checked eight fields of twenty.

That sentence was true when it was written. The bridge channel then
arrived with twelve more: the estimator it names, and each bridge's two
sieves with their widths and their ridge. A claim of totality kept in a
docstring cannot notice a field arriving, so 101 declared leaves sat
under this block, every one of them covered by the sentence and asked
about by nothing.

So the shape changed rather than the list growing. The descriptor is
rebuilt from the question and compared whole, which is what makes the
totality structural: a field on either side that the other does not have
is a mismatch, and the next field cannot arrive unheld. The tests below
are in two halves for that reason -- the fields, and the SET of fields.

One narrowing is recorded rather than fixed: the block writes a sieve
factor's variable by its predicate alone where it writes the treatment
and the outcome as full labels, so a term about ``x(u)`` and one about
``x(nobody)`` reach a reader as the same word. Spelling them differently
in the verifier would refuse every honest answer; the last test says so
instead of a comment saying so.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import Atom, BasisFamily, ConstTerm, SieveFactor, SieveTerm
from themis.verifier.rules import (
    _proximal_sieve,
    _proximal_width,
    _the_proximal_descriptor,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _block(result):
    return (result.get("extensions") or {}).get("proximal_estimand")


#: Derived rather than listed, so a corpus that grows a proximal answer is
#: asked the same questions without anybody remembering to add it here.
PROXIMAL_ROWS = sorted(
    name for name, pair in SHAPES.items()
    if isinstance(_block(pair["result"]), dict))
BRIDGE_ROWS = sorted(
    name for name in PROXIMAL_ROWS
    if _block(SHAPES[name]["result"]).get("channel_kind") == "bridge_channel")
DISCRETE_ROWS = sorted(set(PROXIMAL_ROWS) - set(BRIDGE_ROWS))
TWO_BRIDGE_ROWS = sorted(
    name for name in BRIDGE_ROWS
    if "treatment_bridge_moment_terms" in _block(SHAPES[name]["result"]))


def _refused(name, edit, match):
    pair = SHAPES[name]
    bad = copy.deepcopy(pair["result"])
    edit(_block(bad))
    with pytest.raises(Exception, match=match):
        the_door_for(pair["result"])(pair["program"], bad)


def test_the_corpus_asks_these_questions_of_something():
    """Rosters that came out empty would make every test below pass while
    asking nothing."""
    assert (len(PROXIMAL_ROWS), len(BRIDGE_ROWS), len(TWO_BRIDGE_ROWS)) == \
        (14, 7, 3)


@pytest.mark.parametrize("name", PROXIMAL_ROWS)
def test_a_proximal_answer_is_accepted(name):
    """First, because a forgery refused by an answer the doors already
    refuse proves nothing."""
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


# ------------------------------------------------------- the set of fields


@pytest.mark.parametrize("name", PROXIMAL_ROWS)
def test_the_rebuild_produces_exactly_the_fields_the_block_has(name):
    """The claim the old prose made, as a claim something holds. Not "the
    fields agree" -- that the two sides have the SAME fields, which is
    what nothing was asking when twelve of them arrived."""
    pair = SHAPES[name]
    from themis.kernel import _premises_of
    _ast, _prog, query_stmt, _ctx = _premises_of(pair["program"],
                                                 pair["result"])
    assert set(_the_proximal_descriptor(query_stmt.query)) == \
        set(_block(pair["result"]))


@pytest.mark.parametrize("name", PROXIMAL_ROWS)
def test_a_field_the_question_does_not_ask_for_is_refused(name):
    """A descriptor field this rule cannot rebuild is a field nobody is
    holding, which is the state the last twelve arrived in.

    Asked of the rule rather than through a door, because the block
    declares ``additionalProperties: false`` and the schema refuses an
    extra field first. That makes this check unreachable from outside
    TODAY and worth writing anyway: the twelve did not arrive as strays,
    they arrived with the schema growing to admit them, and on that day
    the schema says yes and this says no.
    """
    from themis.kernel import _premises_of
    from themis.verifier import verify_proximal_estimand

    pair = SHAPES[name]
    _ast, _prog, query_stmt, _ctx = _premises_of(pair["program"],
                                                 pair["result"])
    block = dict(_block(pair["result"]))
    block["outcome_bridge_curvature"] = 3
    with pytest.raises(Exception, match="which the question does not ask for"):
        verify_proximal_estimand(block, query_stmt.query)


@pytest.mark.parametrize("name", DISCRETE_ROWS)
def test_a_field_the_question_declares_going_missing_is_refused(name):
    """``latent_cardinality`` is the one field the question declares that
    the contract does not require, so it is the one a producer could drop
    and still be handed to a rule. How many states the confounder is
    assumed to have decides whether the matrix inverts at all."""
    def edit(block):
        block.pop("latent_cardinality")
    _refused(name, edit, "leaves out")


# ------------------------------------------------------------- the fields


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_another_estimator_is_refused(name):
    """Another MEMBER of the declared set, not a word outside it: which
    of the three answers the bridges support is being reported decides
    which assumption has to hold for it to be right, and the schema
    cannot tell one member from another."""
    def edit(block):
        block["estimator"] = ("doubly_robust"
                              if block["estimator"] != "doubly_robust"
                              else "outcome_regression")
    _refused(name, edit, "records estimator as")


@pytest.mark.parametrize("name", PROXIMAL_ROWS)
def test_another_method_is_refused(name):
    """``method`` and ``channel_kind`` are one distinction in two
    vocabularies; only the second was ever held."""
    def edit(block):
        block["method"] = "proximal_matrix" \
            if block["method"] == "proximal_bridge" else "proximal_bridge"
    _refused(name, edit, "records method as")


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_a_sieve_over_another_variable_is_refused(name):
    def edit(block):
        block["outcome_bridge_moment_terms"][0][0]["variable"] += "_forged"
    _refused(name, edit, "records outcome_bridge_moment_terms as")


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_a_sieve_of_another_basis_is_refused(name):
    def edit(block):
        factor = block["outcome_bridge_span_terms"][0][0]
        factor["basis"] = ("hermite" if factor["basis"] != "hermite"
                           else "fourier")
    _refused(name, edit, "records outcome_bridge_span_terms as")


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_a_sieve_of_another_dimension_is_refused(name):
    """And it is refused twice over: the dimension itself, and the width
    that is arithmetic on it."""
    def edit(block):
        block["outcome_bridge_moment_terms"][0][0]["dimension"] += 1
    _refused(name, edit, "records outcome_bridge_moment_")


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_a_width_that_is_not_the_arithmetic_is_refused(name):
    """A width is the one field here computed from the others, so it is
    recomputed rather than compared to a copy of itself."""
    def edit(block):
        block["outcome_bridge_span_width"] += 1
    _refused(name, edit, "records outcome_bridge_span_width as")


@pytest.mark.parametrize("name", BRIDGE_ROWS)
def test_a_ridge_nobody_asked_for_is_refused(name):
    def edit(block):
        block["outcome_bridge_ridge"] = 0.5
    _refused(name, edit, "records outcome_bridge_ridge as")


@pytest.mark.parametrize("name", TWO_BRIDGE_ROWS)
def test_the_second_bridge_is_held_like_the_first(name):
    """Two bridges is where the conditions a reader is told about double,
    and the treatment side arrived later than the outcome side."""
    def edit(block):
        block["treatment_bridge_span_terms"][0][0]["dimension"] += 2
    _refused(name, edit, "records treatment_bridge_span_")


@pytest.mark.parametrize("name", PROXIMAL_ROWS)
def test_conditions_the_channel_does_not_ask_of_the_data_are_refused(name):
    """What the answer rests on is a function of which bridges there are,
    and a reader who is told one fewer is told the data owes less."""
    def edit(block):
        block["data_conditions"] = block["data_conditions"][:-1]
    _refused(name, edit, "records data_conditions as")


# ------------------------------------------------------- and the narrowing


def test_the_arithmetic_is_the_arithmetic():
    """A term is the product of its factors and a sieve is the sum of its
    terms, stated here rather than inferred from one corpus row."""
    def factor(name, dimension):
        return SieveFactor(variable=Atom(predicate=name, args=()),
                           basis=BasisFamily("polynomial"),
                           dimension=dimension)
    terms = (SieveTerm(factors=(factor("z", 5), factor("x", 3))),
             SieveTerm(factors=(factor("w", 2),)))
    assert _proximal_width(terms) == (5 * 3 - 1) + (2 - 1) + 1
    assert _proximal_width(()) == 0


def test_a_sieve_names_its_variable_by_predicate_alone():
    """The narrowing, as a test rather than a comment.

    The block writes a factor's variable by its predicate where the same
    block writes the treatment as a full label, so two terms about two
    units of one variable reach a reader as the same word. What is held
    is what is written; spelling them apart here would refuse every
    honest answer this repository produces.
    """
    def factor(unit):
        return SieveFactor(
            variable=Atom(predicate="x", args=(ConstTerm(name=unit),)),
            basis=BasisFamily("polynomial"), dimension=2)
    one = _proximal_sieve((SieveTerm(factors=(factor("u"),)),))
    other = _proximal_sieve((SieveTerm(factors=(factor("nobody"),)),))
    assert one == other == [[{"basis": "polynomial", "dimension": 2,
                              "variable": "x"}]]
