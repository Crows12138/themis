"""What the cascade took the query away from, said by the cascade.

Two rows can claim one query. Precedence settles who answers; nothing
settled whether the reader hears that someone else would have. The
disclosure existed for one pair and was rebuilt downstream from which
extension came back empty — an inference from residue, so it could see
only the pair it was written for and would misread a layer that fills its
extension and then fails.

The declaration now lives on the route, and this module holds the two
halves that a declaration alone cannot: that every pair which CAN occur is
declared (the shape band is enumerable, so this is a proof rather than a
sample), and that the table says no to a displacement nobody could act on.
"""
from __future__ import annotations

import itertools
import json
import pathlib

import pytest

import themis
from themis import routing
from themis.output import data_gap_report
from themis.types import DispatchRecord
from themis import gaps as _gaps

CASES = pathlib.Path(themis.__file__).resolve().parent.parent / "docs" / "l3_simulation"

_KIND = "unattempted_layer_due_to_dispatch_conflict"


# --- the declarations agree with each other ---------------------------------

def _declared_pairs() -> set[tuple[str, str]]:
    return {
        (r.id, target)
        for r in routing.EFFECT_ROUTES
        for target in r.displaces
    }


def test_every_declared_displacement_has_a_sentence():
    """A pair declared in the table and missing here reaches the reader as
    a gap with a hole in the middle of its description."""
    assert _declared_pairs() == set(data_gap_report._DISPLACED_BECAUSE)


# --- the shape band is enumerable, so co-firing is decidable ----------------
#
# Guards below precedence 50 run the structural solver. The ones at or
# above it read the query and nothing else, which is what makes the
# question "can these two hold at once" answerable by enumeration rather
# than by inspection. Which routes those are is not listed here: a guard
# that reaches for anything else raises on the stub below, and that is the
# classification.

class _Query:
    def __init__(self, declared: frozenset[str]) -> None:
        self.extra_interventions = (
            ("do(b)",) if "extra_interventions" in declared else ()
        )
        self.target_population = (
            "clinic" if "target_population" in declared else None
        )
        self.mediators = ("m",) if "mediators" in declared else ()
        self.mediator = "m" if "mediator" in declared else None


class _Blind:
    """Facts that can answer the query-shape questions and nothing else.

    Reaching for an adjustment set raises instead of being solved, which
    is both how a non-shape guard is recognised and the reason the real
    dispatcher may not evaluate one speculatively.
    """

    def __init__(self, declared: frozenset[str]) -> None:
        self.query = _Query(declared)
        self.declares_longitudinal = "options.longitudinal" in declared


DECLARATIONS = frozenset({
    "options.longitudinal",
    "extra_interventions",
    "target_population",
    "mediators",
    "mediator",
})


def _shape_routes() -> tuple[routing.Route, ...]:
    out = []
    for r in routing.EFFECT_ROUTES:
        try:
            r.applies_when(_Blind(DECLARATIONS))
        except AttributeError:
            continue
        out.append(r)
    return tuple(out)


def _fires(declared: frozenset[str]) -> tuple[str, ...]:
    facts = _Blind(declared)
    return tuple(r.id for r in _shape_routes() if r.applies_when(facts))


def test_the_shape_band_is_exactly_the_routes_that_name_a_declaration():
    """The stub classifies; this pins that the classification and
    ``triggered_by`` describe the same set, so a shape route added without
    naming its declaration cannot slip past the enumeration below."""
    assert {r.triggered_by for r in _shape_routes()} == DECLARATIONS


@pytest.mark.parametrize("declaration", sorted(DECLARATIONS))
def test_one_declaration_fires_exactly_the_route_that_names_it(declaration):
    """``triggered_by`` is read by the disclosure to say which declaration
    to remove. It restates the guard, so it is held to it."""
    assert _fires(frozenset({declaration})) == (
        next(r.id for r in _shape_routes() if r.triggered_by == declaration),
    )


def _co_firing() -> set[tuple[str, str]]:
    """Every ordered (winner, loser) pair reachable by some query shape."""
    by_precedence = {r.id: r.precedence for r in _shape_routes()}
    pairs: set[tuple[str, str]] = set()
    for size in range(2, len(DECLARATIONS) + 1):
        for combo in itertools.combinations(sorted(DECLARATIONS), size):
            fired = _fires(frozenset(combo))
            for a, b in itertools.combinations(fired, 2):
                if by_precedence[a] < by_precedence[b]:
                    pairs.add((a, b))
                else:
                    pairs.add((b, a))
    return pairs


