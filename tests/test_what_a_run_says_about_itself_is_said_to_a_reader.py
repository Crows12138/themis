"""A ``note`` is what a run says about itself, and it is said to somebody.

Four standalone artifacts held that in a field typed ``string``. #467 built
the door — ``statement.schema.json`` — for the fifth, and named these four as
the population still owed one; this is that cut.

What the shape was doing is visible in the one that had two authors. A Meek
closure's note opened in English where the counts were computed and ended in
Chinese where the conflicts were counted, joined by a full-width semicolon:

    Meek propagation: 2 data-oriented + 0 constraint + 0 propagated edges
    directed, 0 still undetermined；1 constraint与数据冲突

Neither reader gets a sentence. A ``str`` holds one finished string, so the
first author wrote theirs and the second appended theirs, and the field had
nowhere to put a second language of either.

This file checks the cut, and checks the one judgement it rests on: a
statement that is a whole SENTENCE ends itself, and a statement that is an
ITEM of a larger sentence does not. That is the seam ``spoken`` and
``listed`` already draw, and getting it backwards is how a full stop lands
in the middle of a comma-separated list.
"""
from __future__ import annotations

import json
import pathlib
import string

import numpy as np
import pandas as pd
import pytest

from themis import language
from themis.estimation.discovery import (
    _format_note, markov_blanket, markov_blanket_to_dict)
from themis.estimation.discovery_words import NOTES, Blanket, Lagged
from themis.estimation.lagged_discovery import (
    discover_lagged_graph, lagged_discovery_to_dict)
from themis.estimation.orientation import (
    Says as PropagationSays, orientation_to_dict, propagate_orientations)
from themis.estimation.orientation_session import (
    SAYS_STATUS, Says as SessionSays, session_to_dict,
    start_orientation_session)

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "themis" / "schemas"

#: Every set this item added, and the artifact field each rides on.
THE_FOUR = {
    "orientation_propagation_says": PropagationSays,
    "orientation_session_says": SessionSays,
    "markov_blanket_says": Blanket,
    "lagged_discovery_says": Lagged,
}

ARTIFACTS = (
    "orientation_propagation.schema.json",
    "orientation_session.schema.json",
    "markov_blanket.schema.json",
    "lagged_discovery.schema.json",
    "notears_fit.schema.json",
)


# --------------------------------------------------------------------------
# the artifacts, run
# --------------------------------------------------------------------------


def _propagation() -> dict:
    """A→C←B from the data, and a constraint that contradicts it — the build
    that used to produce the half-and-half string above."""
    return orientation_to_dict(propagate_orientations(
        ("A", "B", "C"), directed=[("A", "C"), ("B", "C")],
        constraints=[("C", "A")]))


def _session() -> dict:
    return session_to_dict(start_orientation_session(
        ("a", "b", "c"), undirected=[("a", "b"), ("b", "c")]))


def _blanket() -> dict:
    rng = np.random.default_rng(0)
    n = 400
    t = rng.normal(size=n)
    frame = pd.DataFrame({
        "t": t,
        "parent": t * 0.0 + rng.normal(size=n),
        "child": t * 2.0 + rng.normal(size=n) * 0.4,
        "far": rng.normal(size=n),
    })
    frame["t"] = frame["parent"] * 1.5 + rng.normal(size=n) * 0.4
    frame["child"] = frame["t"] * 2.0 + rng.normal(size=n) * 0.4
    return markov_blanket_to_dict(markov_blanket(frame, target="t"))


def _lagged() -> dict:
    rng = np.random.default_rng(1)
    n = 300
    a = rng.normal(size=n)
    b = np.concatenate([[0.0], a[:-1] * 1.4]) + rng.normal(size=n) * 0.3
    frame = pd.DataFrame({"t": range(n), "a": a, "b": b})
    return lagged_discovery_to_dict(
        discover_lagged_graph(frame, time="t", columns=("a", "b"), max_lag=1))


BUILDS = {
    "orientation_propagation": _propagation,
    "orientation_session": _session,
    "markov_blanket": _blanket,
    "lagged_discovery": _lagged,
}


