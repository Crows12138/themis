"""The condition a decomposition names is one the graph decides.

A mediation block that reports no identification names the condition that
stopped it -- ``M1`` to ``M4`` for the natural effects, ``C1`` or ``C2``
for the controlled one. The audit checked that a condition is named
exactly when one failed and stopped there, on an argument written into
two docstrings: the label belongs to the candidate that got FURTHEST
along a fixed order, which is a property of the SEARCH and not of the
graph, so a verifier recomputing it would be transcribing the producer's
policy and agreeing by construction.

Read against the producer, the argument does not hold.
``structural_solver._search_mediation_adjustment`` keeps
``if order.index(failure) > rank: furthest = failure`` -- a maximum over
the candidate SET, and no order of walking a set changes a maximum. The
"fixed order" the argument names is the order of the CONDITIONS, which
the schema enumerates as its own vocabulary. What IS a producer policy is
the size cap on the candidate pool, and it decides nothing on this corpus:
every pool here is smaller than the cap.

Underneath that was the reason the label looked unreachable. The
conditions are asked TWICE in this verifier. A step rule answered each of
them and named every one that failed; the envelope's audit asked the same
questions in the same order and returned a bool, so the label the row
makes a claim out of had been computed already -- in the copy that is not
the one reading the row. They are asked in one place now, and each reader
takes the half it needs: all-of-them for the step, the first that failed
for the envelope.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib
from itertools import combinations

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis import kernel
from themis.verifier import verify as _verify_module
from themis.verifier.rules import (
    _verifier_first_condition_that_failed,
    _verifier_mediation_cde_asker,
    _verifier_mediation_nde_asker,
    _verifier_nodes_by_label,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))

BLOCKS = ("mediation_decomposition", "mediation_joint_decomposition")

#: Every label the contract admits, read from the schema rather than
#: listed here: a lie inside the vocabulary is the one worth bending to,
#: and a list kept beside the schema is a second vocabulary.
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json")
    .read_text("utf-8"))


def _rows():
    for name in sorted(SHAPES):
        pair = SHAPES[name]
        extensions = pair["result"].get("extensions") or {}
        for block_name in BLOCKS:
            block = extensions.get(block_name)
            if isinstance(block, dict):
                yield name, block_name, pair


ROWS = tuple(_rows())
CARRYING = tuple(sorted({name for name, _, _ in ROWS}))

#: The (answer, block, arm) triples that report a failure -- the only
#: places a label exists to be bent.
NAMING = tuple(
    (name, block_name, arm)
    for name, block_name, pair in ROWS
    for arm in ("nde_nie", "cde")
    if isinstance(
        ((pair["result"]["extensions"][block_name] or {}).get(arm)), dict)
    and (pair["result"]["extensions"][block_name][arm]
         .get("failed_condition")) is not None
)


def _premises(pair):
    """The graph, query and mediators the rule itself would build."""
    _ast, _prog, qs, ctx = kernel._premises_of(
        json.loads(json.dumps(pair["program"])), pair["result"])
    return qs.query, ctx


def _parts(pair, block):
    query, ctx = _premises(pair)
    label = _verifier_nodes_by_label(ctx.graph)
    stated = block.get("mediators")
    if stated is None:
        stated = [block.get("mediator")]
    mediators = frozenset(label[s] for s in stated if s in label)
    x = query.intervention.atom
    y = getattr(query.target, "atom", query.target)
    stratum = frozenset(getattr(g, "atom", g)
                        for g in (getattr(query, "given", ()) or ()))
    pool = [n for n in ctx.graph.nodes
            if n != x and n != y and n not in mediators and n not in stratum]
    return ctx, query, x, y, mediators, stratum, pool


# ------------------------------------------------------------- the census


def test_the_corpus_carries_what_this_file_is_about():
    """Thirteen blocks, and two arms in them that name a condition.

    Pinned because the sweep below is over the second number: a corpus
    that stopped carrying a non-identifiable arm would leave this file
    passing and asking nothing.
    """
    assert len(ROWS) == 13
    assert len(CARRYING) == 13
    assert len(NAMING) == 2
    for name, block_name, arm in NAMING:
        attempt = SHAPES[name]["result"]["extensions"][block_name][arm]
        assert attempt.get("identifiable") is False
        assert attempt["failed_condition"] == "M1"


def test_the_vocabulary_is_the_schemas_and_has_more_than_one_entry():
    """A bend inside the vocabulary is the interesting one, so the
    vocabulary has to come from the contract rather than from here."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("enum"), list) \
                    and "M1" in node["enum"]:
                found.append(node["enum"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(SCHEMA)
    assert found, "the schema no longer enumerates the condition labels"
    for enum in found:
        assert {"M1", "M2", "M3", "M4"} <= set(enum), enum


# ------------------------------------------------------- the honest direction


@pytest.mark.parametrize("name", CARRYING)
def test_every_stored_answer_still_passes(name):
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


@pytest.mark.parametrize(
    "name,block_name,arm,lie",
    [(n, b, a, lie) for n, b, a in NAMING
     for lie in ("M2", "M3", "M4")],
    ids=[f"{n[:28]}:{a}:{lie}" for n, _b, a in NAMING
         for lie in ("M2", "M3", "M4")])
def test_a_label_inside_the_vocabulary_is_refused(name, block_name, arm, lie):
    """The bend the old check could not see.

    ``null`` was already held, because a condition is named exactly when
    one failed. Every other entry of the vocabulary went through.
    """
    pair = SHAPES[name]
    forged = copy.deepcopy(pair["result"])
    forged["extensions"][block_name][arm]["failed_condition"] = lie
    door = the_door_for(forged)
    with pytest.raises(Exception):
        door(pair["program"], forged)


# ---------------------------------------------- one transcription, two readers


def test_the_conditions_are_asked_in_one_place():
    """Two readers, one set of questions.

    The step rule used to build its own mutilated graphs and its own four
    separations, and the envelope's audit built the same ones beside it.
    An AST scan rather than a promise: a second copy is easy to add back
    and impossible to notice.
    """
    from themis.verifier import rules as _rules

    step_source = inspect.getsource(_rules._rule_mediation_nde_nie_check)
    step_source += inspect.getsource(_rules._rule_mediation_cde_check)
    route_source = inspect.getsource(
        _verify_module.verify_mediation_decomposition)
    for source in (step_source, route_source):
        assert "remove_edges_from" not in source
        assert "_verifier_is_m_connected" not in source
    assert "_verifier_mediation_nde_asker" in step_source
    assert "_verifier_mediation_cde_asker" in step_source
    assert "_verifier_mediation_nde_asker" in route_source
    assert "_verifier_mediation_cde_asker" in route_source


def test_the_order_the_conditions_are_named_in_is_the_order_they_are_asked():
    """No second list saying what the order is.

    The producer's ``_NDE_ORDER`` and ``_CDE_ORDER`` are its own, and a
    copy of them here would be a name that can drift from the questions.
    The answers arrive in order, so the order is read off them.
    """
    name, block_name, pair = ROWS[0]
    ctx, _query, x, y, mediators, stratum, _pool = _parts(
        pair, pair["result"]["extensions"][block_name])
    nde = _verifier_mediation_nde_asker(
        ctx.graph, frozenset(ctx.bidirected or ()), x, y, mediators)
    cde = _verifier_mediation_cde_asker(
        ctx.graph, frozenset(ctx.bidirected or ()), x, y, mediators)
    assert list(nde(stratum)) == ["M1", "M2", "M3", "M4"]
    assert list(cde(stratum)) == ["C1", "C2"]

    from themis.runtime import structural_solver

    assert list(structural_solver._NDE_NIE_ORDER) == list(nde(stratum))
    assert list(structural_solver._CDE_ORDER) == list(cde(stratum))


def test_a_bool_is_the_degenerate_reading_of_the_same_answers():
    """Admissibility and the label are one reading of one mapping, so
    they cannot disagree about the same candidate."""
    for answers in ({"M1": True, "M2": True},
                    {"M1": True, "M2": False, "M3": True},
                    {"C1": False, "C2": False}):
        first = _verifier_first_condition_that_failed(answers)
        assert (first is None) == all(answers.values())
        if first is not None:
            assert answers[first] is False


# ------------------------------------------------- the re-derivation itself


@pytest.mark.parametrize("name,block_name,arm", NAMING,
                         ids=[f"{n[:32]}:{a}" for n, _b, a in NAMING])
def test_the_label_is_the_furthest_any_candidate_gets(name, block_name, arm):
    """Recomputed here the way the rule recomputes it, and compared with
    what the row says -- the identity the frontier rests on."""
    pair = SHAPES[name]
    block = pair["result"]["extensions"][block_name]
    ctx, _query, x, y, mediators, stratum, pool = _parts(pair, block)
    bidir = frozenset(ctx.bidirected or ())
    ask = (_verifier_mediation_nde_asker if arm == "nde_nie"
           else _verifier_mediation_cde_asker)(
        ctx.graph, bidir, x, y, mediators)
    order = list(ask(stratum))

    furthest, rank = None, -1
    for size in range(len(pool) + 1):
        for combo in combinations(pool, size):
            stopped = _verifier_first_condition_that_failed(
                ask(frozenset(combo) | stratum))
            assert stopped is not None, (
                "a candidate identifies the quantity the row calls "
                "non-identifiable")
            if order.index(stopped) > rank:
                furthest, rank = stopped, order.index(stopped)

    assert furthest == block[arm]["failed_condition"]


def test_the_producers_size_cap_decides_nothing_on_this_corpus():
    """The one policy number in the producer's search, measured.

    The producer enumerates candidates up to ``max_adjustment_size``;
    this audit enumerates the whole pool, the way its own
    negative-claim search already did. The two agree wherever the pool
    is no larger than the cap, and here every pool is smaller.
    """
    from themis.runtime.structural_solver import mediation_sets

    cap = inspect.signature(
        mediation_sets).parameters["max_adjustment_size"].default
    assert isinstance(cap, int) and cap >= 1
    sizes = []
    for _name, block_name, pair in ROWS:
        block = pair["result"]["extensions"][block_name]
        _ctx, _query, _x, _y, _m, _stratum, pool = _parts(pair, block)
        sizes.append(len(pool))
    assert sizes, "no pools measured"
    assert max(sizes) < cap, sorted(sizes)