def test_every_reachable_displacement_is_declared():
    """The gate. A shape route that can co-fire with another and does not
    declare it is a layer dropped in silence — which is what this whole
    mechanism exists to make undeclarable rather than merely unlikely.

    Scoped to winners the enumeration can reach, which is what it could
    always prove and not what it used to assert. A guard that consults the
    graph is not in the shape band and its co-firings are not decidable
    from four booleans; asserting equality over those too would report a
    declared-and-reachable pair as declared-and-unreachable, which is the
    opposite of what this gate is for. The rows such a winner displaces
    are still held to something, below.
    """
    shape = {r.id for r in _shape_routes()}
    assert _co_firing() == {
        pair for pair in _declared_pairs() if pair[0] in shape
    }


def test_a_displacement_from_outside_the_shape_band_names_shape_rows():
    """What is checkable about the other half.

    ``displaced_by`` evaluates the LOSERS' guards at the moment a winner
    is picked, and the dispatcher may not run the structural solver
    speculatively — so a row displaced by anyone has to be one whose guard
    reads the query and nothing else. That holds however the winner was
    reached, and it is the property the mechanism needs.
    """
    shape = {r.id for r in _shape_routes()}
    outside = {pair for pair in _declared_pairs() if pair[0] not in shape}
    assert outside, "no route outside the shape band declares a displacement"
    assert {loser for _winner, loser in outside} <= shape


def test_the_enumeration_finds_the_pair_the_old_classifier_covered():
    """A guard against the enumeration silently going empty: if the stub
    stopped classifying anything as a shape route, every assertion above
    would pass on two empty sets."""
    assert ("transport", "mediation_single") in _co_firing()
    assert len(_shape_routes()) == 5


# --- the table refuses a displacement nobody could act on -------------------

def _route(rid, precedence, *, ends=routing.BOTH, triggered_by="f", displaces=()):
    return routing.Route(
        id=rid,
        precedence=precedence,
        applies_when=lambda f: True,
        ends=ends,
        triggered_by=triggered_by,
        displaces=frozenset(displaces),
    )


def test_displacing_an_unknown_route_is_refused():
    with pytest.raises(ValueError, match="displaces unknown route"):
        routing._check((_route("a", 10, displaces=("ghost",)),))


def test_displacing_a_route_that_outranks_you_is_refused():
    """Displacement is downward by definition: the cascade never offers the
    query to a row it already passed."""
    with pytest.raises(ValueError, match="which outranks it"):
        routing._check((
            _route("a", 10),
            _route("b", 20, displaces=("a",)),
        ))


def test_displacing_a_single_ended_route_is_refused():
    """The displaced route's guard is evaluated by whichever layer
    answered. A route only one layer can evaluate would raise in the
    other, so the declaration is refused rather than the raise deferred."""
    with pytest.raises(ValueError, match="declares only"):
        routing._check((
            _route("a", 10, displaces=("b",)),
            _route("b", 20, ends=routing.ESTIMATES),
        ))


@pytest.mark.parametrize("blank", ["winner", "loser"])
def test_a_displacement_neither_side_can_name_is_refused(blank):
    """The disclosure has to say which declaration to remove to get the
    other layer. Without ``triggered_by`` on both sides there is no such
    sentence, so the pair cannot be declared."""
    with pytest.raises(ValueError, match="names no triggered_by"):
        routing._check((
            _route("a", 10, triggered_by="" if blank == "winner" else "f",
                   displaces=("b",)),
            _route("b", 20, triggered_by="" if blank == "loser" else "g"),
        ))


# --- the record, and what reads it ------------------------------------------

