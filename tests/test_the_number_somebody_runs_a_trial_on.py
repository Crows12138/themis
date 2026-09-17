"""How much data a reader is told to go and collect.

A blocking gap ends in an instruction somebody runs a trial on. Measured
before the rule: 229 of the leaves under ``required_data`` on the answer
shapes could be rewritten and both public doors said yes — every minimum
sample size among them.

The number is not a copy of anything, which is why nothing on the envelope
held it. It is a power calculation, and the calculation's inputs travel
beside it: the target that says what the number buys states the terms it
was computed from. So the authority is the arithmetic, re-run from a
second transcription — the producer lives in ``themis.output``, which no
verifier may reach, and re-running the producer's own code would prove
only that it agrees with itself.

The relations are measured here before the rule is allowed to lean on
them, since a relation nobody measured is a false refusal waiting for the
shape that disobeys it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import language
from themis.kernel import _premises_of
from themis.output.sample_size import Precision
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import words_the_problem_uses
from themis.verifier.sample_size_rules import (
    _THE_ARITHMETIC, _declared_populations, verify_required_data)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: (answer, gap index, the ask) for every gap that tells a reader what to
#: collect.
ASKS = [
    (name, index, gap["required_data"])
    for name, pair in sorted(SHAPES.items())
    for index, gap in enumerate(
        ((pair.get("result") or {}).get("data_gap_report")
         or {}).get("gaps") or [])
    if isinstance(gap.get("required_data"), dict)
]

CONTEXTS = {
    name: _premises_of(pair["program"], pair["result"])[3]
    for name, pair in SHAPES.items()
}


# ------------------------------------------------- the facts this rests on


def test_the_corpus_carries_data_asks():
    """Stated so a narrowing shows up as a failure, not as a quiet pass."""
    assert len(ASKS) == 135, len(ASKS)


def test_every_precision_target_this_build_can_write_has_arithmetic_here():
    """Coverage of a closed vocabulary, so it can be a fact rather than a hope.

    The rule is silent on a target it has no formula for, and a silence
    nobody measures is how a field goes unheld while looking held. Bound
    here rather than in the rule, because the vocabulary lives in the
    output layer and no verifier may import it — the rule reads the token
    off the envelope and this reads the roster off its author.
    """
    missing = sorted(str(member) for member in Precision
                     if str(member) not in _THE_ARITHMETIC)
    assert not missing, missing


def test_the_number_is_what_its_own_terms_buy():
    """Every ask in the corpus, re-derived from the target beside it."""
    checked = 0
    for name, index, need in ASKS:
        if need.get("min_sample_size") is None:
            continue
        target = need["precision_target"]
        arithmetic = _THE_ARITHMETIC[str(target["token"])]
        again = arithmetic(lambda key: float(target["said"][key]))
        assert again == need["min_sample_size"], (name, index, again)
        checked += 1
    assert checked == 134, checked


def test_the_names_a_reader_is_sent_after_are_the_problems():
    """Both lists, against the words the problem is written in."""
    checked = 0
    for name, _index, need in ASKS:
        words = words_the_problem_uses(CONTEXTS[name])
        for field in ("variables", "confounders_required"):
            for spelt in need.get(field) or ():
                assert spelt in words, (name, field, spelt)
                checked += 1
    assert checked == 25, checked


def test_a_population_named_is_one_the_program_declares():
    """And one CHARACTERISED is a statement, which is not this rule's."""
    named = characterised = 0
    for name, _index, need in ASKS:
        population = need.get("population")
        if isinstance(population, str):
            assert population in _declared_populations(CONTEXTS[name]), name
            named += 1
        elif isinstance(population, dict):
            characterised += 1
    assert (named, characterised) == (16, 1), (named, characterised)


def test_the_one_count_written_twice_agrees():
    checked = 0
    for name, _index, need in ASKS:
        count = need.get("sampling_point_count")
        if count is None:
            continue
        said = need["precision_target"]["said"]
        assert float(count) == float(said["points"]), name
        checked += 1
    assert checked == 8, checked


# ------------------------------------------------------------------- teeth


def test_no_honest_answer_is_refused():
    for name, pair in SHAPES.items():
        verify_required_data(pair["result"], CONTEXTS[name])


def _leaves(node, trail=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{trail}.{key}" if trail else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{trail}.{index}")
    else:
        yield trail, node


def _set_at(node, dotted, value):
    steps = dotted.split(".")
    for step in steps[:-1]:
        node = node[int(step)] if isinstance(node, list) else node[step]
    if isinstance(node, list):
        node[int(steps[-1])] = value
    else:
        node[steps[-1]] = value


