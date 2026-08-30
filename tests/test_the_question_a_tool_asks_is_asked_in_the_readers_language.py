"""A question put to a person is put in that person's language.

The interactive equivalence-class feature asks a human which way an edge
goes, and adjudicates conflicts between what the data found and what
somebody asserted. Every one of those questions existed in Chinese and in
no other language — eighteen of them, the whole readable surface of a
four-module stack.

None was a missing translation. ``OrientationQuestion.prompt`` was typed
``string``, and its own schema described it as "a phrasing for a human.
Rendering, not data" — so twelve branches of one function each became the
author of a sentence, in whichever language that branch was written in.
What was missing was the slot. ``discovery.py``'s note in the language
debt table records the same finding for its own six, and the table's own
line about the standalone artifacts says what is owed: one cut across the
channel where a ``note`` is a rendered string.

This file checks the cut. A question now carries a SPECIES and this
occasion's names; ``asked`` is where a language enters; and the artifact
carries neither.
"""
from __future__ import annotations

import json
import pathlib
import string

import pytest

from themis import language
from themis.estimation.orientation import propagate_orientations
from themis.estimation.orientation_questions import (
    Asks,
    Says,
    asked,
    compile_orientation_questions,
    question_set_to_dict,
)
from themis.verifier.orientation_question_rules import (
    verify_orientation_questions)

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"


def _chain() -> object:
    """Three nodes, two undirected edges: two questions and no conflict."""
    return propagate_orientations(("a", "b", "c"), directed=[],
                                  undirected=[("a", "b"), ("b", "c")])


def _collider_overridden() -> object:
    """A→C←B from the data, and an answer that contradicts it."""
    return propagate_orientations(
        ("A", "B", "C"), directed=[("A", "C"), ("B", "C")],
        constraints=[("C", "A")])


# ---------------------------------------------------------------------------
# Both readers get the question
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang, opens, joins", [
    ("zh", "是 a 导致 b", "还是"),
    ("en", "does a cause b", "or"),
])
def test_the_direction_question_is_asked_in_each_language(lang, opens, joins):
    (q, _) = compile_orientation_questions(_chain()).questions[:2]
    text = asked(q, lang)
    assert text.startswith(opens)
    assert joins in text


def _unwritten(members) -> list[tuple[object, str]]:
    """(member, language) for every text this build owes and does not have."""
    return [(m, tag) for m in members for tag in language.written()
            if not m.words.get(tag)]


def _disagreeing_holes(members) -> list[object]:
    """Members whose languages do not ask for the same facts."""
    out = []
    for m in members:
        holes = {
            frozenset(name for _t, name, _s, _c
                      in string.Formatter().parse(text) if name)
            for text in m.words.values()
        }
        if len(holes) > 1:
            out.append(m)
    return out


class _Stub:
    """A member shape, not a member: enough for the two checks above to
    read, and registered with no vocabulary so nothing can reach it."""

    def __init__(self, words):
        self.words = words


def test_every_species_is_written_in_every_language_this_build_writes():
    """The completeness gate, by the build's own denominator rather than
    by a list here — so a language added tomorrow needs no edit."""
    assert not _unwritten((*Asks, *Says))


def test_the_two_languages_of_a_species_have_the_same_holes():
    """A hole one language has and the other does not is a fact one reader
    is handed and the other is not, which is the defect a second language
    is supposed to close rather than open."""
    assert not _disagreeing_holes((*Asks, *Says))


def test_the_completeness_gate_refuses_a_one_language_member():
    """The counterexample, run through the same function the gate uses.
    A gate checked only against material that passes it is a gate nobody
    has seen say no."""
    assert _unwritten([_Stub({"zh": "只有中文的句子"})])
    assert _unwritten([_Stub({"zh": "有中文", "en": ""})]), (
        "an empty string is a language declared and not written")


def test_the_hole_gate_refuses_a_fact_only_one_reader_gets():
    assert _disagreeing_holes(
        [_Stub({"zh": "有 {a} 也有 {b}", "en": "only {a}"})])


# ---------------------------------------------------------------------------
# The species is the fact; the sentence is the rendering
# ---------------------------------------------------------------------------


def test_a_conflict_carries_which_question_it_is_not_a_phrasing():
    (cq,) = [q for q in compile_orientation_questions(
        _collider_overridden()).questions if q.kind == "conflict"]
    assert cq.asks["vocabulary"] == "orientation_asks"
    assert cq.asks["token"] == "direction_contradicts_the_data"
    # The names travel as values, once, because they render the same for
    # every reader.
    assert cq.asks["said"] == {"settled": "A→C", "proposed": "C→A"}


