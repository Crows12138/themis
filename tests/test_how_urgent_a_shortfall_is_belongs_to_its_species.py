"""How urgent a shortfall is belongs to its species.

A ``missing_information`` row's ``priority`` is the word a reader sorts
their list by, so it decides what they do next, and the ask built over a
group of rows carries the strongest word among them. Both were typed at
every one of the thirty-seven sites that raise a shortfall -- always
``HIGH`` -- and declared nowhere. A value every site writes is a value no
rule can hold: there is nothing to hold it against but the producer's own
layout, and a verifier restating a layout agrees with it by construction.

The blanket was not a judgement. It was the default nobody chose, and it
already contradicted the one place where somebody did: the framing channel
built its ask at ``MEDIUM``, with the reason written beside it -- a reader
working down by priority meets a request to finish DEFINING a variable out
of turn, because it is something they do while reading rather than instead
of reading. The same species reached the envelope as a ROW at ``high`` and
as an ASK at ``medium``: one fact written twice with two different values
and no declaration between them to say which was meant.

So the word is the species', stated once in :data:`themis.gaps.WORTH` and
read by all three of the places that had been writing it -- the producer
that builds the row, the pass that groups rows into an ask, and the door
that recomputes both. Thirty-seven of the thirty-eight are ``HIGH``, which
is one sentence rather than thirty-seven judgements: a shortfall this
system reports is something the reader has to settle before the answer is
usable. :func:`themis.gaps._bind_worth` is what makes the thirty-ninth
species say something rather than inherit the sentence.

WHAT THE LIES LOOK LIKE HERE. This leaf has a declared vocabulary beside
it, so the interesting lie is one from INSIDE the vocabulary: a row filed
at ``low`` is a row the schema is happy with and a reader meets last. The
words outside it -- an empty string, a suffix, ``critical`` -- never reach
a rule at all, because the door validates before it reads, and a file that
counted those as held would be reporting the contract's work as its own.
Both are written down below, one as the rule's and one as the contract's.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis import gaps
from themis.input.syntactic_validator import SyntacticError
from themis.types import Priority
from themis.verifier import investigation_rules
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import verify_investigation_items

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))
UNWITNESSED = json.loads(
    (ROOT / "tests" / "fixtures" / "unwitnessed_leaves.json").read_text("utf-8"))

#: The words a priority can be, read off the contract's own enum rather
#: than spelled here. A lie about this leaf is one of the others.
VOCABULARY = tuple(str(word) for word in Priority)

#: Every stored shortfall row, as ``(answer, index, need, priority)``. The
#: roster is read off the corpus rather than off the declaration this
#: frontier empties: keyed on the file it empties, it would parametrize
#: nothing and a suite reporting no tests reports green.
CARRYING = [
    (name, i, str(row.get("need")), str(row.get("priority")))
    for name, pair in sorted(SHAPES.items())
    for i, row in enumerate(pair["result"].get("missing_information") or ())
    if isinstance(row, dict)
]

#: Every stored ask, as ``(answer, index, priority)``. A second roster
#: rather than a second reading of the first: an ask can hold an item
#: whose row is not on this envelope at all.
ASKING = [
    (name, i, str(ask.get("priority")))
    for name, pair in sorted(SHAPES.items())
    for i, ask in enumerate(pair["result"].get("investigation_requests") or ())
    if isinstance(ask, dict)
]

#: The answers this file bends. Either list is enough to put one here.
BENDING = sorted({name for name, _, _, _ in CARRYING}
                 | {name for name, _, _ in ASKING})


def _lies_about(block):
    """Every ``(answer, word)`` that is a lie about that block's first row.

    A roster rather than a skip inside the test. Parametrizing over the
    whole vocabulary and stepping past the word a row already says reports
    a third of this file's work as neither done nor undone, and the rows
    carrying no such block at all would be reported the same way.
    """
    return [
        (name, word)
        for name in BENDING
        for word in VOCABULARY
        if (rows := SHAPES[name]["result"].get(block))
        and rows[0].get("priority") != word
    ]


ROW_LIES = _lies_about("missing_information")
ASK_LIES = _lies_about("investigation_requests")


# --------------------------------------------------------- the declaration

def test_every_species_that_files_a_row_says_what_that_row_is_worth():
    """Total over the roster, and the two tables do not overlap.

    The binder runs at import, so this is what it already proved; it is
    restated here because a binder that stopped being called would leave
    nothing behind that said so.
    """
    priced = {need for need in gaps.Need if need in gaps.WORTH}
    rowless = {need for need in gaps.Need if need in gaps.FILES_NO_ROW}
    assert priced | rowless == set(gaps.Need)
    assert priced & rowless == set()


def test_a_species_that_files_a_row_and_prices_none_is_refused():
    victim = next(iter(gaps.WORTH))
    kept = gaps.WORTH.pop(victim)
    try:
        with pytest.raises(ValueError, match="no urgency declared"):
            gaps._bind_worth()
    finally:
        gaps.WORTH[victim] = kept
    gaps._bind_worth()


def test_a_species_that_files_no_row_and_prices_one_is_refused():
    """The other direction, and it is not symmetry for its own sake: a
    word about how urgently to act on a row that does not exist is a word
    about nothing, and an absence would otherwise stand for either."""
    victim = next(iter(gaps.FILES_NO_ROW))
    gaps.WORTH[victim] = Priority.HIGH
    try:
        with pytest.raises(ValueError, match="file no row"):
            gaps._bind_worth()
    finally:
        del gaps.WORTH[victim]
    gaps._bind_worth()


def test_what_a_species_is_worth_is_a_word_the_contract_allows():
    assert all(isinstance(word, Priority) for word in gaps.WORTH.values())


def test_the_table_is_not_the_blanket_it_replaced():
    """What makes it a declaration rather than a default written down.

    Thirty-seven sites agreeing on ``HIGH`` said nothing, because nothing
    else was available to them. A table where every entry is still the
    same word would be that blanket with a new address; this one holds the
    distinction the old sites could not express, which is the distinction
    the framing channel had already made by hand.
    """
    assert len(set(gaps.WORTH.values())) > 1


def test_the_verifier_ranks_every_word_the_vocabulary_has():
    """Which words exist is the contract's; which is louder is this
    module's own statement, and it has to cover all of them."""
    assert set(investigation_rules._PRIORITY_ORDER) == set(VOCABULARY)


