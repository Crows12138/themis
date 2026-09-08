"""The reader's copy of an assumption, and the machine's.

A ledger entry writes one fact twice. ``id`` is the machine's name —
the token with this occasion's values run together, as in
``propensity_clipped_to_floor_0.01_on_618`` — and it is anchored:
``_check_estimator_channel`` rejects a ledger that drops an id the
estimator declared. ``claim`` is the same fact structured for a reader,
``(token, vocabulary, said)``, and it is what the sentence is built from.

Only the machine's copy was held. Measured before this: on all forty-four
answer shapes the token, the vocabulary and every value under ``said``
could each be rewritten and the public door said yes, while ``id``,
``layer``, ``severity`` and ``provenance`` were all refused. The
repository's own criterion — whatever is recorded twice, the other record
is where you hold it — had a second record sitting unused.

So the fix needs no new authority and no table of legal tokens: it asks
the two copies to agree. It READS the id rather than rebuilding it,
because the format belongs to whoever writes it and a verifier that
reassembled ``token + values`` would turn a change of format into an
apparent disagreement about the assumption.

One hundred and fifty leaf shapes survived here; fifty still did when the
corpus was those forty-four. It has since widened to the answers that
carry no number, which added a second channel writing entries no estimator
declares and one survivor that is not a family at all. What survives now
is counted at the bottom rather than described.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.verifier.assumption_ledger_rules import (
    _ESTIMATOR_CLAIM_VOCABULARY,
)
from themis.input.syntactic_validator import SyntacticError
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _entries(result):
    return (((result.get("extensions") or {})
             .get("assumption_ledger") or {}).get("assumptions") or [])


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _first_anchored(result):
    """The first entry that has an id to be held against, and a claim."""
    for i, e in enumerate(_entries(result)):
        if isinstance(e.get("id"), str) and e["id"] and e.get("claim"):
            return i, e
    return None, None


WITH_LEDGER = sorted(n for n, p in SHAPES.items() if _entries(p["result"]))

#: The rows this rule can be asked about. A ledger whose every entry comes
#: from a channel that declares no id has no second record for the reader's
#: copy to be held against — that is the family named below, and a forgery
#: refused on such a row would have to be refused by something else, which
#: is not what these two tests would be measuring.
ANCHORED = [name for name in WITH_LEDGER
            if _first_anchored(SHAPES[name]["result"])[1] is not None]

#: The answers the public door will look at. It requires a derivation and
#: refuses an answer without one before reading a word, so on those rows
#: every forgery is refused for what the answer IS — counting that as a
#: leaf being held would be manufacturing a witness.
READ_BY_THE_DOOR = sorted(
    name for name, pair in SHAPES.items()
    if pair["result"].get("derivation") is not None)


# ------------------------------------------------- the facts this rests on


def test_the_two_copies_agree_on_every_answer_this_repository_produces():
    """Stated as the measurement the rule is built on.

    Every claim token is a prefix of its entry's id — most equal to it,
    the rest proper prefixes where the id carries this occasion's values —
    and every value under ``said`` appears in what the id has left over.

    The proper prefixes went up by one, and the values with them, when a
    corpus refresh took ``longitudinal_ipw_msm`` from a run that resolved a
    cluster column: the cluster-bootstrap declaration is an id that carries
    the column's name, so it is one more entry of exactly the kind this
    counts. A ledger line arriving is the producer having more to declare,
    not this rule reaching further.
    """
    equal = prefix = values = no_id = 0
    for pair in SHAPES.values():
        for e in _entries(pair["result"]):
            ident = e.get("id")
            for one in e.get("claim") or []:
                token = one.get("token")
                if not isinstance(ident, str) or not ident:
                    no_id += 1
                    continue
                assert ident.startswith(token), (ident, token)
                equal += ident == token
                prefix += ident != token
                left_over = ident[len(token):]
                for value in (one.get("said") or {}).values():
                    assert str(value) in left_over, (ident, value)
                    values += 1
    assert (equal, prefix, values, no_id) == (448, 60, 62, 24), (
        equal, prefix, values, no_id)


def test_the_entries_with_nothing_to_hold_them_are_named():
    """Some entries carry no id, so nothing on the envelope is a second
    record of them and this rule does not hold them.

    This said two channels wrote one, both about where an EDGE came from
    rather than how a number was computed, and said that a third arriving
    should fail here so somebody decides. A third arrived, and the
    decision is that it belongs with them: ``a_commonsense_prior`` is a
    warrant for a PARAMETER rather than an edge, but it is the same kind
    of warrant — one that lives in what a caller supplied, not in an
    estimator that could declare an id for it. An entry is unheld here
    because nothing on the envelope is a second record of it, and that is
    as true of a prior as of a proposed edge.

    The discovery channel now also appears carrying a second sentence, the
    share of resamples its edge survived. That is one channel saying more,
    not a fourth channel, so the claim TOKENS are compared as a set: what
    this test is about is which warrants go unheld, and a channel that
    starts explaining itself better should not read as a new one.
    """
    unanchored = {
        token
        for pair in SHAPES.values()
        for e in _entries(pair["result"])
        if not e.get("id")
        for token in (c.get("token") for c in (e.get("claim") or []))
    }
    assert unanchored == {
        "the_edge_is_an_llm_proposal",
        "the_edge_was_learned_by_discovery",
        "the_edge_survived_this_share_of_resamples",
        "a_commonsense_prior",
    }, unanchored


def test_the_vocabulary_is_held_only_where_something_anchors_it():
    """A roster of vocabularies is not knowable from here, and saying so
    is the point of this test.

    The first version of this rule listed the vocabularies the forty-four
    answer shapes contain and refused an honest answer whose ledger quoted
    a third — ``theta_prior_claim``, reached only through an LLM-prior
    patch. The table of which vocabularies a reader is glossed from lives in
    ``themis.output.reader_words``, which no verifier module imports, so any
    list written here can only be an inference from the answers this
    repository happens to produce.

    That vocabulary is now IN the corpus, which is the argument made
    twice: a list of vocabularies read off a snapshot was wrong about the
    next snapshot, exactly as predicted, and the rule that stayed narrow
    needed no change when it arrived. What follows is unchanged — the
    anchored side is still one vocabulary — because the new one is on an
    entry with no id, which is the side this holds nothing on.

    What is left is narrower and anchored: an entry the estimator declared
    says its sentence from the assumption glossary. The vocabularies that
    are not that one belong to the channels that declare no id, and those
    entries are not held at all.
    """
    from themis.output.reader_words import GLOSSED

    assert _ESTIMATOR_CLAIM_VOCABULARY in GLOSSED
    anchored = {
        one.get("vocabulary")
        for pair in SHAPES.values()
        for e in _entries(pair["result"])
        if e.get("id")
        for one in e.get("claim") or []
    }
    assert anchored == {_ESTIMATOR_CLAIM_VOCABULARY}, anchored
    unanchored = {
        one.get("vocabulary")
        for pair in SHAPES.values()
        for e in _entries(pair["result"])
        if not e.get("id")
        for one in e.get("claim") or []
    }
    assert unanchored == {"gap_describes", "theta_prior_claim"}, unanchored


# ------------------------------------------ rewriting the reader's copy


@pytest.mark.parametrize("shape", ANCHORED)
def test_a_line_may_not_tell_a_reader_it_is_a_different_assumption(shape):
    program, result = _pair(shape)
    i, entry = _first_anchored(result)
    assert entry is not None, shape
    entry["claim"][0]["token"] = entry["claim"][0]["token"] + "_forged"
    with pytest.raises(VerificationError, match="not the same fact"):
        the_door_for(result)(program, result)


@pytest.mark.parametrize("shape", ANCHORED)
def test_a_declared_line_may_not_send_a_reader_to_another_glossary(shape):
    """The forgery is a REAL other vocabulary, not a nonsense one: the
    failure this prevents is a lookup that lands in the wrong table, and a
    nonsense name would be refused by a weaker rule than this.

    It names ``gap_describes`` rather than ``theta_prior_claim``, which it
    named while the contract enumerated the members of eight sets. It
    enumerates thirty-four now, ``theta_prior_claim`` among them, so that
    forgery is refused by validation before this rule reads it — the token
    stays and no longer belongs to the set the line claims. The refusal was
    still a refusal, which is exactly why the substitution matters: a test
    whose subject is WHICH rule objects has to keep handing that rule
    something to object to. ``gap_describes`` is a table of ids another
    layer coins, so no enumeration stands in front of it, and the two are
    the two sets a ledger claim may honestly quote.
    """
    program, result = _pair(shape)
    i, entry = _first_anchored(result)
    entry["claim"][0]["vocabulary"] = "gap_describes"
    with pytest.raises(VerificationError, match="states its sentence from"):
        the_door_for(result)(program, result)


@pytest.mark.parametrize("shape", ANCHORED[:3])
def test_the_glossary_a_line_names_is_now_refused_earlier_where_it_can_be(
        shape):
    """And the other half of that substitution, so the reason for it is
    held rather than only written above: where the set a line falsely
    claims IS one the contract enumerates, the contract refuses it, and
    the token it kept is what gives it away."""
    program, result = _pair(shape)
    _i, entry = _first_anchored(result)
    entry["claim"][0]["vocabulary"] = "theta_prior_claim"
    with pytest.raises(SyntacticError, match="is not one of"):
        the_door_for(result)(program, result)


def _shape_with_said():
    for name in WITH_LEDGER:
        for i, e in enumerate(_entries(SHAPES[name]["result"])):
            for j, one in enumerate(e.get("claim") or []):
                if one.get("said") and e.get("id"):
                    return name, i, j, sorted(one["said"])[0]
    raise AssertionError("no ledger claim carries said values")


def test_a_line_may_not_tell_a_reader_a_value_its_own_id_denies():
    name, i, j, key = _shape_with_said()
    program, result = _pair(name)
    result["extensions"]["assumption_ledger"]["assumptions"][i][
        "claim"][j]["said"][key] = "9999"
    with pytest.raises(VerificationError, match="says otherwise"):
        the_door_for(result)(program, result)


def test_a_line_may_not_name_a_value_and_leave_it_empty():
    """Emptiness is asked before containment, and this is why.

    "The value appears in the id" is a containment test, and every
    containment test is satisfied by the empty value: ``"" in anything``
    is true. So a line that told a reader nothing where a number goes
    would have passed by saying nothing at all — the third time in three
    frontiers that a check has been vacuous on empty. No honest answer in
    the corpus has an empty value here.
    """
    name, i, j, key = _shape_with_said()
    program, result = _pair(name)
    result["extensions"]["assumption_ledger"]["assumptions"][i][
        "claim"][j]["said"][key] = ""
    with pytest.raises(VerificationError, match="puts nothing there"):
        the_door_for(result)(program, result)


# ------------------------------------------- what this does not close yet


def test_the_remainder_is_counted_rather_than_described():
    """Every ledger leaf shape, bent the census's three ways.

    Sixty-three survive over nine shapes, and they fall in two parts.

    It was sixty-four until the contract enumerated the members of the sets
    whose members the kernel owns. One of these lines quotes such a set, so
    a bent token of it is now refused by validation — which is the same
    answer this file gives about ``claim.vocabulary`` below, arriving one
    field over.

    **Sixty are lines that name no assumption**, counted once per field
    of theirs a bend gets through: ``claim.token`` (18), ``testable`` (19),
    ``said.edge`` (18), ``said.algorithm`` (2), and ``said.key`` /
    ``said.value`` / ``said.confidence`` (1 each) — the proposal channels
    and the supplied prior, which state their line from the gap vocabulary
    instead of naming an assumption.

    ``testable`` used to be much the largest family here, and the paragraph
    that stood in this place said it was a fact about the SYSTEM rather
    than this run, that the envelope held no second record of it, and that
    it needed its own frontier rather than a line here. It got one. The
    second record was never missing — it was in a table under
    ``themis/output/``, which no verifier may read, so the only statement
    of what an assumption ID means was one an audit was forbidden to look
    at. The table is ``themis.assumption_glossary`` now, on the same
    footing as any other statement of what a name means, and a line naming
    an assumption is held to what that name means. What is left is the
    range that rule declares: a table keyed on the assumption's NAME cannot
    be right or wrong about a line that names none.

    **Three are named lines, and both of the shapes are the id's own
    left-over.** ``id`` (2) is one id lengthened by ``_forged``: the entry's
    claim says a token and nothing else, so the part after the token, where
    this occasion's values go, is constrained by nothing, and appending to
    an id looks exactly like an occasion having values. The declaration
    does not catch it either, and that is the price of its being total — an
    id nobody classified and an id nobody could have emitted arrive as the
    same thing, deliberately, because on a disclosure surface the safe
    direction is to over-report rather than drop. Refusing it means holding
    the id's FORMAT, or a roster of which ids this build can emit, and
    neither is a thing this file can read: the estimators own that, not the
    glossary. ``said.suffix`` (1) is the same limitation in a slot —
    ``{x,z}`` bent to ``x``, a value that occurs in the id it is checked
    against.

    ``claim.vocabulary`` used to be a third three, and the reason it was
    here is the reason it no longer is. An earlier version of this rule did
    hold it — against a list of vocabularies INFERRED FROM THESE
    FORTY-FOUR ANSWERS — and refused an honest answer that quoted a third.
    What was wrong was the list's authority, not the check: the sets this
    build declares are now enumerated in the statement carrier, so the
    contract refuses a set that does not exist without any rule here
    guessing which ones do.
    """
    def leaf(v, p=()):
        if isinstance(v, dict):
            for k, x in v.items():
                yield from leaf(x, p + (k,))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                yield from leaf(x, p + (i,))
        else:
            yield p, v

    def bends(v):
        if isinstance(v, bool):
            return [not v]
        if isinstance(v, int):
            return [v + 7, 0, v * 2 + 1, -abs(v) - 1]
        if isinstance(v, float):
            return ([0.9 if v < 0.5 else 0.1, v / 2 + 0.01, 0.0]
                    if 0 <= v <= 1 else [v * 3 + 1, -v - 1, 0.0, v / 2])
        if isinstance(v, str):
            return [v + "_forged", "", "x"]
        return []

    # Every ledger is bent at the door that READS the answer carrying it.
    # The concern this line was written for is real — a bend scored
    # against a door that refuses an answer for what it IS counts a
    # blindness as coverage — but the guard for it was a chain, and a
    # chain is not what makes an answer readable. Ledgers now sit on
    # answers that took no route, and asking those at the chain door
    # would have been exactly the mistake the guard was against.
    assert all(the_door_for(SHAPES[n]["result"]) is not None
               for n in WITH_LEDGER)

    survived = 0
    for name in sorted(SHAPES):
        program = SHAPES[name]["program"]
        base = SHAPES[name]["result"]
        seen = set()
        for path, value in leaf(base):
            shape = ".".join("[]" if isinstance(x, int) else x for x in path)
            if not shape.startswith("extensions.assumption_ledger"):
                continue
            if shape in seen:
                continue
            seen.add(shape)
            for new in bends(value):
                if new == value:
                    continue
                bad = copy.deepcopy(base)
                node = bad
                for step in path[:-1]:
                    node = node[step]
                node[path[-1]] = new
                try:
                    the_door_for(bad)(program, bad)
                except Exception:
                    continue
                survived += 1
                break
    assert survived == 63, survived
