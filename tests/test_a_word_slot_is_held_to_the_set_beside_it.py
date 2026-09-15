"""The set a word slot names, asked whether it has the word.

A statement carries its set BESIDE its token, and that is the carrier's
whole design: a token alone does not say which set it came from, and two
sets are free to spell a member the same way. Which means the set a token
must be a member of is not a fact about the token's POSITION — and both
authorities that asked about membership asked by position.

The contract asks per field: ``statement.schema.json`` enumerates 34 sets
conditioned on the ``vocabulary`` beside the token, and the sets it leaves
out include seven whose member list lives in ``query_result.schema.json``
instead, on the field each was first written at. ``gap_says`` is one of
them, enumerated at ``missing_information[].need``. The same set reaches an
envelope again inside ``words``, four levels deep on the corpus, and no
enumeration follows it there. The verifier asked nothing at all: the one
rule that reads a word slot looked the token's sentence up and, finding
none, returned — because :data:`themis.language.VOCABULARIES` said a
table's tokens are somebody else's, which is true of one table in seven.

So a gap's own reason for itself could be rewritten to any word at all, on
42 of 243 answers, and the reader's surface would hand the forged token
back as a word they are told to go and look up. That is not a label beside
the sentence. For those gaps it IS the sentence.

The SET half is carried for the same reason and was free in the same way,
at the two sites the shared statement def is not applied to: a refusal's
recorded reason names its set, and that name could be rewritten to any
string, leaving a reader sent to a table no surface holds. Both halves are
asked here, by a walk that descends through everything rather than through
a list of the sites somebody thought of.

What this file does NOT claim: that membership is the whole question. A
token bent to another MEMBER of its own set is a different forgery, and
the instrument that measures coverage cannot yet see it — its domains are
keyed by a leaf's path, so for all 61 token leaves on the corpus it has no
domain and every lie it tells is "not a word at all". That is the next
frontier and it is stated here so it is not read as closed.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for, verify_honestly
from themis import gaps, language
from themis.verifier.errors import VerificationError
from themis.verifier.statement_rules import (
    _CARRIERS, _DECLARED_SILENT, verify_statements_carry_their_facts)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SCHEMAS = pathlib.Path(themis.__file__).parent / "schemas"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
LISTED = frozenset(
    branch["if"]["properties"]["vocabulary"]["const"]
    for branch in json.loads(
        (SCHEMAS / "statement.schema.json").read_text(encoding="utf-8")
    )["$defs"]["closedSets"]["allOf"])

#: What a forged token earns, and the half of the message that says it came
#: from this rule rather than from validation. A forgery at a CARRIER field
#: is refused by the contract before any rule runs; one in a word slot has
#: only this rule, and the two have to be told apart or the gate would pass
#: while the rule did nothing.
FROM_THIS_RULE = "has no such word"


def _pair(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


def _word_slots(node, path=()):
    """Every statement written into a SLOT, with where it sits.

    The slots, not the carriers: a carrier's token is spelled under a field
    of its own and the envelope's schema enumerates it, so it is held twice
    over. A slot is where the set travels beside the token and nothing
    followed it.
    """
    if isinstance(node, dict):
        if isinstance(node.get("vocabulary"), str) and "token" in node:
            yield path, node
        for key, value in node.items():
            yield from _word_slots(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _word_slots(value, path + (index,))


def _members(vocabulary: str) -> frozenset[str]:
    owner = language.VOCABULARIES[vocabulary]
    return frozenset(str(k) for k in owner)


def _records_at(node, steps):
    """Every node at one of ``_CARRIERS``' paths, which name a list position
    ``[]`` and so cannot be walked by subscript."""
    if not steps:
        yield node
        return
    step, rest = steps[0], steps[1:]
    if step == "[]":
        if isinstance(node, list):
            for item in node:
                yield from _records_at(item, rest)
        return
    if isinstance(node, dict) and step in node:
        yield from _records_at(node[step], rest)


def _at(result, path):
    node = result
    for step in path:
        node = node[step]
    return node


# ------------------------------------------- whose the tokens are, declared


def test_every_declared_set_says_whose_its_tokens_are():
    """The registry's two halves reach the same sets.

    A set registered without an answer is a set nothing can ask a
    membership question about, and the question would decline rather than
    fail — so the completeness is the gate, and :func:`language.declare`
    refuses a table that does not say.
    """
    assert set(language.TOKENS_ARE_OURS) == set(language.VOCABULARIES)


def test_the_one_set_of_somebody_elses_tokens_has_another_holder():
    """Counted, so that "the tokens are ours" cannot be said of all of them.

    ``assumption_claim`` is keyed on ids an estimator declares: the table
    is a glossary of the ones this build has words for, and an estimator
    adding one is not a change to the envelope. Nothing is lost by leaving
    it open, because the envelope carries a second record of every claim —
    the ``id`` the estimator declared, which the token is a prefix of — and
    ``assumption_ledger_rules`` holds the pair. Which is why that rule's
    own docstring says it needs no table of legal tokens: it does not, and
    this is the set it was talking about.
    """
    open_sets = {name for name, ours in language.TOKENS_ARE_OURS.items()
                 if not ours}
    assert open_sets == {"assumption_claim"}


def test_a_table_that_does_not_say_is_not_registered():
    """A new table joins by answering, or it does not join.

    The failure this prevents is silent: a set registered without the
    answer would have every token passed over, so the words would reach a
    reader and nothing would hold them, and no test would go red.
    """
    words = {"a_token": {"zh": "一句话", "en": "a sentence"}}
    with pytest.raises(TypeError, match="tokens are this"):
        language.declare("a_set_declared_by_a_test", words,
                         language.BETWEEN_STATEMENTS)
    assert "a_set_declared_by_a_test" not in language.VOCABULARIES
    assert "a_set_declared_by_a_test" not in language.TOKENS_ARE_OURS


def test_a_set_whose_words_live_on_its_members_answers_by_being_one():
    """:class:`language.Word` needs no declaration and gets none.

    Its members ARE the set, so there is nowhere else a token under its
    name could have come from. Asking such a set to say so would be asking
    it to restate its own construction, and a restatement can be wrong.
    """
    name = "a_set_declared_by_a_test"
    try:
        class Declared(language.Word, vocabulary=name,
                       between=language.BETWEEN_STATEMENTS):
            A_WORD = ("a_word", {"zh": "一个词", "en": "a word"})

        assert language.TOKENS_ARE_OURS[name] is True
        assert language.VOCABULARIES[name] is Declared
    finally:
        language.VOCABULARIES.pop(name, None)
        language.TOKENS_ARE_OURS.pop(name, None)
        language.SEAMS.pop(name, None)


# ------------------------------------------- which sets this rule is alone on


def _only_this_rule_holds() -> frozenset[str]:
    """Every set of OUR tokens the shared carrier's contract does not list.

    Where the contract enumerates a set, validation refuses a stranger
    before a rule reads a word, and this rule agrees with it. Where it does
    not, this rule is the only holder there is — so which sets those are is
    the scope of what landed here, and it is derived from the two
    authorities rather than listed.
    """
    return frozenset(name for name, ours in language.TOKENS_ARE_OURS.items()
                     if ours and name not in LISTED)


def test_the_sets_this_rule_is_the_only_holder_of_are_these():
    """The scope, in both directions.

    A set joining ``closedSets`` leaves this list and is held twice; a set
    declared with no enumeration the carrier can reach joins it and is held
    once, here. Either is a deliberate edit and neither should be invisible.

    Twenty-two, and they fall into three families that the two rosters
    below separate: six write their sentences for species this build
    declares in the gap and refusal layers; sixteen belong to artifacts
    other than a query result, and their members are enumerated in their
    own artifact's schema at the field each sits at — which is the same
    reach this round is about, one artifact over.
    """
    assert _only_this_rule_holds() == frozenset({
        "bridge_refusal", "discovery_asks", "discovery_note",
        "estimation_refusal", "extraction_refusal", "gap_describes",
        "gap_if_provided", "gap_routes", "gap_says",
        "lagged_discovery_says", "latent_lagged_discovery_says",
        "markov_blanket_says", "orientation_asks",
        "orientation_propagation_says", "orientation_question_set_says",
        "orientation_session_says", "probability_statement_half",
        "proximal_data_condition", "refusal_sentence", "shape",
        "theta_refusal", "workflow_refusal",
    })


#: Sets whose statements live on an artifact this corpus does not contain.
#:
#: The corpus is answer SHAPES, and a query result is one artifact of
#: several: a discovery result, an orientation session, a bridge or
#: extraction refusal, a workflow's, a theta refusal each carry their own.
#: What is missing is a row to demonstrate on, which is a fact about the
#: corpus and not about the rule — the walk is total over whatever envelope
#: it is handed. Written down because a gate that quietly parametrizes over
#: fewer sets each round is a gate that stops measuring without failing.
NO_SLOT_IN_THIS_CORPUS = frozenset({
    "bridge_refusal", "discovery_asks", "estimation_refusal",
    "extraction_refusal", "lagged_discovery_says",
    "latent_lagged_discovery_says", "markov_blanket_says",
    "orientation_asks", "orientation_propagation_says",
    "orientation_question_set_says", "orientation_session_says",
    "probability_statement_half", "proximal_data_condition", "shape",
    "theta_refusal", "workflow_refusal",
})

#: And two that reach this corpus only at a CARRIER field — a gap's
#: ``kind``, a way past's ``route``. The envelope's own schema enumerates
#: both there, so a forgery is refused by validation and would show nothing
#: about this rule; the rule agrees with the contract and is second.
ONLY_AT_A_CARRIER = frozenset({"gap_if_provided", "gap_routes"})

FORGEABLE = sorted(_only_this_rule_holds()
                   - NO_SLOT_IN_THIS_CORPUS - ONLY_AT_A_CARRIER)


def _a_slot_of(vocabulary: str):
    """A row carrying this set in a word slot, a door that reads it, and
    the slot's path.

    Two conditions, and the second is the one that is easy to lose: the row
    has to CARRY such a slot, and a door has to read the row. A gap
    diagnosis has no reasoning chain and the chain door raises on it rather
    than reading it, so a forgery planted on one and put to that door shows
    a refusal that was already there.
    """
    for name in sorted(SHAPES):
        program, result = _pair(name)
        for path, slot in _word_slots(result):
            if slot["vocabulary"] == vocabulary:
                return name, program, result, path, the_door_for(result)
    return None


def test_the_sets_a_forgery_can_be_shown_on_are_the_ones_with_a_slot():
    """A set losing its witness is the corpus changing, not the gate."""
    excused = NO_SLOT_IN_THIS_CORPUS | ONLY_AT_A_CARRIER
    without = {name for name in _only_this_rule_holds()
               if _a_slot_of(name) is None}
    assert without == excused, {
        "no witness now": sorted(without - excused),
        "witnessed now": sorted(excused - without),
    }


def _only_this_edit_refuses(vocabulary: str, token: str) -> None:
    """The envelope passes; the same envelope with one word changed does not.

    The message is matched, unlike the contract's own gate next door, and
    for the opposite reason: there the pairing was the evidence because two
    depths surface through different branches of a ``oneOf``; here the
    pairing alone would be satisfied by validation refusing the row for
    something else, so what has to be shown is WHICH authority spoke.
    """
    found = _a_slot_of(vocabulary)
    assert found is not None, (
        f"{vocabulary} has no slot to forge on; if that is now true it "
        f"belongs in one of the two rosters above, with its reason")
    name, program, result, path, door = found
    verify_honestly(program, result)
    _at(result, path)["token"] = token
    with pytest.raises(VerificationError, match=FROM_THIS_RULE):
        door(program, result)


@pytest.mark.parametrize("vocabulary", FORGEABLE)
def test_a_word_that_set_does_not_have(vocabulary):
    _only_this_edit_refuses(vocabulary, "a_word_from_nowhere")


@pytest.mark.parametrize("vocabulary", FORGEABLE)
def test_a_word_borrowed_from_another_real_set(vocabulary):
    """The forgery membership catches and a spelling check cannot: every
    word is real, and it is not this set's."""
    borrowed = next(
        token for other in sorted(language.VOCABULARIES)
        if other != vocabulary
        for token in sorted(_members(other))
        if token not in _members(vocabulary))
    _only_this_edit_refuses(vocabulary, borrowed)