def test_a_word_the_ranking_has_never_heard_of_is_refused():
    kept = investigation_rules._PRIORITY_ORDER
    investigation_rules._PRIORITY_ORDER = kept[1:]
    try:
        with pytest.raises(ValueError, match="nowhere in _PRIORITY_ORDER"):
            investigation_rules._bind_the_ranking()
    finally:
        investigation_rules._PRIORITY_ORDER = kept
    investigation_rules._bind_the_ranking()


# -------------------------------------------------------------- the door

@pytest.mark.parametrize("need", sorted(gaps.WORTH, key=str), ids=str)
def test_the_door_hands_back_what_the_species_is_worth(need):
    assert gaps.worth(need) is gaps.WORTH[need]
    assert gaps.worth(str(need)) is gaps.WORTH[need]


def test_a_species_that_files_no_row_has_no_urgency_to_hand_out():
    need = next(iter(gaps.FILES_NO_ROW))
    with pytest.raises(ValueError, match="files no missing_information row"):
        gaps.worth(need)


def test_a_site_that_types_the_word_is_refused_rather_than_obeyed():
    """Two authors for one field is the state this declaration replaces,
    so a site that keeps writing one is stopped at the door instead of
    having its word flattened onto the envelope beside the species'."""
    with pytest.raises(ValueError, match="was passed priority="):
        gaps.missing(
            kind=gaps.MissingKind.STRUCTURE,
            need=gaps.Need.NO_BACKDOOR_OR_FRONTDOOR,
            priority=Priority.LOW,
        )


# ------------------------------------------------------------- the sites

