"""The slots a reader fills leave here empty.

An investigation item's skeleton is the reader's copy of a patch. It goes
out on the envelope and comes back through ``apply_patch_and_run``
verbatim, which is the whole reason it exists: an LLM that copies one
"should just work". The rule that reads it read which PARAMETER the ask
is about — the target and the conditioning set, against the key the item
is filed under — and every field of the stub except the two the ask was
raised for.

Those two are the number and where it came from. Going out they are
empty, because this system is asking: it has no number, and it can have
no source for a number nobody has taken. Coming back they are full, and
that half was held — semantic validation refuses a statement whose source
is empty. One record, two directions, a rule on one of them.

WHAT THE SILENCE COST. The outbound source is a constant with one
producer and no second writing anywhere, so the census filed all thirty
of its leaves under "nothing either document writes" and three lies about
it walked through every public door: the word bent, the word blanked, and
a word from nowhere. The third is the one that matters. SKILL.md says the
source is shown to the user verbatim; an ask that leaves here already
reading "WHO 2020 cohort estimate" comes back unchanged with a real
number written beside it, and a provenance this system invented is now
under a figure somebody else supplied. The return door checks only that
the field is non-empty, so it passes.

The mirror is the blank one. A source of "" is refused on the way back
in, so a reader handed that form measures the number, returns it, and is
turned away for a field they were never given anything to write.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.runtime.numeric_estimator import ProbabilityKey
from themis.runtime.scheduler import _skeleton_for_parameter
from themis.types import Atom, ConstTerm
from themis.verifier import investigation_rules as rules
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))

LEAF = "investigation_requests.[].items.[].skeleton.annotations.source"

#: Every answer that files a probability ask. The CORPUS is the roster,
#: not the census's declaration: this frontier removes the leaf from that
#: file, so a gate keyed on it would parametrize over an empty list and
#: report skips where it used to report catches. The declaration is asked
#: one question instead, below, and it is the opposite question.
CARRYING = sorted(
    name for name, shape in SHAPES.items()
    if any(isinstance(item.get("skeleton"), dict)
           and item["skeleton"].get("kind") == "probability"
           for request in shape["result"].get("investigation_requests") or ()
           for item in request.get("items") or ()))


def _skeletons(result):
    """Every probability skeleton on one answer, with where it sits."""
    for ri, request in enumerate(
            result.get("investigation_requests") or ()):
        for ii, item in enumerate(request.get("items") or ()):
            skeleton = item.get("skeleton")
            if (isinstance(skeleton, dict)
                    and skeleton.get("kind") == "probability"):
                yield ri, ii, skeleton


def _forge(name, bend):
    """One answer with ``bend`` applied to its first probability stub."""
    forged = copy.deepcopy(SHAPES[name]["result"])
    ri, ii, _ = next(_skeletons(forged))
    bend(forged["investigation_requests"][ri]["items"][ii]["skeleton"])
    return forged


# --------------------------------------------------- what the corpus holds

def test_the_corpus_is_the_size_it_was_measured_at():
    assert len(CARRYING) == 30
    assert sum(1 for name in CARRYING
               for _ in _skeletons(SHAPES[name]["result"])) == 85


def test_the_census_no_longer_names_this_leaf_anywhere():
    """The declaration's side of the same fact, asked the only way that
    keeps meaning something after the leaf closes: not "these thirty rows
    still declare it" — they do not, that is the point — but "no row
    does"."""
    assert not [name for name, leaves in UNWITNESSED.items()
                if LEAF in leaves]


def test_every_stub_that_ever_left_here_has_both_slots_empty():
    """The claim the rule makes, stated as a fact about the corpus first.

    A rule whose corpus disagrees with it is a rule that refuses honest
    answers, and this is the cheapest place to find that out.
    """
    for name in CARRYING:
        for ri, ii, skeleton in _skeletons(SHAPES[name]["result"]):
            where = f"{name} investigation_requests[{ri}].items[{ii}]"
            assert skeleton["value"] is None, where
            assert skeleton["annotations"] == {
                "source": rules._A_SOURCE_NOBODY_HAS_YET}, where


def test_the_stub_is_the_same_five_fields_every_time():
    """No probability stub on the corpus carries a sixth field, which is
    why two slots is the whole of what a reader fills."""
    assert {tuple(sorted(skeleton)) for name in CARRYING
            for _, _, skeleton in _skeletons(SHAPES[name]["result"])} == {
        ("annotations", "given", "kind", "target", "value")}


# ------------------------------------------- the word, and where it is from

def test_the_placeholder_is_the_producers_own_word():
    """Restated in the verifier, pinned to the one function that writes it.

    A verifier importing the producer's literal agrees with it by
    construction, including with a producer that starts pre-filling the
    field. So the word is written twice and held equal here.
    """
    stub = _skeleton_for_parameter(ProbabilityKey(
        target_atom=Atom(predicate="y", args=(ConstTerm("u"),)),
        target_value=True,
        given=frozenset({(Atom(predicate="x", args=(ConstTerm("u"),)), True)}),
    ))
    assert stub["annotations"] == {"source": rules._A_SOURCE_NOBODY_HAS_YET}
    assert stub["value"] is None


def test_the_other_direction_fills_exactly_these_two_slots():
    """What an ANSWER to this ask looks like, written elsewhere already.

    The KB translator turns a knowledge-base hit into the same record with
    the reader's half supplied: a number in the value and a citation in
    the source. That it writes those two and nothing else is what makes
    "the slots a reader fills" a description of this record rather than a
    pair of fields this test happens to name.
    """
    from themis.kb import translator

    source = inspect.getsource(translator.kb_result_to_skeleton)
    assert '"value": result.value' in source
    assert '"source": result.provenance.citation' in source


