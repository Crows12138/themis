"""A restriction on a collider is told when it is one, and only then.

Two caveats tell a reader that an effect was estimated inside a restricted
sample and that the restriction is on a collider, so the estimate carries
selection bias: ``collider_conditioning_opens_backdoor`` when the question
conditions on it, ``selection_on_collider_opens_path`` when an observation
restricts the data. Which answers carry one was decided by the report's
author alone.

Measured on the corpus before anything was written. Each of its 7 such
caveats, removed, was accepted by every door; a caveat added for a given or
observed atom that is no collider, placed where its severity and kind sort
it, was accepted 5 times of 5; the value a selection caveat names, changed,
3 of 3.

Which caveats are owed is a fact about the program, the question and the
ground graph with its bidirected edges, so the audit states it once and
holds the report to it both ways. On every corpus answer the two are equal.

What a report writes was read off each caveat's description, and a caveat
gap says it in three places: the description, the gap's own occasion, and
the ways past that name the collider. The other two took any variable the
problem has, and the selection caveat's value anything at all -- 46 such
rewrites passed every door, and a way past is what a reader acts on. Each
place now spells the caveat it tells, over the description's slots.
The parts of that statement the corpus never exercises -- an arm that is a
latent common cause, a conditioned descendant of a collider, a chain that
is no common effect -- each have a program, and so do the two programs
unrolled in time on which the producer read predicates until #631.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import kernel, language
from themis.verifier.data_gap_rules import verify_collider_caveats_are_owed
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures" /
                     "answer_shapes.json").read_text(encoding="utf-8"))
COLLIDER = "collider_conditioning_opens_backdoor"
SELECTION = "selection_on_collider_opens_path"
KINDS = (COLLIDER, SELECTION)
_RANK = {"blocking": 0, "important": 1, "informational": 2}
_OWED = "owes a caveat"
_UNOWED = "opens a path"


def _gaps(result):
    return (result.get("data_gap_report") or {}).get("gaps") or []


def _query(program, result):
    return next(st["query"] for st in program["statements"]
                if st.get("kind") == "query" and st.get("id") == result.get("query_id"))


def _without(result, k):
    bent = copy.deepcopy(result)
    _gaps(bent).pop(k)
    return bent


def _places_it_says(gap):
    yield from (s.get("said") or {} for s in gap.get("describes") or ())
    yield gap.get("said") or {}
    yield from (r.get("said") or {} for r in gap.get("alternative_paths") or ())


_TEMPLATE = {kind: next(g for p in SHAPES.values() for g in _gaps(p["result"])
                        if g.get("kind") == kind) for kind in KINDS}


def _with_a_caveat(result, kind, collider, value, intervention, target):
    """``result`` telling its reader that ``collider`` is one, in every place
    such a caveat says so, placed where the report sorts its gaps."""
    bent = copy.deepcopy(result)
    gap = copy.deepcopy(_TEMPLATE[kind])
    slots = {"collider": collider, "intervention": intervention,
             "target": target, "value": value}
    for place in _places_it_says(gap):
        for slot in set(place) & set(slots):
            place[slot] = slots[slot]
    for ref in gap.get("provenance") or ():
        ref["ref_id"] = (f"{ref['ref_id'].split(':', 1)[0]}:"
                         f"{collider}|{intervention}->{target}")
    gaps = bent["data_gap_report"]["gaps"]
    key = (_RANK[gap["severity"]], gap["kind"])
    gaps.insert(sum(1 for g in gaps if (_RANK[g["severity"]], g["kind"]) <= key), gap)
    return bent


def _said(value):
    return language.capped(language.symbols(value))


REMOVALS = [pytest.param(name, k, id=f"{name}-{gap['kind']}")
            for name in sorted(SHAPES)
            for k, gap in enumerate(_gaps(SHAPES[name]["result"]))
            if gap.get("kind") in KINDS]

FLIPS = [pytest.param(name, k, id=name) for name, k in (p.values for p in REMOVALS)
         if _gaps(SHAPES[name]["result"])[k]["kind"] == SELECTION]


def _elsewhere(gap):
    """The places a caveat gap says it besides its description."""
    yield "occasion", gap.get("said") or {}
    for i, route in enumerate(gap.get("alternative_paths") or ()):
        yield f"alternative_paths.{i}", route.get("said") or {}


def _at_place(gap, where):
    if where == "occasion":
        return gap["said"]
    return gap["alternative_paths"][int(where.split(".")[1])]["said"]


RESTATED = [pytest.param(name, k, where, slot, id=f"{name}-{where}-{slot}")
            for name, k in (p.values for p in REMOVALS)
            for where, said in _elsewhere(_gaps(SHAPES[name]["result"])[k])
            for slot in ("collider", "value") if slot in said]


def _restrictions(program, result):
    query = _query(program, result)
    for item in query.get("given") or ():
        yield COLLIDER, item["atom"]["predicate"], None
    for statement in program["statements"]:
        if statement.get("kind") == "observation":
            yield SELECTION, statement["atom"]["predicate"], _said(statement["value"])


ADDITIONS = [
    pytest.param(name, kind, collider, value, id=f"{name}-{kind}-{collider}")
    for name in sorted(SHAPES)
    if SHAPES[name]["result"].get("query_kind") == "effect"
    and SHAPES[name]["result"].get("data_gap_report") is not None
    and not any(g.get("kind") in KINDS for g in _gaps(SHAPES[name]["result"]))
    for kind, collider, value in _restrictions(SHAPES[name]["program"],
                                               SHAPES[name]["result"])
]


# ------------------------------------------------- the fact this rests on


def test_on_every_corpus_answer_the_caveats_owed_are_the_ones_written():
    for name in sorted(SHAPES):
        program, result = SHAPES[name]["program"], SHAPES[name]["result"]
        _ast, prog, _query_stmt, ctx = kernel._premises_of(program, result)
        verify_collider_caveats_are_owed(result, prog, ctx)


def test_the_measured_sizes():
    assert (len(REMOVALS), len(ADDITIONS), len(FLIPS), len(RESTATED)) == (
        7, 5, 3, 30), (len(REMOVALS), len(ADDITIONS), len(FLIPS), len(RESTATED))


def test_the_forgeries_start_from_answers_their_door_reads():
    for name in sorted({p.values[0] for p in REMOVALS + ADDITIONS}):
        program, result = SHAPES[name]["program"], SHAPES[name]["result"]
        the_door_for(result)(program, result)


# ------------------------------------------------------------ both ways


@pytest.mark.parametrize(("name", "k"), REMOVALS)
def test_a_caveat_the_answer_owes_may_not_be_removed(name, k):
    program = SHAPES[name]["program"]
    bent = _without(SHAPES[name]["result"], k)
    with pytest.raises(VerificationError, match=_OWED):
        the_door_for(bent)(program, bent)


@pytest.mark.parametrize(("name", "kind", "collider", "value"), ADDITIONS)
def test_a_caveat_the_answer_does_not_owe_may_not_be_added(name, kind, collider, value):
    program, result = SHAPES[name]["program"], SHAPES[name]["result"]
    query = _query(program, result)
    bent = _with_a_caveat(result, kind, collider, value,
                          query["intervention"]["atom"]["predicate"],
                          query["target"]["atom"]["predicate"])
    with pytest.raises(VerificationError, match=_UNOWED):
        the_door_for(bent)(program, bent)


@pytest.mark.parametrize(("name", "k"), FLIPS)
def test_the_value_a_sample_is_restricted_to_is_the_one_observed(name, k):
    program = SHAPES[name]["program"]
    bent = copy.deepcopy(SHAPES[name]["result"])
    for place in _places_it_says(_gaps(bent)[k]):
        if "value" in place:
            place["value"] = "False"
    with pytest.raises(VerificationError, match=_OWED):
        the_door_for(bent)(program, bent)


@pytest.mark.parametrize(("name", "k", "where", "slot"), RESTATED)
def test_a_caveat_is_the_same_caveat_everywhere_its_gap_says_it(
        name, k, where, slot):
    """One place rewritten, the description left alone: the caveat that
    place now tells is one nothing owes."""
    program, result = SHAPES[name]["program"], SHAPES[name]["result"]
    bent = copy.deepcopy(result)
    said = _at_place(_gaps(bent)[k], where)
    if slot == "value":
        said[slot] = "True" if said[slot] == "False" else "False"
    else:
        said[slot] = _query(program, result)["intervention"]["atom"]["predicate"]
    with pytest.raises(VerificationError, match=_UNOWED):
        the_door_for(bent)(program, bent)


def test_an_answer_owing_a_caveat_may_not_drop_the_report():
    name = REMOVALS[0].values[0]
    program = SHAPES[name]["program"]
    bent = copy.deepcopy(SHAPES[name]["result"])
    del bent["data_gap_report"]
    _ast, prog, _query_stmt, ctx = kernel._premises_of(program, bent)
    with pytest.raises(VerificationError, match=_OWED):
        verify_collider_caveats_are_owed(bent, prog, ctx)


# ------------------------------------------ the parts the corpus never needs

_ME = [{"type": "const", "name": "me"}]


def _at(predicate, t=None):
    atom = {"predicate": predicate, "args": _ME}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _asked(causes, x, y, w, restricted_by, bidirected=()):
    """The effect of ``x`` on ``y``, the sample restricted to ``w`` by the
    question's ``given`` or by an observation."""
    names = sorted({a["predicate"] for edge in (*causes, *bidirected) for a in edge})
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in names]
    statements += [{"kind": "cause", "from": a, "to": b} for a, b in causes]
    statements += [{"kind": "bidirected", "left": a, "right": b} for a, b in bidirected]
    given = []
    if restricted_by == "given":
        given = [{"atom": w, "value": True}]
    else:
        statements.append({"kind": "observation", "atom": w, "value": True})
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": given,
        "intervention": {"atom": x, "value": True},
        "target": {"atom": y, "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _kind(restricted_by):
    return COLLIDER if restricted_by == "given" else SELECTION


def _latent_arms(restricted_by):
    return _asked(((_at("x"), _at("y")),), _at("x"), _at("y"), _at("w"),
                  restricted_by, bidirected=((_at("x"), _at("w")), (_at("w"), _at("y"))))


def _below_a_collider(restricted_by):
    return _asked(((_at("x"), _at("y")), (_at("x"), _at("c")), (_at("y"), _at("c")),
                   (_at("c"), _at("d"))), _at("x"), _at("y"), _at("d"), restricted_by)


def _a_chain(restricted_by):
    return _asked(((_at("x"), _at("y")), (_at("y"), _at("w"))),
                  _at("x"), _at("y"), _at("w"), restricted_by)


def _unrolled_under_the_intervention_s_name(restricted_by):
    """``x`` now is moved by ``x`` a step back and by ``y`` now."""
    return _asked(((_at("x", -1), _at("y", 0)), (_at("x", -1), _at("x", 0)),
                   (_at("y", 0), _at("x", 0))),
                  _at("x", -1), _at("y", 0), _at("x", 0), restricted_by)


def _unrolled_no_ground_path(restricted_by):
    """Over predicates ``x -> w <- y``; ``w`` a step back is moved by ``y`` a
    step back alone."""
    return _asked(((_at("x", -1), _at("y", 0)), (_at("x", -1), _at("w", 0)),
                   (_at("y", -1), _at("w", -1))),
                  _at("x", -1), _at("y", 0), _at("w", -1), restricted_by)


OWED = {
    # x <-> w <-> y: conditioning opens a path whose arms are latent.
    "latent_arms/given": lambda: _latent_arms("given"),
    # x -> c <- y, c -> d: conditioning on d activates c.
    "below_a_collider/given": lambda: _below_a_collider("given"),
    "below_a_collider/observation": lambda: _below_a_collider("observation"),
    # Under the intervention's own predicate, a step apart.
    "unrolled_under_the_intervention_s_name/given":
        lambda: _unrolled_under_the_intervention_s_name("given"),
    "unrolled_under_the_intervention_s_name/observation":
        lambda: _unrolled_under_the_intervention_s_name("observation"),
}

NOT_OWED = {
    # x -> y -> w reaches w from x only through y: no common effect.
    "a_chain/given": (lambda: _a_chain("given"), "w"),
    "a_chain/observation": (lambda: _a_chain("observation"), "w"),
    # A restriction is a common effect by directed paths; latent arms are not.
    "latent_arms/observation": (lambda: _latent_arms("observation"), "w"),
    "unrolled_no_ground_path/given": (lambda: _unrolled_no_ground_path("given"), "w"),
    "unrolled_no_ground_path/observation":
        (lambda: _unrolled_no_ground_path("observation"), "w"),
}


def _answer(program):
    return next(r for r in themis.run(program)["results"] if r.get("query_id") == "q")


@pytest.mark.parametrize("case", sorted(OWED))
def test_each_caveat_a_program_owes_is_held_there(case):
    program = OWED[case]()
    result = _answer(program)
    the_door_for(result)(program, result)
    owed = [k for k, gap in enumerate(_gaps(result))
            if gap.get("kind") == _kind(case.split("/")[1])]
    assert owed, "the program has to owe a caveat for this to ask anything"
    for k in owed:
        bent = _without(result, k)
        with pytest.raises(VerificationError, match=_OWED):
            the_door_for(bent)(program, bent)


@pytest.mark.parametrize("case", sorted(NOT_OWED))
def test_a_restriction_that_is_no_collider_owes_nothing(case):
    build, restricted = NOT_OWED[case]
    program = build()
    result = _answer(program)
    kind = _kind(case.split("/")[1])
    assert not [gap for gap in _gaps(result) if gap.get("kind") == kind]
    the_door_for(result)(program, result)
    bent = _with_a_caveat(result, kind, restricted,
                          None if kind == COLLIDER else "True", "x", "y")
    with pytest.raises(VerificationError, match=_UNOWED):
        the_door_for(bent)(program, bent)