# ------------------------------------------- and the set half of the pair


#: Where the contract's ``declaredVocabulary`` enum does not reach, read off
#: the corpus rather than listed: a statement whose set name could be
#: rewritten to any string at all is one the shared statement def is not
#: applied to, and which sites those are is the envelope's schema's business
#: and not this rule's. Both of these are inside a refusal's ``recorded``
#: block, which is typed as an open object.
SETS_NAMED_WHERE_THE_CONTRACT_DOES_NOT_ASK = (
    ("estimator_failure", "recorded", "identification_reason"),
    ("estimator_failure", "recorded", "identification_reason",
     "words", "factors", 0),
)


@pytest.mark.parametrize("path", SETS_NAMED_WHERE_THE_CONTRACT_DOES_NOT_ASK,
                         ids=lambda p: ".".join(str(s) for s in p))
def test_a_set_this_build_does_not_declare(path):
    """The other carried half. A statement names its set beside its token
    because a token alone does not say which set it came from — so the set
    name is a claim too, and at these two sites nothing had read it."""
    found = next(
        ((name, *_pair(name)) for name in sorted(SHAPES)
         if _has(SHAPES[name]["result"], path)), None)
    assert found is not None, f"no row carries a statement at {path}"
    name, program, result = found
    verify_honestly(program, result)
    _at(result, path)["vocabulary"] = "a_set_no_build_declares"
    with pytest.raises(VerificationError, match="declares no such set"):
        the_door_for(result)(program, result)


