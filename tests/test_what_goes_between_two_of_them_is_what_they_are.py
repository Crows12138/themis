"""The mark between two members, and who gets to decide it.

``assemble`` put several statements in one hole by joining them with the
mark that goes between two NAMES, because the only thing it could see was
that it had been handed a list. What separates two things is decided by
what they ARE — ``、`` between names, ``；`` between clauses, the gap after
a full stop between sentences — and by the time anything renders a list it
holds several tokens off an envelope with nobody left to ask.

Measured with a hook on ``assemble`` over the whole suite before this
existed: five holes are ever filled with a list, and three of them hold
clauses. The sharpest of the three is the consistency constraint, whose
two sentences carry commas of their own — so the mark a list takes was not
merely the light one, it was indistinguishable from the punctuation inside
each of the things it was supposed to separate.

The fact is a property of the SET, and it is the only one of the three
seams a reader cannot work out for themselves, so every vocabulary
declares it where it is declared and both surfaces read it from there.

Declaring the mark between two members is declaring what a member IS, and
that half went unchecked while six sets held both kinds at once — 88 gap
descriptions of which 14 stopped nowhere, 137 refusal sentences of which 6
stopped, 37 shortfalls of which 16 did, and three smaller ones. Whichever
mark those declared was wrong for part of them, which is why the rule could
not be written down when the seam was: it would have failed on the sets it
was for. It is written down now, and it is refused at the door.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from themis import language
from themis.output import data_gap_report, reader_words
from themis.runtime import scheduler_words

from . import web_source

SEAM_NAMES = ("BETWEEN_ITEMS", "BETWEEN_STATEMENTS", "BETWEEN_SENTENCES")
PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "themis"


def _clauses():
    """The two the census caught, as their producer builds them."""
    return [
        language.state(scheduler_words.Feasibility.A_RISK_SITS_OUTSIDE_ITS_BOUND,
                       quantity="P(Y=1|do(X=1))", value=1,
                       expression="[P(X=1,Y=1), P(X=1,Y=1)+P(X=0)]",
                       lower=0.25, upper=0.75),
        language.state(scheduler_words.Feasibility.A_RISK_SITS_OUTSIDE_ITS_BOUND,
                       quantity="P(Y=1|do(X=0))", value=0,
                       expression="[P(X=0,Y=1), P(X=0,Y=1)+P(X=1)]",
                       lower=0.25, upper=0.75),
    ]


def _names():
    """And the two it caught in the other hole, which were right already."""
    cut = data_gap_report.Measurement.A_THRESHOLD_CUT_IT_IN_TWO
    return [language.state(cut, variable="x", cut=">=3cm"),
            language.state(cut, variable="z", cut=">=50")]


# --- the declaration ----------------------------------------------------------


def test_every_vocabulary_says_what_goes_between_two_of_its_members():
    """No default, because a default is the defect one level up: it would be
    right for the two holes that hold names and wrong for the three that do
    not, and silently."""
    assert set(language.SEAMS) == set(language.VOCABULARIES)
    for vocabulary, mark in language.SEAMS.items():
        assert any(mark is known for known in language.SEAM_ORDER), vocabulary


def test_a_vocabulary_that_does_not_say_is_refused():
    with pytest.raises(TypeError, match="does not say what goes between"):
        class Silent(language.Word, vocabulary="a_set_that_did_not_say"):
            A = ("a", {"zh": "甲", "en": "a"})


def test_a_seam_that_is_not_one_of_the_three_is_refused():
    """A mark rather than one of the language layer's own is a site writing
    punctuation again, which is what having a table for each of these was
    for."""
    with pytest.raises(TypeError, match="between two of its members"):
        class Invented(language.Word, vocabulary="a_set_with_its_own_mark",
                       between={"zh": " · ", "en": " · "}):
            A = ("a", {"zh": "甲", "en": "a"})


# --- and the half of the declaration a set can be WRONG about -----------------


@pytest.mark.parametrize("vocabulary", sorted(language.VOCABULARIES))
def test_every_member_is_what_its_own_seam_says_it_is(vocabulary):
    """Declaring the mark between two members is declaring what a member IS,
    and only one of the two was ever checked.

    Measured when this rule was written: six sets held both kinds at once —
    88 gap descriptions of which 14 stopped nowhere, 137 refusal sentences of
    which 6 stopped, and four more — so whichever mark each declared was
    wrong for part of it. The declaration is now refused at the door, and
    this states it per set so a failure names which one.
    """
    owner = language.VOCABULARIES[vocabulary]
    whole = language.SEAMS[vocabulary] is language.BETWEEN_SENTENCES
    rows = (owner.items() if not isinstance(owner, type)
            else ((member.value, member.words) for member in owner))
    for token, words in rows:
        for lang, text in words.items():
            assert language.ends_a_sentence(text) is whole, (
                f"{vocabulary}.{token} in {lang}: {text!r}"
            )


def test_a_set_of_sentences_whose_member_stops_nowhere_is_refused():
    with pytest.raises(TypeError, match="does not end a sentence"):
        class Unfinished(language.Word, vocabulary="a_set_that_stops_nowhere",
                         between=language.BETWEEN_SENTENCES):
            A = ("a", {"zh": "这是一句话。", "en": "this is a sentence."})
            B = ("b", {"zh": "这一句没有收尾", "en": "this one just stops"})
    assert "a_set_that_stops_nowhere" not in language.VOCABULARIES


def test_a_set_of_clauses_whose_member_ends_is_refused():
    """The other direction, and the one that reads as harmless: a clause
    carrying its own mark lands a full stop in the middle of the sentence
    the slot belongs to."""
    with pytest.raises(TypeError, match="ends a sentence"):
        language.declare(
            "a_set_of_clauses_that_ended",
            {"a": {"zh": "少了一列", "en": "a column is missing"},
             "b": {"zh": "少了一行。", "en": "a row is missing."}},
            language.BETWEEN_STATEMENTS)
    assert "a_set_of_clauses_that_ended" not in language.VOCABULARIES


def test_a_template_that_ends_in_a_hole_is_not_a_whole_sentence():
    """Where the mark goes when the sentence ends with somebody else's words.

    Eight of the fourteen unfinished descriptions ended in a hole, and the
    hole is filled from a set with a seam of its own that owes this sentence
    nothing. So the mark belongs to the template, after the hole.
    """
    with pytest.raises(TypeError, match="does not end a sentence"):
        language.declare(
            "a_set_that_left_it_to_the_hole",
            {"a": {"zh": "识别路径失败：{why}", "en": "the route failed: {why}"}},
            language.BETWEEN_SENTENCES)
    assert language.ends_a_sentence("识别路径失败：{why}。")
    assert language.ends_a_sentence("the route failed: {why}.")


def test_what_closes_after_the_mark_does_not_unfinish_the_sentence():
    """Emphasis and brackets close after the mark, and a rule that cannot
    see past them measures the markup instead of the punctuation — which is
    what the first scan for this did, on the four members that end in one."""
    assert language.ends_a_sentence("这一句是完整的。**")
    assert language.ends_a_sentence('he said "so it is."')
    assert not language.ends_a_sentence("最多能定下 3 条边）")


def test_the_declaration_reaches_the_registry_from_either_door():
    """A table-backed set and a member-backed one answer the same way. Both
    go through ``_answers_to``, which is where this is written, so neither
    door can be given the fact and the other left without it."""
    tables = {name for name, owner in language.VOCABULARIES.items()
              if not isinstance(owner, type)}
    assert tables, "no table-backed vocabulary to check the other door with"
    assert tables <= set(language.SEAMS)


# --- what a hole does with it -------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_two_clauses_in_one_hole_are_separated_as_clauses(lang):
    said = language.joined(_clauses(), lang)
    assert language.fill(language.BETWEEN_STATEMENTS, lang) in said
    # In English the list mark is a comma and each clause contains commas,
    # so this is not "a slightly light seam": it is one the reader cannot
    # find. The assertion is that the two clauses are not run together on
    # the mark their own contents already use.
    assert not re.search(r"\]\s*,\s*P\(", said)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_two_names_in_one_hole_are_still_a_list(lang):
    said = language.joined(_names(), lang)
    assert language.fill(language.BETWEEN_ITEMS, lang) in said
    assert language.fill(language.BETWEEN_STATEMENTS, lang) not in said


def test_a_list_drawn_from_two_sets_takes_the_coarser_seam():
    """A mark too heavy for one of a pair still separates it from the next;
    one too light leaves the reader looking for a boundary nobody wrote."""
    mixed = [_names()[0], _clauses()[0]]
    assert language.seam(mixed) is language.BETWEEN_STATEMENTS
    assert language.seam(list(reversed(mixed))) is language.BETWEEN_STATEMENTS


def test_a_set_this_build_does_not_carry_falls_back_to_the_list_mark():
    """The one guess, and it is the guess ``gloss`` already makes one level
    down: a set nothing here knows leaves the reader a token to look up,
    and a token is a name."""
    stranger = [{"vocabulary": "nothing_declares_this", "token": "a"},
                {"vocabulary": "nothing_declares_this", "token": "b"}]
    assert language.seam(stranger) is language.BETWEEN_ITEMS


def test_the_hole_goes_through_the_door():
    """``assemble`` is what this was found in, so it is named rather than
    left to the two above: the sentence a reader actually gets has to carry
    the seam, not just the joining function nobody would have called."""
    template = {"zh": "因为 {detail}。", "en": "because {detail}."}
    said = language.assemble(template, None, {"detail": _clauses()}, "en")
    assert language.fill(language.BETWEEN_STATEMENTS, "en") in said


# --- the mark had no door, and eight sites were spelling it out ---------------


def test_each_of_the_four_marks_has_a_door():
    for door, mark in ((language.listing, language.BETWEEN_ITEMS),
                       (language.clauses, language.BETWEEN_CLAUSES),
                       (language.statements, language.BETWEEN_STATEMENTS),
                       (language.sentences, language.BETWEEN_SENTENCES)):
        joined = (door(["a", "b"], "zh") if door is language.listing
                  else door("a", "b", lang="zh"))
        assert joined == "a" + language.fill(mark, "zh") + "b"


def test_no_site_outside_the_language_layer_joins_on_a_mark_itself():
    """The rule the doors exist for. ``BETWEEN_STATEMENTS`` had a table and
    eight hand-written consumers and no function, so every site that wanted
    it reached past the layer — and a site that reaches past the layer is a
    site free to reach for the wrong one, which is how a list mark ended up
    between two clauses.
    """
    reaching = re.compile(r"fill\(\s*(?:language\.)?BETWEEN_\w+")
    stray, read = [], 0
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "language.py":
            continue
        read += 1
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if reaching.search(line):
                stray.append(f"{path.name}:{i}")
    # The reach is pinned rather than trusted, for the reason the vocabulary
    # scans pin theirs: a rule that reads nothing passes.
    assert read > 100, f"this scanned {read} modules and the package is larger"
    assert not stray, (
        f"{stray} join on a seam table directly; the four doors are "
        f"listing / clauses / statements / sentences, and a hole full of "
        f"statements goes through `joined`"
    )


# --- and the browser reads the same answer ------------------------------------


def test_the_browser_is_told_which_mark_each_set_takes():
    """It cannot be worked out there either, and the browser has the same
    hole to fill. The generated table is pinned byte-for-byte elsewhere;
    what this states is that it names every set and names one of the three.
    """
    generated = web_source.read(web_source.GENERATED)
    body = web_source.literal("SEAMS", generated)
    written = dict(re.findall(r"^\s*([\w_]+): (BETWEEN_\w+),", body, re.M))
    assert written == reader_words.seams()
    assert set(written.values()) <= set(SEAM_NAMES)


def test_the_browser_fills_a_hole_through_the_same_door():
    """It had this defect too, in its own copy of ``assemble``: a list in a
    hole went through ``listing``, which is the browser's list mark for
    every reader and every kind of thing."""
    verdict = web_source.read(web_source.VERDICT)
    assembled = web_source.chunks(verdict)["assembled"]
    assert "joined(word, lang)" in assembled, (
        "verdict.ts fills a hole holding several statements without asking "
        "what they are"
    )
    assert "listing(" not in assembled
