"""A gap's contents, and the walk that never reached them.

A gap carries a ``need`` token and a ``said`` mapping, and the sentence a
reader gets is the template for that token with those facts substituted
in. So ``said`` is the sentence's CONTENTS. "No data on ``y``" and "no
data on ``y_forged``" are the same gap saying different things, and only
one of them is about this problem.

``data_gap_rules`` runs three audits and every one is about the report's
skeleton — provenance points at something real, every upstream failure is
covered, a gap's ``kind`` agrees with the signal it cites. Each writes its
own ``for gap in report["gaps"]`` loop and none descends into a gap.
Grepping the verifier package for ``describes`` or ``alternative_paths``
returns the English word in prose and nothing else. Measured before this:
all four hundred and sixty-two ``said`` string leaves on the forty-four
answer shapes could be rewritten and the public door said yes.

The defect is the DEPTH of a walk, not a missing field, so the fix is a
depth-blind walk rather than three more loops. Two hundred and
eighty-seven of the four hundred and sixty-two were refused by it, and the
rest were claim-kinds with their own root causes, counted at the bottom of
this file rather than described.

The corpus has since widened to the answers that carry no number, and both
halves of that paragraph moved: the walk found three more depths without
being touched, and thirteen keys arrived that the roster had never
classified, because a roster measured against answers that reached an
estimator is a statement about estimators. The counts below are the ones
this build gives, and they are taken at the strongest door that reads each
answer: an answer whose whole content is a gap report has no chain, so the
door that re-runs chains will not read it, and the door that holds what an
answer SAYS is the one that asks it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import (
    _NAMES, _NOT_NAMES, every_said, words_the_problem_uses,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _said_leaves(result):
    return list(every_said(result.get("data_gap_report") or {}))


WITH_NAMES = sorted(
    name for name, pair in SHAPES.items()
    if any(key in _NAMES for _, key, _ in _said_leaves(pair["result"])))


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _set_at(report, dotted, value):
    node = report
    steps = dotted.split(".")
    for step in steps[:-1]:
        node = node[int(step)] if isinstance(node, list) else node[step]
    node[steps[-1]] = value


# ------------------------------------------------- the facts this rests on


def test_a_gap_report_is_carried_by_almost_every_answer():
    """Stated so a narrowing shows up as a failure, not as a quiet pass."""
    carriers = [n for n in SHAPES
                if (SHAPES[n]["result"].get("data_gap_report") or {}).get(
                    "gaps")]
    assert len(carriers) == 231, sorted(set(SHAPES) - set(carriers))
    # Some carriers say nothing that names a variable, so they have gaps
    # and nothing for this rule to ask. That is an answer, not a skip.
    assert len(set(carriers) - set(WITH_NAMES)) == 52, len(
        set(carriers) - set(WITH_NAMES))
    assert len(WITH_NAMES) == 179, len(WITH_NAMES)


def test_every_key_a_gap_says_is_classified():
    """The roster is a statement about the whole key space.

    A rule that checks the keys someone happened to think of has coverage
    that is a fact about its author. Every key any answer shape produces
    must be named either as a name or as the kind of thing it is instead,
    so a new one arrives as a failure rather than as an exemption.
    """
    seen = set()
    for pair in SHAPES.values():
        seen.update(key for _, key, _ in _said_leaves(pair["result"]))
    unclassified = seen - set(_NAMES) - set(_NOT_NAMES)
    assert unclassified == set(), unclassified
    assert not (set(_NAMES) & set(_NOT_NAMES))


def test_the_walk_reaches_every_depth_a_gap_uses():
    """The scope, asserted rather than implied — and the argument for it.

    Three depths were known when this was written: the gap itself, each
    item it describes, each alternative path. The walk was made
    depth-blind because DEPTH was the defect, and it then returned two
    nobody had listed — a gap nested inside a glossed word, which names a
    variable a reader is shown (``…words.variables[].said.variable``).
    Three hand-written loops would have missed exactly those two.

    Widening the corpus to the answers that carry no number returned three
    more, one of them a gloss inside a gloss, and again the walk needed no
    change: the depths a report uses are a fact about producers, and the
    only honest way to hold them is to find them and say how many there
    are. None of the eight is written into the walk. This is the only
    place they are named, and narrowing the walk fails here.
    """
    depths = set()
    for pair in SHAPES.values():
        for where, _, _ in _said_leaves(pair["result"]):
            parts = where.split(".")
            depths.add(".".join(p for p in parts[:-2] if not p.isdigit()))
    assert depths == {
        "gaps",
        "gaps.describes",
        "gaps.alternative_paths",
        "gaps.required_data.precision_target",
        "gaps.describes.words.variables",
        "gaps.describes.words.violations",
        "gaps.describes.words.why",
        "gaps.describes.words.why.words.detail",
        # And two more from the re-harvested corpus, both deeper than any
        # listed before: a note glossed inside a why, and a refusal
        # glossed inside that note. Ten now, and still none of them
        # written into the walk.
        "gaps.describes.words.why.words.note",
        "gaps.describes.words.why.words.note.words.refusal",
    }, depths


# ------------------------------------------------------ rewriting a gap


@pytest.mark.parametrize("shape", WITH_NAMES)
def test_a_gap_may_not_be_about_a_variable_this_problem_lacks(shape):
    """Rename the variable a gap says it is about.

    Two rules refuse this and which one arrives depends on the problem.
    Where it reports names, the renamed word is not among them and the
    membership rule says so. Where it reports none, that rule has nothing
    to be a member of and declines — and the forgery is caught by the
    gap's own provenance instead, which never mentions the new word.

    Both are refusals, and this asks only that one of them arrives: which
    it is on a given row is not a fact this test can read off the program
    without restating how a context gets built. It is measured instead,
    once and with a number, by the test below — so "some rows take the
    other branch" cannot grow quietly, while no row here can be silently
    accepted.
    """
    program, result = _pair(shape)
    where, _, value = next(
        (w, k, v) for w, k, v in _said_leaves(result) if k in _NAMES)
    _set_at(result["data_gap_report"], where, value + "_forged")
    with pytest.raises(VerificationError,
                       match="does not name|this gap is not about"):
        the_door_for(result)(program, result)


def test_which_of_the_two_refusals_a_renamed_variable_earns():
    """The split above, counted where it can go stale.

    A problem that reports no names is rare and is not a curiosity: it is
    the shape every rule that compares against a vocabulary has to decide
    what to do about, and the decision is to decline that comparison and
    let a rule needing no vocabulary answer. Exactly one answer in the
    corpus is on such a problem. If that becomes many, the second rule is
    carrying weight nobody measured; if it becomes none, this file stops
    testing the branch and would not say so.
    """
    membership, provenance = [], []
    for shape in WITH_NAMES:
        program, result = _pair(shape)
        where, _, value = next(
            (w, k, v) for w, k, v in _said_leaves(result) if k in _NAMES)
        _set_at(result["data_gap_report"], where, value + "_forged")
        try:
            the_door_for(result)(program, result)
        except VerificationError as exc:
            (membership if "does not name" in str(exc)
             else provenance).append(shape)
    assert len(membership) + len(provenance) == len(WITH_NAMES)
    assert provenance == ["needs_investigation:probability:none#6bdf54"], (
        provenance)


def test_a_name_is_read_out_of_the_spelling_not_the_spelling_out_of_a_parse():
    """One claim, five spellings, and why none of them is parsed.

    A gap writes a variable bare (``y``), applied to the object it is
    about (``y(u)``), as a set (``{m1(me), m2(me)}``), as a pair with an
    arrow (``a → b``), and as a backtick-quoted list. Two of those five
    were found only by auditing the roster against the data — both had
    been filed as prose — and the rule needed no change to accept them,
    because it pulls identifier tokens out instead of parsing spellings.
    A rule that parsed would have earned a bug per spelling.
    """
    spellings = set()
    for pair in SHAPES.values():
        for _, key, value in _said_leaves(pair["result"]):
            if key not in _NAMES:
                continue
            spellings.add(
                "set" if value.startswith("{")
                else "arrow" if "→" in value
                else "quoted list" if "`" in value
                else "applied" if "(" in value
                else "bare")
    assert spellings == {
        "bare", "applied", "set", "arrow", "quoted list"}, spellings


def test_the_words_a_problem_uses_come_from_every_source_the_context_has():
    """The trap this repository walked into one frontier earlier.

    An estimation route's graph carries the variables while its theta is
    empty; a probability query's theta carries them while its graph, built
    from the cause statements, has no nodes at all. A rule that asked one
    source would read "took part in no edge" as "does not exist" and
    refuse an honest answer. Both directions are pinned.
    """
    import networkx as nx

    from themis.runtime.numeric_estimator import Theta
    from themis.types import Atom
    from themis.verifier.context import VerificationContext

    y = Atom("y", ())

    class _Q:
        pass

    graphless = VerificationContext(graph=nx.DiGraph(), query=_Q())
    assert words_the_problem_uses(graphless) == set()

    theta = Theta()
    theta.domains[y] = (True, False)
    thetaonly = VerificationContext(
        graph=nx.DiGraph(), query=_Q(), theta=theta)
    assert "y" in words_the_problem_uses(thetaonly)

    withgraph = nx.DiGraph()
    withgraph.add_node(Atom("x", ()))
    graphonly = VerificationContext(graph=withgraph, query=_Q())
    assert words_the_problem_uses(graphonly) == {"x"}


@pytest.mark.parametrize("shape", WITH_NAMES)
def test_a_gap_may_not_say_which_variable_and_then_say_nothing(shape):
    """An empty name is a claim, not the absence of one.

    The walk used to skip falsy values, which is a decision wearing the
    clothes of an absence — the same shape as the defect this whole line
    of work is about, written into the fix. The census's own edit set
    includes the empty string, so every gap shape was escaping through it
    while the renamed-variable forgery was being refused. Measured: no
    honest answer in the corpus has an empty name; the one honest empty
    value in it sits on a ``note``, which is prose and not a name.
    """
    program, result = _pair(shape)
    where, _, _ = next(
        (w, k, v) for w, k, v in _said_leaves(result) if k in _NAMES)
    _set_at(result["data_gap_report"], where, "")
    with pytest.raises(VerificationError, match="says nothing there"):
        the_door_for(result)(program, result)


def test_an_honest_empty_value_survives_where_it_is_not_a_name():
    """The other direction, so the rule above cannot be widened by
    accident: some answers honestly carry an empty ``note``, and prose is
    allowed to be absent in a way a variable name is not.

    Stated about the KEY rather than about which answers happened to have
    one. Which rows carry an empty note is a fact about what those
    producers had to say; that no empty one ever sits where a variable
    goes is the claim, and it stays the claim at any corpus size. Each is
    put through its own door afterwards, so "allowed" means measured.
    """
    empties = [
        (name, where, key)
        for name, pair in SHAPES.items()
        for where, key, value in _said_leaves(pair["result"])
        if value == ""
    ]
    assert len(empties) == 5, empties
    assert {key for _, _, key in empties} == {"note"}
    assert not {key for _, _, key in empties} & set(_NAMES)
    for name in sorted({name for name, _, _ in empties}):
        program, result = _pair(name)
        the_door_for(result)(program, result)


# ------------------------------------------- what this does not close yet


def test_the_remainder_is_counted_rather_than_described():
    """Every ``said`` string leaf, bent one at a time, through the door.

    The refused are the name claim and, for ``missing``, the later rule
    that asks which fields a gap may say a variable lacks. The accepted
    are six other kinds, and none of them is a line missing from this
    rule:

    A VOCABULARY member (``assumptions``, ``method``, ``branch`` …) would
    need a table of strings restated in the verifier, and some of those
    keys hold English prose — a verifier that pins prose in a repository
    with a language layer is a false refusal waiting for the first
    translation.

    A NUMBER (``count``, ``total``, ``share``, ``j`` …) needs a second
    record and most do not have one: the matches a search finds are
    coincidences (``high`` 1.000 equals a graph edge's endpoint, ``df`` 1
    equals a bounds value), and several keys match nothing at all. A rule
    built on those would be a table indexed by key name, which is the
    shape this frontier exists to remove.

    An EXPRESSION is written in the notation as well as in the problem's
    words, so the token membership this rule uses would refuse an honest
    one for saying ``P`` or ``do``; holding it means reading the notation,
    which is the estimand rule's trade and not a key to add here.

    A DOMAIN names a population rather than a variable, and the words this
    rule knows are the problem's variables by construction.

    A VALUE is a member of a variable's domain — ``True``, ``0``,
    ``[False, True]`` — so holding one means reading the declared domains,
    a different table from the problem's words.

    A QUOTED word is one the gap is reporting BECAUSE the problem lacks
    it. Holding it would refuse the gap whose entire subject is that the
    word is not theirs.

    The number is asserted so that closing any kind fails here. It counts
    leaves rather than rows, so it also moves when the producer writes a
    name it used to leave out — the route beside a declared loop names the
    loop's two variables now, and the shortfall about a joint intervention
    names the layer it collided with.

    Both halves move for a second reason worth knowing, since it looks
    like this rule losing ground and is not: a corpus row that the
    producer has moved away from is refused WHOLESALE by whatever rule
    catches the drift, whichever leaf the forgery is planted in. One such
    row was contributing 22 refusals that were about the row and not about
    the forgeries; refreshed, it contributes 8.
    """
    refused = accepted = 0
    for name in sorted(SHAPES):
        program, base = _pair(name)
        door = the_door_for(base)
        for where, _, value in _said_leaves(base):
            bad = copy.deepcopy(base)
            _set_at(bad["data_gap_report"], where, value + "_forged")
            try:
                door(program, bad)
            except VerificationError:
                refused += 1
            else:
                accepted += 1
    assert (refused, accepted) == (1513, 755), (refused, accepted)


def test_the_answer_that_is_nothing_but_a_gap_report_is_asked_too():
    """The rows this file could not put a question to, and now can.

    Seventy-one answers took no route, so they carry no chain, and the
    door that re-runs a chain refuses them before reading a word. Their
    gap report is not a footnote to an answer — it IS the answer, and a
    large share of its leaves are the very name claim this file exists to
    hold. They were counted here as a hole for one frontier, and the hole
    was never this rule's: the audits that are facts about the ANSWER
    stood behind a precondition belonging to the audits that are facts
    about the ROUTE.

    Now they are asked at the door that reads them. Pinned so that the
    coverage above cannot quietly go back to being a statement about the
    answers that happened to reach an estimator. It was six answers when
    that was written, which is small enough to read as a curiosity; the
    re-harvest brought seventy-one, and the same sentence is now about
    most of a third of everything this repository produces.
    """
    chainless = sorted(name for name, pair in SHAPES.items()
                       if pair["result"].get("derivation") is None)
    leaves = [(name, key) for name in chainless
              for _, key, _ in _said_leaves(SHAPES[name]["result"])]
    assert len(chainless) == 71, len(chainless)
    assert len(leaves) == 998, len(leaves)
    assert sum(1 for _, key in leaves if key in _NAMES) == 450, len(leaves)
    # The three with no name claim in them have nothing here to ask, which
    # is not the same as this missing them: a refusal outside the language
    # says why in prose and has no variable to be about, and two causation
    # reports say only what they could not settle.
    assert set(chainless) - set(WITH_NAMES) == {
        "needs_investigation:causation:none",
        "needs_investigation:causation:none#4f0014",
        "outside_language:causation:none",
    }, sorted(set(chainless) - set(WITH_NAMES))
    for name in chainless:
        assert the_door_for(SHAPES[name]["result"]) is themis.verify_answer_claims