def _has(node, path) -> bool:
    try:
        for step in path:
            node = node[step]
    except (KeyError, IndexError, TypeError):
        return False
    return isinstance(node, dict) and "vocabulary" in node


# ------------------------------------------- and what stays passed over
#
# The pass-over itself is a unit fact about ``_hold`` and is asked beside
# the rest of that rule's unit cases, in
# ``test_a_sentence_promises_the_facts_it_names``. What belongs here is the
# one shape of it a roster could get wrong.


def test_a_kind_declared_to_have_no_sentence_is_a_member_and_not_a_stranger():
    """The other half of a table that is partial ON PURPOSE.

    ``IF_PROVIDED`` and ``NOTHING_FILLS`` partition the gap kinds, and a
    kind on the second half has no sentence by declaration. The membership
    question must read the partition and not the table, or every one of
    those kinds would be a word from nowhere — 215 gaps in the corpus carry
    one.
    """
    silent = sorted(_DECLARED_SILENT[gaps.PROVIDED])
    assert set(silent) == set(gaps.NOTHING_FILLS)
    assert not (set(silent) & set(gaps.IF_PROVIDED))
    verify_statements_carry_their_facts(
        {"data_gap_report": {"gaps": [{"kind": silent[0]}]}})


# ------------------------------------------- and the price of asking at all