def test_no_site_types_the_word_the_reader_sorts_by():
    """The measurement that made this frontier, kept as the rule.

    Read off the product tree rather than the corpus, and stated about the
    keyword rather than about one function: a literal written into any
    ``priority=`` is a second author whichever record it is building.
    """
    typed = [
        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
        for path in sorted((ROOT / "themis").rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text("utf-8")))
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "priority" and isinstance(kw.value, ast.Attribute)
        and isinstance(kw.value.value, ast.Name)
        and kw.value.value.id == "Priority"
    ]
    assert typed == [], typed


# ------------------------------------------------------------- the corpus

@pytest.mark.parametrize("answer,index,need,priority", CARRYING,
                         ids=[f"{a}[{i}]" for a, i, _, _ in CARRYING])
def test_a_stored_row_is_worth_what_its_species_says(
    answer, index, need, priority,
):
    assert priority == str(gaps.WORTH[gaps.BY_NAME[need]])


@pytest.mark.parametrize("answer,index,priority", ASKING,
                         ids=[f"{a}[{i}]" for a, i, _ in ASKING])
def test_a_stored_ask_is_as_urgent_as_the_worst_thing_under_it(
    answer, index, priority,
):
    ask = SHAPES[answer]["result"]["investigation_requests"][index]
    worth = [gaps.WORTH[gaps.BY_NAME[item["need"]]]
             for item in ask.get("items") or ()]
    assert priority == str(max(worth, key=VOCABULARY.index))


@pytest.mark.parametrize("answer", sorted({n for n, _, _ in ASKING}))
def test_every_stored_ask_names_only_species_this_build_raises(answer):
    """The invariant the ask rule leans on, which is why it is written
    down rather than trusted: the rule goes SILENT on an ask holding an
    item whose species this build does not price, and a silent rule holds
    nothing. Measured on the corpus, 475 of 475 items name one."""
    for ask in SHAPES[answer]["result"].get("investigation_requests") or ():
        for item in ask.get("items") or ():
            assert gaps.BY_NAME.get(item.get("need")) in gaps.WORTH, item


# -------------------------------------------------------------- the bends

def _bent(answer, block, index, word):
    bad = copy.deepcopy(SHAPES[answer]["result"])
    bad[block][index]["priority"] = word
    return bad


@pytest.mark.parametrize("answer,word", ROW_LIES,
                         ids=[f"{a}:{w}" for a, w in ROW_LIES])
def test_a_row_filed_at_another_word_of_the_vocabulary_is_refused(
    answer, word,
):
    with pytest.raises(VerificationError, match="wrong order"):
        themis.verify_answer_claims(
            copy.deepcopy(SHAPES[answer]["program"]),
            _bent(answer, "missing_information", 0, word))


@pytest.mark.parametrize("answer,word", ASK_LIES,
                         ids=[f"{a}:{w}" for a, w in ASK_LIES])
def test_an_ask_filed_at_another_word_of_the_vocabulary_is_refused(
    answer, word,
):
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(
            copy.deepcopy(SHAPES[answer]["program"]),
            _bent(answer, "investigation_requests", 0, word))


@pytest.mark.parametrize("answer", BENDING)
def test_a_word_outside_the_vocabulary_is_the_contracts_refusal(answer):
    """The division of labour, stated where it can be read.

    The contract enumerates the words, so one from outside never reaches a
    rule: the door validates before it reads. Both refuse it and only one
    of them gets to, and writing that down is what stops this file from
    reporting the schema's work as its own.
    """
    block = ("missing_information"
             if SHAPES[answer]["result"].get("missing_information")
             else "investigation_requests")
    with pytest.raises(SyntacticError):
        themis.verify_answer_claims(
            copy.deepcopy(SHAPES[answer]["program"]),
            _bent(answer, block, 0, "critical"))


# ------------------------------------------- the two rules, one at a time

def _name_for(species) -> str:
    """A name this species would really be filed under."""
    if species in gaps.FILED_WHOLE:
        return gaps.filed(species)
    if species in gaps.FILED_UNDER:
        return gaps.filed(species, subject="thing")
    return gaps.filed(species, channel="mediation")


