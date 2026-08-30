"""One envelope, two kinds, and one sentence per thing that is wrong with it.

Both halves of #477 are checked here, because they are one change: the
sentences moved off the raise sites BECAUSE the check they were written at
became one check. What made nineteen f-strings cheap was five exception
classes needing five carriers — two of them the same name for the same job
— so the copy this file pins is the copy that is gone.

What it does NOT check is that the wording is good. That is a reader's
judgement, and the gates that hold every member to both languages and to
the same holes are the generic ones over ``language.VOCABULARIES``.
"""
from __future__ import annotations

import pytest

from themis import language
from themis.shape_words import Shape
from themis.types import Program, VariableDeclaration
from themis.workflow import bundle, parameter_fill, variable_framing
from themis.workflow.bundle import MalformedBundleError, Refuses


def _skeleton_bundle(**over) -> dict:
    return {"version": bundle.VERSION, "kind": parameter_fill.BUNDLE_KIND,
            "skeletons": [], **over}


def _patch_bundle(**over) -> dict:
    return {"version": bundle.VERSION, "kind": variable_framing.BUNDLE_KIND,
            "patches": [], **over}


def _empty() -> Program:
    return Program(version="0.1", objects=(), statements=())


def _as_a_word(member) -> dict:
    """A word on its way out of the process: the set it belongs to and
    its token, for the surface that knows the reader to look up."""
    return {"vocabulary": "shape", "token": member.value}


# --- the envelope is one envelope --------------------------------------------

def test_the_two_kinds_share_one_exception_class():
    """The copy this item removed, pinned as an identity.

    Two modules each defined a ``MalformedBundleError``, so a caller who
    imported one and caught it did not catch the other — a distinction
    nothing in the tree ever used, and the kernel's own docstring named a
    single class for both kinds.
    """
    assert parameter_fill.MalformedBundleError is MalformedBundleError
    assert variable_framing.MalformedBundleError is MalformedBundleError


def test_the_two_kinds_share_one_version():
    """It was declared in three modules and written as a literal in a
    fourth — four places for a constant whose only job is that both ends
    of a round trip agree about it."""
    assert parameter_fill.BUNDLE_VERSION is bundle.VERSION
    assert variable_framing.BUNDLE_VERSION is bundle.VERSION
    from themis import kernel
    assert kernel.BUNDLE_VERSION is bundle.VERSION


@pytest.mark.parametrize("kind", ["skeleton", "patch"])
@pytest.mark.parametrize("fault, species", [
    ("not_a_dict", Refuses.IS_NOT),
    ("wrong_kind", Refuses.KIND_IS_LIMITED_TO),
    ("wrong_version", Refuses.VERSION_IS_LIMITED_TO),
    ("records_not_a_list", Refuses.IS_NOT),
])
def test_each_envelope_fault_is_the_same_species_either_side(kind, fault,
                                                             species):
    """The point of one function: a fault in the envelope says the same
    thing whichever kind of records were meant to be inside it."""
    merge, make, key = (
        (parameter_fill.merge_skeleton_bundle, _skeleton_bundle, "skeletons")
        if kind == "skeleton" else
        (variable_framing.merge_variable_declaration, _patch_bundle, "patches"))
    given = {
        "not_a_dict": ["not", "a", "dict"],
        "wrong_kind": make(kind="something_else"),
        "wrong_version": make(version="0.2"),
        "records_not_a_list": make(**{key: "not a list"}),
    }[fault]
    with pytest.raises(MalformedBundleError) as raised:
        merge(_empty(), given)
    assert raised.value.species is species


def test_one_kind_handed_to_the_other_merger_is_refused():
    """The envelope check is what keeps the two apart, and it is now one
    piece of code — so this is the case that would break first if the pair
    it is parameterised by ever went missing."""
    with pytest.raises(MalformedBundleError) as to_framing:
        variable_framing.merge_variable_declaration(_empty(),
                                                    _skeleton_bundle())
    with pytest.raises(MalformedBundleError) as to_parameters:
        parameter_fill.merge_skeleton_bundle(_empty(), _patch_bundle())
    for raised in (to_framing, to_parameters):
        assert raised.value.species is Refuses.KIND_IS_LIMITED_TO