def _load(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def _run_first(program: dict) -> dict:
    return themis.run(program)["results"][0]


def _kinds(result: dict) -> list[str]:
    report = result.get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", ())]


def _conflicts(result: dict) -> list[dict]:
    report = result.get("data_gap_report") or {}
    return [g for g in report.get("gaps", ()) if g["kind"] == _KIND]


def test_the_dispatcher_records_who_answered_and_whom_it_displaced():
    """The identification layer's own record, before any renderer sees it."""
    from themis import kernel

    prog = kernel.validate_program(
        kernel.validate_ast(_load("case_009_mediation_x_transport.json"))
    )
    results = kernel.dispatch_all(prog, kernel.project(kernel.instantiate(prog)))
    dispatched = [r for r in results if r.dispatch is not None]
    assert dispatched, "no effect query in case 009 reached a route"
    record = dispatched[0].dispatch
    assert record.answered_by == "transport"
    assert record.displaced == ("mediation_single",)


def test_the_estimation_cascade_keeps_the_same_record():
    """Both layers call the same :func:`routing.displaced_by`, so they
    cannot disagree about WHICH rows were displaced. What they could
    disagree about is whether either of them asks — and the estimation
    cascade is where the question was previously unanswerable: it stops at
    the winner, so the rows below are in neither ``considered`` nor
    anywhere else, while ``considered`` claims to explain reachability."""
    from themis.estimation.claim import answered
    from themis.estimation.strategy import (
        Estimand, Role, Strategy, check_table, run_cascade,
    )

    class _Facts:
        query = _Query(frozenset({"target_population", "mediator"}))

    table = check_table((
        Strategy(
            route=routing.Route(
                id="transport", precedence=30, applies_when=lambda f: True,
                ends=routing.ESTIMATES, triggered_by="target_population",
                displaces=frozenset({"mediation_single"}),
            ),
            role=Role.CLAIM, produces=Estimand.TRANSPORTED_EFFECT,
            run=lambda f, r, k: answered(),
        ),
    ))
    ev = run_cascade(table, _Facts(), {}, None, query_id="q1")
    assert ev.displaced == ("mediation_single",)


def test_a_mediator_block_and_a_single_mediator_now_disclose_the_skip():
    """A pair the residue-reading classifier could not see: both fields are
    mediation, so the only extension it consulted comes back populated
    either way and it inferred no conflict."""
    program = _load("case_006_smoking_birthweight_mediation.json")
    touched = False
    for stmt in program["statements"]:
        q = stmt.get("query") if stmt.get("kind") == "query" else None
        if q and q.get("mediator") is not None:
            q["mediators"] = [q["mediator"]]
            touched = True
    assert touched, "premise: case 006 names a single mediator"

    conflicts = _conflicts(_run_first(program))
    assert len(conflicts) == 1
    gap = conflicts[0]
    assert "`mediators`" in _gaps.described(gap)
    assert "`mediator`" in _gaps.described(gap)
    assert gap["severity"] == "important"


def test_transport_displaces_a_mediator_block_as_readily_as_a_lone_one():
    program = _load("case_009_mediation_x_transport.json")
    for stmt in program["statements"]:
        q = stmt.get("query") if stmt.get("kind") == "query" else None
        if q and q.get("mediator") is not None:
            q["mediators"] = [q.pop("mediator")]

    gap = _conflicts(_run_first(program))[0]
    assert "mediation_joint" in _gaps.described(gap)
    assert "`mediators`" in _gaps.described(gap)


def test_a_single_layer_query_discloses_nothing():
    for case in (
        "case_006_smoking_birthweight_mediation.json",
        "case_007_statin_transport.json",
    ):
        assert _KIND not in _kinds(_run_first(_load(case)))


def test_the_disclosure_no_longer_depends_on_an_empty_extension():
    """The residue reading fired only when exactly one of the two
    extensions was populated; with both populated it concluded there was
    no conflict. The record does not consult them at all."""
    from themis import blocks

    report = data_gap_report.compute_data_gap_report(
        query_kind=themis.types.QueryKind.EFFECT,
        status=themis.types.ResultStatus.STRUCTURALLY_SOLVED,
        extensions={
            blocks.Block.TRANSPORT_IDENTIFICATION: {"transportable": True},
            blocks.Block.MEDIATION_DECOMPOSITION: {"mediator_valid": True},
        },
        dispatch=DispatchRecord(
            answered_by="transport", displaced=("mediation_single",),
        ),
    )
    assert report is not None
    assert _KIND in [g.kind.value for g in report.gaps]