def _one_row(need, *, row_worth=None, ask_worth=None) -> dict:
    """The smallest envelope these rules read: one row, one ask naming it.

    Built rather than borrowed, because a corpus row carries the facts its
    own sentence needs and several rules read those first -- a bend made
    on one is refused, but not always here, and a test that cannot say
    which rule refused is not a test of this one.
    """
    species = gaps.registered(need)
    name = _name_for(species)
    owed = str(gaps.WORTH[species])
    return {
        "missing_information": [
            {"kind": "structure", "name": name,
             "priority": row_worth or owed,
             "gap": "unidentifiable_no_admissible_set", "need": str(need)},
        ],
        "investigation_requests": [
            # The heading carries what its one ask says, because a
            # neighbouring rule reads that and a test whose envelope two
            # rules refuse cannot say which of them it is about.
            {"action": "run_experiment", "target": name,
             "priority": ask_worth or owed, "group": "structure",
             "note": {"need": str(need)},
             "items": [{"target": name, "need": str(need)}]},
        ],
    }


def test_a_row_filed_at_anything_but_its_species_worth_is_refused():
    need = gaps.Need.NO_BACKDOOR_OR_FRONTDOOR
    verify_investigation_items(_one_row(need), {})
    for word in VOCABULARY:
        if word == str(gaps.WORTH[need]):
            continue
        with pytest.raises(VerificationError, match="wrong order"):
            verify_investigation_items(_one_row(need, row_worth=word), {})


def test_a_group_is_as_urgent_as_the_most_urgent_thing_in_it():
    need = gaps.Need.NO_BACKDOOR_OR_FRONTDOOR
    for word in VOCABULARY:
        if word == str(gaps.WORTH[need]):
            continue
        with pytest.raises(VerificationError, match="most urgent thing"):
            verify_investigation_items(_one_row(need, ask_worth=word), {})


def test_the_ask_reads_the_species_its_items_name_and_not_the_rows():
    """Which is the whole reason the rule can speak at all here.

    An ask can hold an item whose row is not on this envelope: the framing
    channel's items are predicates rather than shortfalls, and elsewhere
    the estimate settled a row and pruned it. A rule reading the rows
    would go silent on every one of those -- 145 framing asks and thirteen
    others -- so it reads the species each item names.
    """
    need = gaps.Need.NO_BACKDOOR_OR_FRONTDOOR
    envelope = _one_row(need)
    envelope["missing_information"] = []
    envelope["investigation_requests"][0]["priority"] = next(
        word for word in VOCABULARY if word != str(gaps.WORTH[need]))
    with pytest.raises(VerificationError, match="most urgent thing"):
        verify_investigation_items(envelope, {})


def test_an_ask_naming_a_species_this_build_does_not_raise_is_left_alone():
    """The silent branch, shown to be the branch it claims to be.

    A word outside the species roster is refused by the contract, so what
    reaches here is an item carrying no species at all -- and what such an
    ask is worth is not a question this declaration answers.
    """
    need = gaps.Need.NO_BACKDOOR_OR_FRONTDOOR
    envelope = _one_row(need)
    ask = envelope["investigation_requests"][0]
    del ask["items"][0]["need"]
    del ask["note"]
    ask["priority"] = next(
        word for word in VOCABULARY if word != str(gaps.WORTH[need]))
    verify_investigation_items(envelope, {})


@pytest.mark.parametrize("answer", BENDING)
def test_an_honest_answer_is_still_accepted(answer):
    """Both directions, because a rule that refuses everything refuses
    nothing in particular."""
    pair = SHAPES[answer]
    themis.verify_answer_claims(
        copy.deepcopy(pair["program"]), copy.deepcopy(pair["result"]))


# ------------------------------------------------------------ the census

def test_the_census_no_longer_names_either_leaf_anywhere():
    """What the frontier is FOR, stated where a reader of this file is."""
    still = sorted(
        (answer, leaf)
        for answer, paths in UNWITNESSED.items()
        for leaf in paths
        if leaf in ("missing_information.[].priority",
                    "investigation_requests.[].priority"))
    assert still == [], still