def test_the_records_key_is_the_other_half_of_the_pair():
    """``kind`` alone does not say where the records are; a bundle of the
    right kind with the records under the wrong key is still not one."""
    with pytest.raises(MalformedBundleError) as raised:
        bundle.envelope(_skeleton_bundle(), kind=parameter_fill.BUNDLE_KIND,
                        key="patches")
    assert raised.value.species is Refuses.IS_NOT
    assert raised.value.words["shape"] == _as_a_word(Shape.LIST)


# --- the shape is a word, not a sentence -------------------------------------

def test_a_shape_travels_as_a_word_and_reaches_each_reader_in_their_own():
    """Six of the nine species are "{where} must be {shape}", and the shape
    is the noun the LLM-side front door already interpolates. Written as a
    species each, a seventh shape would be a seventh sentence in two
    languages rather than one member in two."""
    with pytest.raises(MalformedBundleError) as raised:
        parameter_fill.merge_skeleton_bundle(_empty(), "not a dict")
    exc = raised.value
    assert exc.words["shape"] == _as_a_word(Shape.DICT)
    rendered = {lang: language.assemble(exc.species.words, exc.said,
                                        exc.words, lang)
                for lang in sorted(language.written())}
    assert rendered["zh"] != rendered["en"]
    assert "一个字典" in rendered["zh"]
    assert "a dict" in rendered["en"]
    assert "Shape." not in rendered["zh"] and "DICT" not in rendered["zh"]


def test_the_path_is_a_symbol_and_reads_the_same_to_everyone():
    """The half that always worked. Keeping the path a FACT rather than
    folding it into the sentence is what lets one species cover six
    sites — and a path written as English prose would be a sentence
    wearing a slot's clothes."""
    program = Program(version="0.1", objects=(),
                      statements=(VariableDeclaration(predicate="x"),))
    with pytest.raises(MalformedBundleError) as raised:
        variable_framing.merge_variable_declaration(
            program, _patch_bundle(patches=[{
                "kind": variable_framing.PATCH_KIND, "predicate": "x",
                "fields": {"defaulted": "not a list"}}]))
    where = raised.value.said["where"]
    assert where == "variable_patch[x].fields.defaulted"
    assert raised.value.words["shape"] == _as_a_word(
        Shape.LIST_OF_FIELD_NAMES)


# --- a refusal keeps the facts a caller acts on ------------------------------

def test_the_indices_a_caller_points_at_survive_as_a_list():
    """``unfilled`` is what a surface highlights. Reading it back out of a
    rendered sentence is not reading it, so it stays an attribute as well
    as a fact of the sentence."""
    exc = parameter_fill.UnfilledSkeletonError([0, 3])
    assert exc.unfilled == [0, 3]
    assert exc.said["count"] == "2"
    assert "0" in exc.said["indices"] and "3" in exc.said["indices"]


def test_a_conflict_keeps_the_four_facts_it_is_about():
    program = Program(
        version="0.1", objects=(),
        statements=(VariableDeclaration(predicate="y", time_window="12w"),))
    with pytest.raises(variable_framing.VariablePatchConflictError) as raised:
        variable_framing.merge_variable_declaration(
            program, _patch_bundle(patches=[{
                "kind": variable_framing.PATCH_KIND, "predicate": "y",
                "fields": {"time_window": "4w"}}]))
    exc = raised.value
    assert (exc.predicate, exc.field, exc.existing, exc.incoming) == (
        "y", "time_window", "12w", "4w")
    assert exc.species is Refuses.FIELD_IS_ALREADY_SET_DIFFERENTLY


@pytest.mark.parametrize("cls, species", [
    (variable_framing.UnknownPredicateError, Refuses.NO_DECLARATION_TO_PATCH),
    (variable_framing.VariablePatchConflictError,
     Refuses.FIELD_IS_ALREADY_SET_DIFFERENTLY),
    (variable_framing.VariablePatchAnsweredTwiceError,
     Refuses.FIELD_IS_ANSWERED_TWICE),
    (parameter_fill.UnfilledSkeletonError, Refuses.SKELETONS_ARE_STILL_EMPTY),
])
def test_the_channel_and_the_species_are_two_questions(cls, species):
    """Four classes built their sentence in ``__init__`` rather than at a
    raise site, which put them outside the scan that reads raise sites and
    is why the family looked smaller than it was. The class still says
    which door to catch at; the species says what went wrong."""
    assert issubclass(cls, language.Voiced)
    assert species in set(Refuses)