def test_the_value_slots_absence_is_the_contracts_question():
    """Why one slot is read for absence and the other is not.

    The stub's schema requires ``value`` and requires nothing inside
    ``annotations``, so a missing value cannot reach any rule and a
    missing source can. A rule asking the first would be a branch no door
    reaches, which reports coverage it does not have.
    """
    schema = json.loads(
        (pathlib.Path(rules.__file__).parents[1] / "schemas"
         / "query_result.schema.json").read_text(encoding="utf-8"))
    stub = schema["$defs"]["parameterSkeleton"]
    assert "value" in stub["required"]
    assert "annotations" not in stub["required"]
    assert "required" not in stub["properties"]["annotations"]


# ------------------------------------------------------------- honest side

@pytest.mark.parametrize("name", CARRYING)
def test_an_honest_ask_is_accepted(name):
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


def test_no_answer_in_the_corpus_is_refused_by_this():
    """The rule reads a field thirty answers carry and two hundred do not,
    and a rule that refuses an answer for a field it has none of is the
    failure this sweep exists to catch."""
    for name, pair in SHAPES.items():
        verify_honestly(pair["program"], pair["result"])


def test_most_of_these_answers_reach_no_chain_door():
    """Where the rule is reached FROM, as a fact rather than an intention.

    An ask exists because something was missing, and an answer that was
    missing something mostly took no route — so ``verify`` refuses the
    majority of these envelopes before reading a word. The rule is held
    at ``verify_answer_claims``, which asks for the program and not the
    chain, and that is the only reason the thirty leaves below close.
    """
    import themis

    chained = [name for name in CARRYING
               if SHAPES[name]["result"].get("derivation") is not None]
    assert (len(chained), len(CARRYING)) == (5, 30)
    for name in CARRYING:
        assert the_door_for(SHAPES[name]["result"]) is (
            themis.verify if name in chained else themis.verify_answer_claims)


# ------------------------------------------------------------- forged side

#: Every kind of lie the two slots admit. The census bends a string three
#: ways; the fourth source below is the one that costs a reader something
#: rather than merely being wrong, and the last two are the slots emptied
#: instead of filled.
BENDS = {
    "source bent": lambda s: s["annotations"].__setitem__(
        "source", s["annotations"]["source"] + "_forged"),
    "source blanked": lambda s: s["annotations"].__setitem__("source", ""),
    "source from nowhere": lambda s: s["annotations"].__setitem__(
        "source", "xzz"),
    "source that reads like a citation": lambda s: s["annotations"].__setitem__(
        "source", "WHO 2020 cohort estimate"),
    "source dropped": lambda s: s["annotations"].pop("source"),
    "annotations dropped": lambda s: s.pop("annotations"),
    "value already measured": lambda s: s.__setitem__("value", 0.42),
}


@pytest.mark.parametrize("label", sorted(BENDS))
def test_a_slot_the_reader_did_not_fill_is_refused_on_every_answer(label):
    for name in CARRYING:
        forged = _forge(name, BENDS[label])
        with pytest.raises(VerificationError):
            the_door_for(forged)(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name", CARRYING)
def test_a_citation_this_system_wrote_is_refused(name):
    """The lie the frontier is about, put to every answer that can carry
    it. A source that reads like a real one is what a reader copies back
    without noticing, and what the return door then accepts."""
    forged = _forge(name, BENDS["source that reads like a citation"])
    with pytest.raises(VerificationError, match="asking for the number"):
        the_door_for(forged)(SHAPES[name]["program"], forged)


def test_the_refusal_says_which_of_the_two_slots_went_wrong():
    """Two harms, two sentences. This system's own figure coming back as
    somebody's measurement, and a provenance nobody wrote filed under
    somebody's figure, are not one complaint.

    The source's three bends are one complaint, though, and share a
    sentence: each of them is the same thing — not the word that says the
    field is still blank.
    """
    name = CARRYING[0]
    program = SHAPES[name]["program"]
    for label, phrase in (
            ("source blanked", "still blank"),
            ("source that reads like a citation", "did not write"),
            ("value already measured", "as their measurement"),
    ):
        forged = _forge(name, BENDS[label])
        with pytest.raises(VerificationError, match=phrase):
            the_door_for(forged)(program, forged)


def test_the_inbound_rule_this_one_pairs_with_is_the_narrower_one():
    """Said in the docstring, so held here: the return door refuses an
    empty source only where the value is declared an LLM prior, and a
    merged stub is ``structural`` unless the caller says otherwise. The
    pairing is real and it is not symmetric, and a comment claiming a
    rule that does not exist is worse than no comment."""
    from themis.input import semantic_validator as sv

    guard = inspect.getsource(sv._check_llm_prior_requires_source)
    assert 'stmt.provenance != "llm_prior"' in guard
    assert 'provenance=d.get("provenance", "structural")' in inspect.getsource(
        sv._to_statement)


def test_a_variable_patch_is_not_asked_these_questions():
    """The other kind of stub has neither slot — its fill surface is a
    fields map — so the rule is on the probability branch and a framing
    ask is not refused for lacking what it never carries."""
    patches = [skeleton for shape in SHAPES.values()
               for request in shape["result"].get("investigation_requests") or ()
               for item in request.get("items") or ()
               if isinstance(skeleton := item.get("skeleton"), dict)
               and skeleton.get("kind") == "variable_patch"]
    assert len(patches) == 311
    assert not any("annotations" in patch or "value" in patch
                   for patch in patches)
