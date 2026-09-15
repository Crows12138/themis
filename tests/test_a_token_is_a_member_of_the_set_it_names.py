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
from tests.answer_corpus import verify_honestly
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
    """A shape this gate can put a forgery through for this set, and it.

    Two conditions, not one. The row has to CARRY a statement of the set,
    and ``verify`` has to READ the row — most rows carrying a gap report
    have no derivation and ``verify`` raises on them rather than reading
    them, so a pairing built on one would show a refusal that was already
    there before the edit. Which rows qualify is a fact about the corpus,
    so it is measured and pinned rather than assumed.
    """
    for name in sorted(SHAPES):
        program, result = _pair(name)
        if not any(s["vocabulary"] == vocabulary for s in _statements(result)):
            continue
        try:
            themis.verify(program, result)
        except Exception:
            continue
        for statement in _statements(result):
            if statement["vocabulary"] == vocabulary:
                return name, program, result, statement
    return None


#: Sets the contract now enumerates that no answer in the corpus puts
#: through ``verify`` — either nothing carries one, or the rows that do are
#: gap diagnoses ``verify`` declines to read. The enumeration still holds
#: them: what is missing is a row to demonstrate it on, and that is a fact
#: about the corpus rather than about the contract. Written down because a
#: gate that quietly parametrizes over fewer sets each round is a gate that
#: stops measuring without failing.
NO_ROW_TO_FORGE_ON = frozenset({
    "bridge_side", "consistency_constraint", "data_contract_warning",
    "instrument_route_note", "malformed_program", "missing_data_shortfall",
    "monotonicity_refutation", "outcome_error_premise",
    "proximal_criterion_failure", "proximal_role", "query_part",
    "recovery_factor", "recovery_mechanism", "selection_recovery_shortfall",
    "unbiased_distribution",
})

FORGEABLE = sorted(set(LISTED) - NO_ROW_TO_FORGE_ON)


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


#: The sets whose members the kernel owns that are deliberately NOT listed,
#: each with the reason the ``closedSets`` description gives. A row here is
#: how a set stays out on purpose; without one, the gate below has nowhere
#: to put an exception and would be argued with by deleting it.
NOT_LISTED_ON_PURPOSE = {
    "proximal_data_condition":
        "the artifact's own schema already enumerates it, and the shared "
        "carrier must not reach back into that",
}

#: Sets this build declares that have no glossed row at all, so nothing here
#: can read their members. Pinned rather than skipped: a set that quietly
#: stops being readable is a set that quietly stops being asked.
NO_ROW_TO_READ = {"gap_routes"}


def _the_kernel_owns_the_members_of() -> set[str]:
    """Every declared set whose member list this build writes itself.

    The same question ``closedSets`` answers, asked of the kernel instead of
    the contract — which is what makes holding the two equal mean anything.
    """
    import inspect

    owns = set()
    for vocabulary in language.VOCABULARIES:
        row = reader_words.GLOSSED.get(vocabulary)
        if row is None:
            continue
        try:
            source = inspect.getsource(row.members)
            row.members()
        except Exception:
            continue
        if "_stated(" in source:
            owns.add(vocabulary)
    return owns


def test_the_listed_sets_are_the_ones_whose_members_the_kernel_owns():
    """The boundary, asked in BOTH directions.

    It was asked in one: every listed set had to be one the kernel owns, so
    listing somebody else's set failed here. Nothing asked the converse, and
    a list can only be wrong in the direction nobody checks — measured when
    that side was added, the kernel owned the members of 35 sets and 8 were
    listed. Of the 27 that were not, one has a reason and is written down
    below; the other 26 are not a decision anybody recorded. They are what a
    one-sided gate lets accumulate, and a reader's surface met every one of
    them as a token nothing could disagree with.

    So the omissions are enumerated now, with their reasons, and a set that
    joins the kernel's own without joining the contract fails here.
    """
    reader_words.load()
    owned = _the_kernel_owns_the_members_of()
    listed = set(LISTED)
    assert listed <= owned, (
        "listed as the kernel's own, and its members are coined elsewhere: "
        f"{sorted(listed - owned)}")
    assert owned - listed == set(NOT_LISTED_ON_PURPOSE), (
        "the kernel owns these sets' members and the contract does not say "
        f"which: {sorted(owned - listed - set(NOT_LISTED_ON_PURPOSE))}")


def test_every_declared_set_has_a_row_to_read_or_is_named_here():
    """The gate above skips a set it cannot read, which is how it would
    stop measuring without failing. What it skips is written down."""
    reader_words.load()
    unreadable = {name for name in language.VOCABULARIES
                  if reader_words.GLOSSED.get(name) is None}
    assert unreadable == NO_ROW_TO_READ, sorted(unreadable)


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        verify_honestly(*_pair(name))


# ------------------------------------------------------------- the gate


def _only_this_edit_refuses(vocabulary, field, value):
    """The envelope passes; the same envelope with one word changed does not.

    The message is not matched because these statements sit at two depths
    and the deeper ones surface through the ``oneOf`` that lets a slot hold
    a statement or a list of them. What the pairing establishes instead is
    sharper than any wording: nothing else about the answer moved.
    """
    found = _carrier(vocabulary)
    assert found is not None, (
        f"{vocabulary} has no row to forge on; if that is now true, it "
        f"belongs in NO_ROW_TO_FORGE_ON with the rest")
    _, program, result, statement = found
    themis.verify(program, result)
    statement[field] = value
    with pytest.raises(SyntacticError):
        themis.verify(program, result)


def test_the_sets_a_forgery_can_be_shown_on_are_the_ones_that_have_a_row():
    """The gate's own scope, asserted rather than left to the parametrize.

    A set moving into ``NO_ROW_TO_FORGE_ON`` is the corpus losing a witness
    and has to be a deliberate edit; a set moving out is a witness gained
    and has to be exercised. Either way it is visible in a diff, which a
    shrinking parametrize list is not.
    """
    without = {name for name in LISTED if _carrier(name) is None}
    assert without == NO_ROW_TO_FORGE_ON, {
        "no longer forgeable": sorted(without - NO_ROW_TO_FORGE_ON),
        "forgeable now": sorted(NO_ROW_TO_FORGE_ON - without),
    }


@pytest.mark.parametrize("vocabulary", FORGEABLE)
def test_a_word_that_set_does_not_have(vocabulary):
    _only_this_edit_refuses(vocabulary, "token", "x")


@pytest.mark.parametrize("vocabulary", FORGEABLE)
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

    Both reasons stand and the second was read as more than it says. An
    enumeration in an artifact's schema constrains the FIELD it is
    written at — ``missing_information[].need`` for this one — and a
    statement carries its set beside its token so that the same set can
    travel anywhere. ``gap_says`` reaches 49 word slots inside ``words``
    on this corpus and that enum follows it to none of them. What asks
    there is a verifier rule reading the set named beside the token; see
    ``test_a_word_slot_is_held_to_the_set_beside_it``.
    """
    assert "assumption_claim" not in LISTED
    assert "gap_says" not in LISTED
    envelope = json.loads(
        (SCHEMAS / "query_result.schema.json").read_text(encoding="utf-8"))
    assert set(envelope["$defs"]["need"]["enum"]) \
        == set(reader_words.GLOSSED["gap_says"].members())
