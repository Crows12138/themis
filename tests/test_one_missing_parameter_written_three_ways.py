"""A row that names a missing parameter says the same thing three times.

A ``missing_information`` row that is short of a parameter carries one
fact in three places::

    name                 "parameter:P(survival=False|treatment=False)"
    said.key             "P(survival=False|treatment=False)"
    observable.variables ["survival", "treatment"]

They are one fact, so they agree or one of them is wrong, and a reader
who acts on the wrong one goes and collects the wrong table. This is the
list an analyst works from: it is the whole point of the block.

``name`` is more than a label. :func:`verify_investigation_items` indexes
this block BY it and resolves each ask's ``target`` against the index with
``.get`` — silent when it misses. So a moved name was not merely
unnoticed on its own account; it quietly switched off
``_check_the_two_renderings_agree`` for the ask pointing at it. One edit
disabled another rule, which is why holding the name matters more than
the copy it is.

Measured before this existed: every one of the 123 rows had its ``name``
replaced with a string nobody declared, and all 123 passed both public
doors.

What is asserted here:

- no honest row is refused, on any of the corpus's 54 carrying answers
- every single-field edit of the three is refused, counted not sampled
- the reading of a key is stated and reproduced from the corpus, so a key
  whose grammar moved fails loudly rather than being under-read into
  silence
- the rows this CANNOT speak for are named and counted, because a rule
  that is silent on a third of the block should say so out loud — and the
  five of those it reads anyway, by the name where no key is written, are
  counted with them.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import _NAMES_IN_A_KEY

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Answers carrying the block at all.
CARRIERS = sorted(
    name for name, pair in SHAPES.items()
    if (pair["result"] or {}).get("missing_information"))

#: (answer, row index) for the rows this rule can speak for: the ones
#: whose ``said.key`` gives it something to hold the other two against.
WITH_KEY = sorted(
    (name, i)
    for name in CARRIERS
    for i, row in enumerate(SHAPES[name]["result"]["missing_information"])
    if isinstance((row.get("said") or {}).get("key"), str)
    and (row.get("said") or {}).get("key")
)


def test_the_block_and_the_part_of_it_this_rule_reaches():
    """The denominator and the honest limit, both as numbers.

    A rule silent on a third of the rows is not a rule that holds the
    block, and the difference between the two counts is the only place
    that is visible.
    """
    assert len(CARRIERS) == 53, len(CARRIERS)
    rows = sum(len(SHAPES[n]["result"]["missing_information"]) for n in CARRIERS)
    assert rows == 121, rows
    assert len(WITH_KEY) == 80, len(WITH_KEY)


@pytest.mark.parametrize("name", CARRIERS)
def test_an_honest_row_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_the_reading_of_a_key_is_the_one_the_corpus_shows():
    """What "the variables a parameter is over" means, stated.

    The rule reads a key by taking whatever stands immediately before an
    ``=``. That is a narrow reading of one grammar, so it is reproduced
    against the corpus's own answer to the same question rather than
    asserted: on every row carrying both, the reading and the recorded
    ``observable.variables`` are the same set. A key whose grammar moves
    breaks this test instead of quietly making the rule read nothing.
    """
    checked = 0
    for name, i in WITH_KEY:
        row = SHAPES[name]["result"]["missing_information"][i]
        shown = (row.get("observable") or {}).get("variables")
        if not isinstance(shown, list):
            continue
        assert set(shown) == set(_NAMES_IN_A_KEY.findall(row["said"]["key"])), (
            name, row["said"]["key"], shown)
        checked += 1
    assert checked == 80, checked


def test_every_single_field_edit_of_the_three_is_refused():
    """One edit at a time, counted.

    Three separate lies: the row filed under another parameter's name, a
    reader sent to measure a variable the parameter is not over, and a
    variable it IS over dropped from that list. The third is the one a
    "compare the keys both sides have" rule would miss, and it is the
    edit that quietly shortens an analyst's shopping list.
    """
    refused = 0
    for name, i in WITH_KEY:
        row = SHAPES[name]
        original = row["result"]["missing_information"][i]
        shown = (original.get("observable") or {}).get("variables")

        edits = [lambda r: r.update({"name": "parameter:P(nobody=True)"})]
        if isinstance(shown, list) and shown:
            edits += [
                lambda r: r["observable"]["variables"].append("nobody"),
                lambda r: r["observable"]["variables"].pop(),
            ]

        for edit in edits:
            forged = copy.deepcopy(row["result"])
            edit(forged["missing_information"][i])
            with pytest.raises(VerificationError):
                the_door_for(row["result"])(row["program"], forged)
            refused += 1
    assert refused == 240, refused


def test_the_three_lies_are_told_apart_in_the_message():
    """Not a count: the sentence a reader gets has to say which.

    A misfiled name and a wrong shopping list are different problems with
    different fixes, and one message covering both would leave whoever
    reads the refusal to go and diff the row themselves.
    """
    name, i = WITH_KEY[0]
    row = SHAPES[name]

    forged = copy.deepcopy(row["result"])
    forged["missing_information"][i]["name"] = "parameter:P(nobody=True)"
    with pytest.raises(VerificationError, match="is filed under the name"):
        the_door_for(row["result"])(row["program"], forged)

    forged = copy.deepcopy(row["result"])
    forged["missing_information"][i]["observable"]["variables"].append("nobody")
    with pytest.raises(VerificationError, match="must observe"):
        the_door_for(row["result"])(row["program"], forged)


def test_a_row_with_no_key_is_not_asked_to_agree_with_one():
    """The limit, exercised rather than described.

    41 of the 121 rows name something that is not a parameter — a query
    that cannot be identified, an assumption nobody declared — and carry
    no key. They are not rows that disagree with themselves, and a rule
    demanding a key would refuse them for what they honestly are.

    Five of those 41 are read all the same, and by the name rather than
    by a key. What a row is short of is written after the colon whether
    or not the sentence repeats it, so where that half names variables it
    is what the shopping list is held against — measured here too, since
    a rule that reaches five more rows than its own account says is as
    wrong about itself as one that reaches five fewer.
    """
    keyless = [
        (n, i)
        for n in CARRIERS
        for i, r in enumerate(SHAPES[n]["result"]["missing_information"])
        if not isinstance((r.get("said") or {}).get("key"), str)
    ]
    assert len(keyless) == 41, len(keyless)

    read_by_name = [
        (n, i) for n, i in keyless
        if _NAMES_IN_A_KEY.findall(
            str(SHAPES[n]["result"]["missing_information"][i].get("name") or ""
                ).partition(":")[2])
        and isinstance((SHAPES[n]["result"]["missing_information"][i]
                        .get("observable") or {}).get("variables"), list)
    ]
    assert len(read_by_name) == 5, len(read_by_name)
    for n, i in read_by_name:
        forged = copy.deepcopy(SHAPES[n]["result"])
        forged["missing_information"][i]["observable"]["variables"].append(
            "nobody")
        with pytest.raises(VerificationError, match="must observe"):
            the_door_for(SHAPES[n]["result"])(SHAPES[n]["program"], forged)

    # Nothing on such a row settles a name, so this rule stays silent
    # there rather than inventing an anchor. It used to be the only rule
    # that could have, and the line below accepted a moved name to say so.
    # What speaks instead is the row's species, which declares the channel
    # it is filed under, and the ask the row was pushed into, which
    # carries the whole name back as its target — neither of them a key,
    # which is why this rule is still the wrong one to ask.
    n, i = keyless[0]
    forged = copy.deepcopy(SHAPES[n]["result"])
    forged["missing_information"][i]["name"] = "query:something_else_entirely"
    with pytest.raises(VerificationError) as refusal:
        the_door_for(SHAPES[n]["result"])(SHAPES[n]["program"], forged)
    assert "is filed under the name" not in str(refusal.value), refusal.value