@pytest.mark.parametrize("kind", sorted(BUILDS))
def test_the_artifact_carries_no_language(kind):
    """The envelope is the same envelope whoever reads it.

    Both halves matter: the Chinese that was there, and the English that was
    beside it. A field holding one finished string had already picked a
    reader by the time it left, whichever language it picked.

    Checked by rendering rather than against a list of words, because a
    TOKEN is supposed to read like this — ``found_this_blanket`` is in no
    language and a rule that objected to the shape of it would be asking
    the envelope to hide the one thing it is for. What must not be here is
    the SENTENCE, so the sentence is what is looked for, in every language
    this build writes.
    """
    note = BUILDS[kind]()["note"]
    assert note, f"{kind} says nothing about itself"
    blob = json.dumps(note, ensure_ascii=False)
    for lang in sorted(language.written()):
        for one in note:
            assert language.spoke(one, lang) not in blob, (kind, lang)
    for one in note:
        assert set(one) <= {"vocabulary", "token", "said", "words"}


@pytest.mark.parametrize("kind", sorted(BUILDS))
def test_both_readers_get_the_whole_note(kind):
    note = BUILDS[kind]()["note"]
    for lang in sorted(language.written()):
        said = language.spoken(note, lang)
        assert said
        for one in note:
            assert one["token"] not in said, (kind, lang, one["token"])


def test_the_two_authors_of_one_string_are_two_statements_now():
    """The half-and-half note, by species rather than by wording.

    The counts and the refusal were computed in two places and joined by a
    mark belonging to one of the two languages. They are two members now,
    and the mark between them is the reader's.
    """
    note = _propagation()["note"]
    assert [one["token"] for one in note] == [
        "closed_the_graph", "constraints_clash_with_the_data"]
    assert note[1]["said"] == {"count": "1"}
    zh, en = (language.spoken(note, lang) for lang in ("zh", "en"))
    assert "；" not in zh and "；" not in en
    assert en.count(".") >= 2 and zh.count("。") >= 2


def test_a_closure_with_nothing_to_refuse_says_only_what_it_did():
    """One member per kind of input refused, and none where none was.

    The shape it replaces appended a clause per non-zero bucket to one
    string, so "no conflicts" was spelled by the absence of a suffix.
    """
    note = propagate_orientations(
        ("a", "b", "c"), directed=[], undirected=[("a", "b"), ("b", "c")]).note
    assert [one["token"] for one in note] == ["closed_the_graph"]


def test_the_session_says_what_its_status_MEANS():
    """``orientation_session_status`` is excused from a gloss on the grounds
    that the note says the status in a sentence. It used to say it by
    ending ``status=blocked`` with the token showing."""
    note = _session()["note"]
    assert [one["token"] for one in note] == [
        "ingested_the_answers", "still_worth_asking"]
    assert "status" not in json.dumps(note)
    assert set(SAYS_STATUS) == set(
        json.loads((SCHEMAS / "orientation_session.schema.json")
                   .read_text("utf-8"))["properties"]["status"]["enum"])


def test_the_blanket_says_it_is_not_an_adjustment_set():
    """The one sentence on this artifact that is not a field read back, and
    the one a reader can act wrongly on without it."""
    note = _blanket()["note"]
    assert [one["token"] for one in note] == [
        "found_this_blanket", "a_screen_and_not_an_adjustment_set"]
    for lang in ("zh", "en"):
        said = language.spoke(note[1], lang)
        assert ("调整集" in said) or ("adjustment set" in said)


def test_the_lagged_note_says_what_it_did_not_look_for():
    note = _lagged()["note"]
    assert [one["token"] for one in note][-1] == "only_lagged_links"
    assert note[0]["said"]["max_lag"] == "1"


# --------------------------------------------------------------------------
# the sets themselves
# --------------------------------------------------------------------------


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


def _unended(members) -> list[tuple[object, str]]:
    """(member, language) for every whole sentence that does not end itself.

    ``spoken`` supplies the GAP after a sentence and not the MARK, which is
    what ``FULL_STOP`` says about itself — so a member joined by it and
    carrying no mark runs into the next one.
    """
    return [(m, tag) for m in members for tag, text in m.words.items()
            if text and text[-1] not in "。！？.!?"]


ALL_MEMBERS = tuple(m for cls in THE_FOUR.values() for m in cls)


def test_every_species_is_written_in_every_language_this_build_writes():
    assert not _unwritten(ALL_MEMBERS)


def test_the_two_languages_of_a_species_have_the_same_holes():
    assert not _disagreeing_holes(ALL_MEMBERS)