def test_the_artifact_carries_no_language():
    """The envelope is the same envelope whoever reads it. A phrasing on
    it was the kernel choosing a reader, which is the thing this channel
    exists to stop."""
    d = question_set_to_dict(compile_orientation_questions(_chain()))
    blob = json.dumps(d, ensure_ascii=False)
    assert "导致" not in blob and "cause" not in blob
    for q in d["questions"]:
        assert set(q["asks"]) <= {"vocabulary", "token", "said", "words"}


def test_the_set_says_what_it_is_the_same_way():
    d = question_set_to_dict(compile_orientation_questions(_chain()))
    assert d["says"]["token"] == "the_set"
    assert d["says"]["said"] == {
        "conflicts": "0", "questions": "2", "edges": "2", "top": "2"}
    assert "conflict(s)" not in json.dumps(d) and "冲突" not in json.dumps(d)
    assert "0 个冲突" in language.spoke(d["says"], "zh")
    assert "0 conflict(s)" in language.spoke(d["says"], "en")


def test_the_tail_is_a_species_and_not_a_clause():
    """``leverage``'s extra clause used to be built at the site and glued
    on. Glue is where a second author gets in: the two shapes are two
    members now, and which one applies is the same test the glue made."""
    qs = compile_orientation_questions(_chain())
    tokens = {q.asks["token"] for q in qs.questions}
    assert tokens == {"which_direction_and_unlocks"}
    for q in qs.questions:
        assert q.asks["said"]["also"]


# ---------------------------------------------------------------------------
# The channel, and who else may use it
# ---------------------------------------------------------------------------


def test_the_statement_shape_is_declared_once_for_every_artifact():
    """A file rather than a copy in each artifact, because the six
    standalone artifacts are exactly the population that has been owed
    one — and a shape copied six times is six shapes the day one is
    edited."""
    shape = json.loads((SCHEMAS / "statement.schema.json").read_text("utf-8"))
    assert set(shape["$defs"]) == {"said", "words", "statement"}
    assert shape["$defs"]["statement"]["required"] == ["vocabulary", "token"]
    assert shape["$defs"]["statement"]["additionalProperties"] is False


def test_the_envelope_borrows_the_shape_rather_than_restating_it():
    """The envelope has carried statements since #395 and stated the shape
    in its own ``$defs`` — which is exactly why the standalone artifacts
    did not have it.

    The first version of this test asserted the two copies were equal and
    said so in the commit as a declared cost. The repository's own gate
    (``test_no_shape_is_recorded_in_two_documents``) refused that, and it
    was right: a shape written down twice is two shapes on the day one is
    edited, and a test pinning them equal is a promise to notice rather
    than a reason they cannot differ.
    """
    envelope = json.loads(
        (SCHEMAS / "query_result.schema.json").read_text("utf-8"))["$defs"]
    for name, target in (("said", "said"), ("words", "words"),
                         ("statedSentence", "statement")):
        assert envelope[name]["$ref"] == (
            f"statement.schema.json#/$defs/{target}"), name
        assert set(envelope[name]) == {"$ref", "description"}, (
            f"{name} borrows the shape and adds nothing to it")


def test_the_question_set_refers_to_the_shared_shape():
    art = json.loads(
        (SCHEMAS / "orientation_question_set.schema.json").read_text("utf-8"))
    asks = art["$defs"]["question"]["properties"]["asks"]
    assert asks["$ref"] == "statement.schema.json#/$defs/statement"
    assert art["properties"]["says"]["$ref"] == asks["$ref"]
    assert "prompt" not in art["$defs"]["question"]["properties"]
    assert "note" not in art["properties"]


def test_the_verifier_still_accepts_what_the_producer_makes():
    """The audit re-derives every number without the producer, and none of
    those numbers moved: this change is about the sentence beside them."""
    for build in (_chain, _collider_overridden):
        verify_orientation_questions(
            question_set_to_dict(compile_orientation_questions(build())))


def test_the_reader_s_door_takes_either_side_of_the_boundary():
    qs = compile_orientation_questions(_chain())
    d = question_set_to_dict(qs)
    for lang in ("zh", "en"):
        assert asked(qs.questions[0], lang) == asked(d["questions"][0], lang)
