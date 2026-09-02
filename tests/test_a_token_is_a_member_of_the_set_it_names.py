"""A statement's two halves, held to the contract that carries them.

A statement travels as ``{vocabulary, token}`` — which closed set, and
which member of it — and both halves were free strings. So a bounds row's
note could be edited to any word at all, and a reader's surface would look
up a set that never existed or a member that set never had. A hundred and
sixteen leaves across the bounds rows, the gap report and the IV block
survived exactly that.

The reason recorded twice for leaving them was that the verifier has no
authority for these words: they live in ``themis.output.reader_words`` and
no verifier module may import ``themis.output``. That reason was about the
wrong side of the boundary. ``verify`` validates against the contract
before any rule runs, so the contract is an authority available here — and
``reader_words._enum_at`` already reads several of its sets back OUT of
``query_result.schema.json``. What was missing was not a table in the
verifier. It was the enumeration living where the token is written.

The enumeration goes in the SHARED statement schema rather than the
envelope's, because six of the ten sets are written at nested sites —
inside ``words`` — and the envelope's alias for a statement does not reach
those. The shared carrier is where the recursion is.

The set constrains the token and never the reverse: four members of these
sets are spelled the same way in some other set, which is the collision
the ``vocabulary`` field exists to survive.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
import themis.output.reader_words as reader_words
from themis import language
from themis.input.syntactic_validator import SyntacticError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SCHEMAS = pathlib.Path(themis.__file__).parent / "schemas"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
STATEMENT = json.loads(
    (SCHEMAS / "statement.schema.json").read_text(encoding="utf-8"))["$defs"]

LISTED = {
    branch["if"]["properties"]["vocabulary"]["const"]:
        set(branch["then"]["properties"]["token"]["enum"])
    for branch in STATEMENT["closedSets"]["allOf"]
}


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _statements(node):
    if isinstance(node, dict):
        if isinstance(node.get("vocabulary"), str) \
                and isinstance(node.get("token"), str):
            yield node
        for value in node.values():
            yield from _statements(value)
    elif isinstance(node, list):
        for value in node:
            yield from _statements(value)


def _carrier(vocabulary):
    """A shape whose result carries a statement of this set, and it."""
    for name in sorted(SHAPES):
        program, result = _pair(name)
        for statement in _statements(result):
            if statement["vocabulary"] == vocabulary:
                return name, program, result, statement
    raise AssertionError(f"no answer shape carries a {vocabulary} statement")


# ------------------------------------------- the contract says what it says


def test_the_declared_sets_are_the_sets_this_build_declares():
    """The registry is filled when a vocabulary's class body runs, so which
    sets exist depended on which producers something had imported. This is
    the record of it a reader's surface can hold without running anything,
    and it has to be the same list."""
    reader_words.load()
    assert set(STATEMENT["declaredVocabulary"]["enum"]) \
        == set(language.VOCABULARIES)


@pytest.mark.parametrize("vocabulary", sorted(LISTED))
def test_a_listed_set_is_enumerated_as_the_kernel_has_it(vocabulary):
    assert LISTED[vocabulary] == set(
        reader_words.GLOSSED[vocabulary].members()), vocabulary


def test_the_listed_sets_are_the_ones_whose_members_the_kernel_owns():
    """Stated as the boundary rather than as a list, so that adding a set
    whose tokens another layer coins fails here."""
    import inspect

    for vocabulary in LISTED:
        source = inspect.getsource(reader_words.GLOSSED[vocabulary].members)
        assert "_stated(" in source, (vocabulary, source)


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        program, result = _pair(name)
        themis.verify(program, result)


# ------------------------------------------------------------- the gate


def _only_this_edit_refuses(vocabulary, field, value):
    """The envelope passes; the same envelope with one word changed does not.

    The message is not matched because these statements sit at two depths
    and the deeper ones surface through the ``oneOf`` that lets a slot hold
    a statement or a list of them. What the pairing establishes instead is
    sharper than any wording: nothing else about the answer moved.
    """
    _, program, result, statement = _carrier(vocabulary)
    themis.verify(program, result)
    statement[field] = value
    with pytest.raises(SyntacticError):
        themis.verify(program, result)


@pytest.mark.parametrize("vocabulary", sorted(LISTED))
def test_a_word_that_set_does_not_have(vocabulary):
    _only_this_edit_refuses(vocabulary, "token", "x")


@pytest.mark.parametrize("vocabulary", sorted(LISTED))
def test_a_word_borrowed_from_another_real_set(vocabulary):
    """The forgery a membership check has to catch and a spelling check
    cannot: every word is real, and it is not this set's."""
    other = next(t for v, ts in sorted(LISTED.items()) if v != vocabulary
                 for t in sorted(ts) if t not in LISTED[vocabulary])
    _only_this_edit_refuses(vocabulary, "token", other)


def test_a_set_this_build_does_not_declare():
    _only_this_edit_refuses("bounds_note", "vocabulary", "x")


def test_a_set_that_exists_but_is_not_the_one_this_word_is_from():
    """The vocabulary half's own borrowed-name forgery."""
    _only_this_edit_refuses("bounds_note", "vocabulary", "monotonicity")


# ------------------------------------------- what the contract leaves open


def test_a_member_may_be_spelled_the_way_another_set_spells_one():
    """Why the constraint runs one way only.

    ``binary`` is a measurement scale and a four-way mediator scale;
    ``outcome`` is a query role, a measurement-correction side, a proximal
    role and an unnamed thing. Inferring the set from the token would pick
    one of them, which is the mistake carrying the set exists to prevent.
    """
    reader_words.load()
    members = {}
    for name, row in reader_words.GLOSSED.items():
        try:
            members[name] = set(row.members())
        except Exception:                      # a set this build cannot read
            members[name] = set()
    shared = {
        token: sorted(v for v, ms in members.items() if token in ms)
        for vocabulary in LISTED
        for token in LISTED[vocabulary]
        if sum(token in ms for ms in members.values()) > 1
    }
    assert shared == {
        "binary": ["four_way_mediator_scale", "measurement_scale"],
        "continuous": ["four_way_mediator_scale", "measurement_scale"],
        "exposure": ["measurement_correction_side", "query_role"],
        "outcome": ["measurement_correction_side", "proximal_role",
                    "query_role", "unnamed_thing"],
    }, shared


def test_the_sets_left_open_are_open_for_a_reason():
    """Counted, so that "we closed the reader's words" cannot be said.

    ``assumption_claim`` is keyed on ids estimators declare and the schema
    types those as a free string on purpose — an estimator adding one is
    not a change to the envelope. ``gap_says`` is already enumerated, in
    ``query_result.schema.json``'s own ``$defs/need``, and the shared
    carrier must not reach back into one artifact's file to find it.
    """
    assert "assumption_claim" not in LISTED
    assert "gap_says" not in LISTED
    envelope = json.loads(
        (SCHEMAS / "query_result.schema.json").read_text(encoding="utf-8"))
    assert set(envelope["$defs"]["need"]["enum"]) \
        == set(reader_words.GLOSSED["gap_says"].members())