def test_a_sentence_of_a_note_ends_itself():
    """The judgement this cut rests on, and the reason it is not the one
    ``discovery_note`` makes one file over."""
    assert not _unended(ALL_MEMBERS)


def _ended(table) -> list[str]:
    """The tokens of a WORDS TABLE whose texts end as sentences."""
    return sorted({token for token, words in table.items()
                   for text in words.values()
                   if text and text[-1] in "。."})


def test_an_item_of_a_list_does_not_end_itself():
    """The other side of the same judgement, on the set that has it.

    ``NOTES`` members go into a SLOT of a larger sentence — the gap report
    puts every measured violation into one — where they are joined by the
    ITEM separator. A full stop there lands inside a comma-separated list,
    which is why the two sets differ and why the difference is not a style.
    """
    assert not _ended(NOTES), (
        f"these are joined as items and end as sentences: {_ended(NOTES)}")


def test_the_item_gate_refuses_an_item_that_ends_itself():
    assert _ended({"t": {"zh": "像句子一样收尾。", "en": "ends like a sentence."}})
    assert not _ended({"t": {"zh": "不收尾", "en": "does not end"}})


class _Stub:
    """A member shape, not a member: enough for the three checks above to
    read, and registered with no vocabulary so nothing can reach it."""

    def __init__(self, words):
        self.words = words


def test_the_completeness_gate_refuses_a_one_language_member():
    assert _unwritten([_Stub({"zh": "只有中文的句子。"})])
    assert _unwritten([_Stub({"zh": "有中文。", "en": ""})])


def test_the_hole_gate_refuses_a_fact_only_one_reader_gets():
    assert _disagreeing_holes(
        [_Stub({"zh": "有 {a} 也有 {b}。", "en": "only {a}."})])


def test_the_ending_gate_refuses_a_sentence_that_runs_on():
    """The counterexample for the judgement above, through the same
    function — including the case that reads correctly in Chinese and
    wrongly in English, which is the direction this repository's gaps have
    always gone."""
    assert _unended([_Stub({"zh": "没有句号", "en": "no full stop"})])
    assert _unended([_Stub({"zh": "有句号。", "en": "none here"})])
    assert not _unended([_Stub({"zh": "问句吗？", "en": "a question?"})])


# --------------------------------------------------------------------------
# the channel
# --------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_every_standalone_artifact_reaches_the_shape_directly(artifact):
    """Not through ``query_result``.

    ``notears_fit`` had the right shape and the wrong route: it borrowed
    the envelope's ``statedSentence``, which made a standalone artifact
    depend on the document of a thing it is not part of. That coupling is
    the reason the shape was unreachable to the other four in the first
    place, so pointing at it would have been repeating it.
    """
    text = (SCHEMAS / artifact).read_text("utf-8")
    assert "statement.schema.json#/$defs/statement" in text
    assert "query_result.schema.json#/$defs/statedSentence" not in text


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_no_artifact_still_types_its_own_note_as_text(artifact):
    doc = json.loads((SCHEMAS / artifact).read_text("utf-8"))
    note = doc["properties"]["note"]
    assert note["type"] == "array", artifact
    assert note["items"]["$ref"].endswith("#/$defs/statement")


def test_an_answerers_own_note_stays_a_string():
    """The one field on these artifacts that must NOT move.

    A session answer carries whatever the person wrote beside it. That is a
    reader's sentence, not the kernel's, and its language is theirs — a
    vocabulary here would be this package choosing words for somebody
    else's note. The distinction is which side of the boundary wrote it,
    and it is the reason "make every string a statement" is the wrong rule.
    """
    doc = json.loads(
        (SCHEMAS / "orientation_session.schema.json").read_text("utf-8"))
    for where in (doc["$defs"]["answer"], doc["$defs"]["sourceTrailEntry"]):
        assert where["properties"]["note"]["type"] == "string"
        assert where["properties"]["note"]["description"]


def test_the_discovery_layer_still_says_what_it_found():
    """The neighbouring note this did not touch, so that the cut is visible
    as a cut: ``_format_note`` was already statements and stays as it is."""
    note = _format_note("pc", 2, 0, 1)
    assert [one["token"] for one in note][0] == "found_this_many_edges"
    assert all(one["vocabulary"] == "discovery_note" for one in note)