def _bend(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "_forged"
    if isinstance(value, list):
        return value[1:] if value else ["forged"]
    if isinstance(value, dict):
        return {**value, "forged": True}
    return "forged"


def test_a_bent_leaf_is_refused():
    """Every leaf of every data ask, bent one at a time."""
    held = free = 0
    for name, index, _need in ASKS:
        result = SHAPES[name]["result"]
        for where, value in _leaves(
                result["data_gap_report"]["gaps"][index]["required_data"]):
            bad = copy.deepcopy(result)
            _set_at(bad["data_gap_report"]["gaps"][index]["required_data"],
                    where, _bend(value))
            try:
                verify_required_data(bad, CONTEXTS[name])
            except VerificationError:
                held += 1
            else:
                free += 1
    assert (held, free) == (374, 453), (held, free)


def test_a_design_swapped_for_another_declared_one_is_refused():
    """The lie the vocabulary cannot catch, because both words are real.

    Naming a different design does not merely rename the number: the terms
    beside it stop fitting the formula that design is, so the ask claims a
    size nothing could have arrived at. Every swap between declared
    targets, on every ask that carries a size.
    """
    accepted = refused = 0
    for name, index, need in ASKS:
        if need.get("min_sample_size") is None:
            continue
        mine = str(need["precision_target"]["token"])
        for other in Precision:
            if str(other) == mine:
                continue
            bad = copy.deepcopy(SHAPES[name]["result"])
            ask = bad["data_gap_report"]["gaps"][index]["required_data"]
            ask["precision_target"]["token"] = str(other)
            try:
                verify_required_data(bad, CONTEXTS[name])
            except VerificationError:
                refused += 1
            else:
                accepted += 1
    assert (refused, accepted) == (804, 0), (refused, accepted)


def test_a_size_that_agrees_with_nothing_is_refused():
    """The lie the block's own terms catch: a number nobody could arrive at."""
    refused = 0
    for name, index, need in ASKS:
        if need.get("min_sample_size") is None:
            continue
        bad = copy.deepcopy(SHAPES[name]["result"])
        ask = bad["data_gap_report"]["gaps"][index]["required_data"]
        ask["min_sample_size"] = need["min_sample_size"] + 50
        with pytest.raises(VerificationError, match="wrong size"):
            verify_required_data(bad, CONTEXTS[name])
        refused += 1
    assert refused == 134, refused


def test_a_term_swapped_moves_the_number_it_was_sized_from():
    """The other direction: the size stands and the terms beneath it move.

    This is the edit that leaves a reader with a number that is right for
    a study nobody is proposing — and it is the one the sentence rule
    cannot see, since the sentence still has a fact for every hole.
    """
    refused = 0
    for name, index, need in ASKS:
        said = (need.get("precision_target") or {}).get("said") or {}
        if need.get("min_sample_size") is None or not said:
            continue
        key = sorted(said)[0]
        bad = copy.deepcopy(SHAPES[name]["result"])
        ask = bad["data_gap_report"]["gaps"][index]["required_data"]
        ask["precision_target"]["said"][key] = str(float(said[key]) * 2)
        try:
            verify_required_data(bad, CONTEXTS[name])
        except VerificationError:
            refused += 1
    assert refused == 134, refused


# --------------------------------------------------- the stated silences


def test_a_term_the_design_needs_and_nobody_stated_is_refused():
    """And the reason it is refused rather than passed over.

    Every one of the seven producers fills its slots where it states the
    target, so a design short of a term is claiming a number nothing could
    have arrived at. It is also the edit that would otherwise walk
    through — rename the design and its terms no longer fit any formula,
    which reads as "nothing to check" if the silence is spent here.
    Nothing else asks it: the statement carrier holds a token's facts
    against its holes and its table has no row for this block, which is a
    frontier of its own and not a reason for this rule to look away.
    """
    name, index, need = next(
        (n, i, d) for n, i, d in ASKS
        if d.get("min_sample_size") is not None
        and (d.get("precision_target") or {}).get("said"))
    bad = copy.deepcopy(SHAPES[name]["result"])
    ask = bad["data_gap_report"]["gaps"][index]["required_data"]
    ask["precision_target"]["said"] = {}
    with pytest.raises(VerificationError, match="states no"):
        verify_required_data(bad, CONTEXTS[name])


def test_a_design_this_build_has_no_arithmetic_for_says_nothing():
    """The one silence that stays, and why it cannot be spent otherwise.

    Which designs exist is declared in the output layer, and no verifier
    may import it — so a token this build has no formula for might be a
    member from another build as easily as a forgery, and refusing would
    reject an honest answer for having been produced elsewhere. What
    closes it is the statement carrier's table, which does not list this
    block; that is where the roster belongs, not here.
    """
    name, index, need = next(
        (n, i, d) for n, i, d in ASKS if d.get("min_sample_size") is not None)
    bad = copy.deepcopy(SHAPES[name]["result"])
    ask = bad["data_gap_report"]["gaps"][index]["required_data"]
    ask["precision_target"]["token"] = "a_design_from_another_build"
    verify_required_data(bad, CONTEXTS[name])


def test_which_kind_of_data_closes_a_gap_is_not_held():
    """Said as a number so a later rule can see what closing it buys.

    Which shape of data a gap needs is chosen where the gap is raised, and
    nothing declares a relation between it and anything else on the
    envelope. A table from gap kinds to data types would be this package
    restating a producer's judgement.
    """
    accepted = 0
    for name, index, need in ASKS:
        if "data_type" not in need:
            continue
        bad = copy.deepcopy(SHAPES[name]["result"])
        ask = bad["data_gap_report"]["gaps"][index]["required_data"]
        ask["data_type"] = "cohort" if need["data_type"] != "cohort" else "ipd"
        verify_required_data(bad, CONTEXTS[name])
        accepted += 1
    assert accepted == 135, accepted
