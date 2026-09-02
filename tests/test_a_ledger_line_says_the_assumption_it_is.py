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

One hundred and fifty leaf shapes survived here; fifty still do, and
what they are is counted at the bottom rather than described.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.assumption_ledger_rules import (
    _ESTIMATOR_CLAIM_VOCABULARY,
)
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


# ------------------------------------------------- the facts this rests on


def test_the_two_copies_agree_on_every_answer_this_repository_produces():
    """Stated as the measurement the rule is built on.

    Every claim token is a prefix of its entry's id — most equal to it,
    the rest proper prefixes where the id carries this occasion's values —
    and every value under ``said`` appears in what the id has left over.
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
    assert (equal, prefix, values, no_id) == (214, 34, 37, 3), (
        equal, prefix, values, no_id)


def test_the_entries_with_nothing_to_hold_them_are_named():
    """Three entries carry no id, so nothing on the envelope is a second
    record of them and this rule does not hold them. Declared rather than
    skipped: if a fourth appears, or these stop being what they are, this
    fails and somebody decides."""
    unanchored = {
        tuple(c.get("token") for c in (e.get("claim") or []))
        for pair in SHAPES.values()
        for e in _entries(pair["result"])
        if not e.get("id")
    }
    assert unanchored == {("the_edge_is_an_llm_proposal",)}, unanchored


def test_the_vocabulary_is_held_only_where_something_anchors_it():
    """A roster of vocabularies is not knowable from here, and saying so
    is the point of this test.

    The first version of this rule listed the vocabularies the forty-four
    answer shapes contain and refused an honest answer whose ledger quoted
    a third — ``theta_prior_claim``, reached only through an LLM-prior
    patch. The tables live in ``themis.output``, which no verifier module
    imports, so any list written here can only be an inference from the
    answers this repository happens to produce.

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
    assert unanchored == {"gap_describes"}, unanchored


# ------------------------------------------ rewriting the reader's copy


@pytest.mark.parametrize("shape", WITH_LEDGER)
def test_a_line_may_not_tell_a_reader_it_is_a_different_assumption(shape):
    program, result = _pair(shape)
    i, entry = _first_anchored(result)
    assert entry is not None, shape
    entry["claim"][0]["token"] = entry["claim"][0]["token"] + "_forged"
    with pytest.raises(VerificationError, match="not the same fact"):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", WITH_LEDGER)
def test_a_declared_line_may_not_send_a_reader_to_another_glossary(shape):
    """The forgery is a REAL other vocabulary, not a nonsense one: the
    failure this prevents is a lookup that lands in the wrong table, and a
    nonsense name would be refused by a weaker rule than this."""
    program, result = _pair(shape)
    i, entry = _first_anchored(result)
    entry["claim"][0]["vocabulary"] = "theta_prior_claim"
    with pytest.raises(VerificationError, match="states its sentence from"):
        themis.verify(program, result)


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
        themis.verify(program, result)


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
        themis.verify(program, result)


# ------------------------------------------- what this does not close yet


def test_the_remainder_is_counted_rather_than_described():
    """Every ledger leaf shape, bent the census's three ways.

    Fifty of the original hundred and fifty survive:

    ``testable`` (40) says whether data could refute this assumption. It
    is a fact about the SYSTEM, not this run — measured, it is a function
    of the token across all 118 of them — and the envelope holds no second
    record of it. ``_CHECKS`` in the rules module knows only the checks
    re-runnable from this envelope, so it cannot answer for the rest. That
    is a line the system draws over a hundred and eighteen tokens, and it
    needs its own frontier rather than a line here.

    ``claim.token`` (3) and ``said.edge`` (3) are the LLM-proposal entries
    named above, which carry no id.

    ``claim.vocabulary`` used to be a third three, and the reason it was
    here is the reason it no longer is. An earlier version of this rule did
    hold it — against a list of vocabularies INFERRED FROM THESE
    FORTY-FOUR ANSWERS — and refused an honest answer that quoted a third.
    What was wrong was the list's authority, not the check: the sets this
    build declares are now enumerated in the statement carrier, so the
    contract refuses a set that does not exist without any rule here
    guessing which ones do.

    ``said.suffix`` (1) survives a bend to a value that happens to occur
    in the id it is checked against — the same in-corpus limitation as a
    swap between two real names.
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
                    themis.verify(program, bad)
                except Exception:
                    continue
                survived += 1
                break
    assert survived == 47, survived