def test_every_word_a_corpus_answer_carries_is_a_member_of_the_set_it_names():
    """The rule refuses nothing honest, measured rather than hoped.

    Both shapes a statement travels in, because the rule asks both: a slot,
    where the set is carried beside the token, and a carrier, where it is
    named by the field. A single honest token outside its set would make
    this rule a refusal of an answer this build produces, and the count is
    here so that "nothing honest is refused" is a number.
    """
    slots = carriers = 0
    missing = []
    for name in sorted(SHAPES):
        _program, result = _pair(name)
        for path, slot in _word_slots(result):
            slots += 1
            vocabulary = str(slot["vocabulary"])
            token = str(slot.get("token") or "")
            if language._words_of(vocabulary, token) is None:
                missing.append((name, ".".join(str(p) for p in path),
                                vocabulary, token))
        for where, (spelling, vocabulary) in _CARRIERS.items():
            for node in _records_at(result, where.split(".")):
                token = node.get(spelling)
                if not token:
                    continue
                carriers += 1
                if (language._words_of(vocabulary, str(token)) is None
                        and str(token)
                        not in _DECLARED_SILENT.get(vocabulary, ())):
                    missing.append((name, where, vocabulary, str(token)))
    assert not missing, missing[:10]
    assert slots >= 1000 and carriers >= 3000, (slots, carriers)
