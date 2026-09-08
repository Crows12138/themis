"""What a gap tells a reader to go and do, held to the gap it is.

``alternative_paths[].route`` is the field a reader ACTS on. It was typed
at 84 construction sites and declared for three species
(:data:`themis.gaps.ESCAPES`, which answers one level finer, by species
rather than by kind). Nothing anywhere asked whether a route belonged to
the gap offering it: swapping one for any of the other 84 the kernel
names left 63 unrefused on a measured gap. The 21 refusals came from
``statement_rules._CARRIERS``, which asks whether the slots a sentence
names are the ones filled in beside it — so any two routes with the same
slot signature were interchangeable, and a gap could tell a reader to go
and find an instrument where the honest way past was to measure the
confounder and identify again.

The declaration is a CEILING and says so: which of a species' ways past
this occasion offers is the renderer's decision, and a table answering
that would be the renderer's branches written a second time. So two ways
past of the SAME species stay interchangeable here. That is the gate's
reach, measured below rather than left to be discovered.

One route belongs to no species. A pass after identification knows which
intervals actually came out and replaces a promise of one with a pointer
at it, so ``bounds_already_computed`` is on a gap because of what the RUN
found. Where it may land is still derived rather than listed:
:attr:`themis.gaps.Route.answered_by` says which routes an interval can
stand in for, and the gap's own severity says whether it leads the answer.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis import gaps
from themis.gaps import Route
from themis.types import BoundsMethod, DataGap, GapKind
from themis.verifier import data_gap_rules
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

ALL_ROUTES = sorted(str(route) for route in Route)


def _results(envelope):
    return envelope.get("results") or [envelope]


def _door(result):
    return (themis.verify if result.get("derivation") is not None
            else themis.verify_answer_claims)


# --------------------------------------------- the declaration is complete


def test_every_species_says_which_ways_past_are_its_own_or_that_it_has_none():
    """The premise everything below rests on, asked of the enum rather
    than of the two tables: a species missing from both is one whose
    reader gets whatever advice its renderer happened to hold."""
    assert set(gaps.ROUTES_OF) | set(gaps.NO_WAY_PAST) == set(GapKind)
    assert not set(gaps.ROUTES_OF) & set(gaps.NO_WAY_PAST)
    assert all(routes for routes in gaps.ROUTES_OF.values())
    assert all(reason.strip() for reason in gaps.NO_WAY_PAST.values())


def test_the_finer_table_is_folded_in_rather_than_copied():
    """``ESCAPES`` settles routes per species and ``Need.gap`` says which
    kind each species is filed under, so what it settles is already
    settled here. A copy is how the coarse name came to disagree with the
    fine one in the first place."""
    for need, routes in gaps.ESCAPES.items():
        assert set(routes) <= gaps.ROUTES_OF[need.gap], need


def test_every_route_the_kernel_names_is_some_species_or_the_runs():
    """The other direction, which is the one #614 was about. A route no
    species offers is one no gap can carry, so every rule reading this
    table would refuse it wherever it was written — and two were, at
    sites the corpus does not reach: the Anderson-Rubin set that could
    not be constructed from this sample. Asking the table in one
    direction only would have shipped them as refusals."""
    offered = {route for routes in gaps.ROUTES_OF.values()
               for route in routes}
    assert offered | set(gaps.THE_RUN_SETTLES) == set(Route)


def test_no_species_claims_the_route_that_belongs_to_the_run():
    """A species declaring ``bounds_already_computed`` would be claiming
    to know, before the question was run, which intervals came out of
    it."""
    for kind, routes in gaps.ROUTES_OF.items():
        assert not set(routes) & set(gaps.THE_RUN_SETTLES), kind


def test_the_runs_own_route_is_admitted_by_a_condition_already_declared():
    """Not a second list of species. It leads a gap that blocks the
    answer, or replaces a route an interval can stand in for — and both
    of those are written down elsewhere already."""
    for kind, routes in gaps.ROUTES_OF.items():
        stands_in = any(route.answered_by for route in routes)
        assert (Route.BOUNDS_ALREADY_COMPUTED
                in gaps.ways_past(kind, blocking=True))
        assert ((Route.BOUNDS_ALREADY_COMPUTED
                 in gaps.ways_past(kind, blocking=False))
                is stands_in), kind


def test_a_species_with_no_way_past_still_takes_the_runs_pointer():
    """The condition reaches the twelve species that offer nothing, and
    it has to.

    Read the other way round, ``NO_WAY_PAST`` invites a reader to say
    that a species offering nothing should be offered nothing — and the
    pass after identification puts the pointer FIRST precisely where a
    gap promised no interval of its own, which is what a gap with no
    routes at all does. Tightening the permission to the species that
    have routes would refuse a report this repository produces.

    So the producer is asked here rather than described: what it returns
    for an empty offer is the pin.
    """
    computed = [m for m in BoundsMethod
                if m in Route.BOUNDS_ALREADY_COMPUTED.answered_by]
    assert computed, "the run's pointer stands in for no method at all"

    put = gaps.past_the_bounds_in_hand((), computed, blocking=True)
    assert put is not None and [str(a.route) for a in put] == [
        "bounds_already_computed"], put

    for kind in gaps.NO_WAY_PAST:
        assert not gaps.ways_past(kind, blocking=False), kind
        assert gaps.ways_past(kind, blocking=True) == frozenset(
            {Route.BOUNDS_ALREADY_COMPUTED}), kind

    blocks = GapKind.MISSING_POPULATION_DISTRIBUTION
    gap = DataGap(kind=blocks, describes=(), alternative_paths=tuple(put))
    assert [str(a.route) for a in gap.alternative_paths] == [
        "bounds_already_computed"]

    with pytest.raises(ValueError, match="declares no way past at all"):
        DataGap(kind=blocks, describes=(),
                alternative_paths=(gaps.route(Route.RUN_AN_E_VALUE),))


# ------------------------------------------------- the producer honours it


def test_a_gap_may_offer_a_way_past_its_species_declares():
    gap = DataGap(
        kind=GapKind.UNMEASURED_CONFOUNDER_RISK, describes=(),
        alternative_paths=(gaps.route(Route.RUN_AN_E_VALUE),),
    )
    assert [str(a.route) for a in gap.alternative_paths] == ["run_an_e_value"]


def test_a_gap_may_not_offer_another_species_way_past():
    """The forgery this whole gate is about, at the door it is built:
    advice that belongs to a different failure, on a gap that did not
    fail that way."""
    with pytest.raises(ValueError, match="does not declare as a way past"):
        DataGap(
            kind=GapKind.UNMEASURED_CONFOUNDER_RISK, describes=(),
            alternative_paths=(gaps.route(Route.SPLIT_THE_INTERVENTION_IN_TWO),
                               ),
        )


def test_a_species_with_no_way_past_is_refused_in_its_own_words():
    """The other side of the partition. The refusal quotes the reason the
    species gives, so that a site meeting it is told what to argue with
    rather than which table to edit."""
    with pytest.raises(ValueError, match="declares no way past at all"):
        DataGap(
            kind=GapKind.LOW_CONFIDENCE_INPUT_DATA, describes=(),
            alternative_paths=(gaps.route(Route.RUN_AN_E_VALUE),),
        )


def test_rewriting_a_gap_keeps_the_ways_past_it_already_had():
    """``dataclasses.replace`` re-enters the constructor, and three
    passes rewrite a gap after it is built."""
    from dataclasses import replace

    gap = DataGap(
        kind=GapKind.WEAK_IV_INSTRUMENT, describes=(),
        alternative_paths=(gaps.route(Route.FALL_BACK_TO_IV_BOUNDS),),
    )
    again = replace(gap, alternative_paths=(
        gaps.route(Route.BOUNDS_ALREADY_COMPUTED, methods="manski"),))
    assert [str(a.route) for a in again.alternative_paths] \
        == ["bounds_already_computed"]


# -------------------------------------------------- what the corpus offers


def test_no_answer_this_repository_produces_offers_a_stray_way_past():
    """The honest side, whole. A rule that refuses an answer the kernel
    itself writes is worse than the hole it closes, so the sweep runs
    before the numbers below mean anything.

    Pinned at what it measures, because a sweep that quietly covers less
    each round is a sweep that stops measuring without failing.
    """
    slots = 0
    gap_total = 0
    species: set[str] = set()
    for name in sorted(SHAPES):
        for result in _results(SHAPES[name]["result"]):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for gap in report.get("gaps") or []:
                offered = [p["route"]
                           for p in gap.get("alternative_paths") or []]
                if not offered:
                    continue
                gap_total += 1
                slots += len(offered)
                species.add(gap["kind"])
                allowed = {str(route) for route in gaps.ways_past(
                    gap["kind"],
                    blocking=gap.get("severity") == "blocking")}
                assert set(offered) <= allowed, (name, gap["kind"])
    assert (slots, gap_total, len(species)) == (1193, 427, 29)


def test_the_door_still_accepts_every_answer_the_corpus_holds():
    for name in sorted(SHAPES):
        row = SHAPES[name]
        for result in _results(row["result"]):
            verify_honestly(row["program"], result)


# ----------------------------------------------------- what the rule holds


def _report(kind: str, route: str, severity: str = "blocking") -> dict:
    return {"gaps": [{"kind": kind, "severity": severity,
                      "alternative_paths": [{"route": route}]}]}


def test_every_species_refuses_every_way_past_that_is_not_its_own():
    """Both directions over the whole cross product, so the gate cannot
    be tightened on one species and loosened on another without saying
    so. ``blocking`` is passed for every species here because it is the
    widest permission any of them gets."""
    refused = 0
    allowed = 0
    for kind in sorted(k.value for k in GapKind):
        own = {str(r) for r in gaps.ways_past(kind, blocking=True)}
        for candidate in ALL_ROUTES:
            report = _report(kind, candidate)
            if candidate in own:
                data_gap_rules._verify_t10_7_ways_past(report)
                allowed += 1
                continue
            with pytest.raises(VerificationError, match="T10-7"):
                data_gap_rules._verify_t10_7_ways_past(report)
            refused += 1
    assert (allowed, refused) == (137, 3433)
    assert allowed + refused == len(list(GapKind)) * len(ALL_ROUTES)


def test_a_species_with_no_way_past_is_told_so_in_its_own_words():
    with pytest.raises(VerificationError, match="has no way past at all"):
        data_gap_rules._verify_t10_7_ways_past(
            _report("low_confidence_input_data", "run_an_e_value"))


def test_the_rule_declines_a_species_this_build_cannot_name():
    """An unrecognised kind belongs to T10-3, and a rule refusing for a
    reason another authority owns reports that authority's coverage as
    its own."""
    data_gap_rules._verify_t10_7_ways_past(
        _report("a_species_from_some_other_build", "run_an_e_value"))


def test_the_rule_declines_a_route_this_build_cannot_name():
    """An unrecognised route belongs to the contract, which enumerates
    them, and ``verify`` validates against it before any rule runs."""
    data_gap_rules._verify_t10_7_ways_past(
        _report("unmeasured_confounder_risk", "go_and_ask_someone"))


# ------------------------------------------- the reader's door, and the gap


def _carrier(kind: str):
    """An accepted answer offering a way past, and where it sits."""
    for name in sorted(SHAPES):
        row = SHAPES[name]
        try:
            for one in _results(row["result"]):
                _door(one)(row["program"], one)
        except Exception:                                      # noqa: BLE001
            continue
        for index, result in enumerate(_results(row["result"])):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for position, gap in enumerate(report.get("gaps") or []):
                if gap.get("kind") == kind and gap.get("alternative_paths"):
                    return name, index, position
    raise AssertionError(f"no accepted answer in the corpus offers a {kind}")


def test_the_advice_a_gap_gives_cannot_be_swapped_for_another_species():
    """The measurement the gate exists for, at the door a reader uses.

    Sixty-three of the eighty-four foreign routes went through before,
    and what survives now is this species' own other two — the ceiling
    working as declared, not a gap in it.
    """
    name, index, position = _carrier("unmeasured_confounder_risk")
    row = SHAPES[name]
    honest = _results(row["result"])[index]["data_gap_report"]["gaps"][
        position]["alternative_paths"][0]["route"]
    assert honest == "run_an_e_value"

    through = []
    for candidate in ALL_ROUTES:
        if candidate == honest:
            continue
        envelope = copy.deepcopy(_results(row["result"])[index])
        envelope["data_gap_report"]["gaps"][position][
            "alternative_paths"][0]["route"] = candidate
        try:
            _door(envelope)(row["program"], envelope)
        except Exception:                                      # noqa: BLE001
            continue
        through.append(candidate)
    assert through == ["cross_check_an_experiment", "emulate_a_target_trial"]
    assert set(through) < {str(r) for r in gaps.ROUTES_OF[
        GapKind.UNMEASURED_CONFOUNDER_RISK]}


def test_without_the_rule_the_same_swap_goes_through(monkeypatch):
    """What the gate is worth, measured rather than asserted. The routes
    that get past without it are not near-misses: 'go and find a
    stronger instrument' on a gap about unmeasured confounding is advice
    for a study that was never run."""
    name, index, position = _carrier("unmeasured_confounder_risk")
    row = SHAPES[name]
    monkeypatch.setattr(
        data_gap_rules, "_verify_t10_7_ways_past", lambda report: None)
    through = []
    for candidate in ALL_ROUTES:
        envelope = copy.deepcopy(_results(row["result"])[index])
        envelope["data_gap_report"]["gaps"][position][
            "alternative_paths"][0]["route"] = candidate
        try:
            _door(envelope)(row["program"], envelope)
        except Exception:                                      # noqa: BLE001
            continue
        through.append(candidate)
    assert len(through) == 64
    assert "find_a_stronger_instrument" in through


# ---------------------------------------------------------- what it is not


def test_two_ways_past_of_one_species_are_still_interchangeable():
    """Said out loud, because a ceiling that nobody states gets read as a
    floor. Deciding between them means saying which the occasion offers,
    and that is the renderer's branches copied into a table."""
    both = {Route.CROSS_CHECK_AN_EXPERIMENT, Route.RUN_AN_E_VALUE}
    assert both <= gaps.ROUTES_OF[GapKind.UNMEASURED_CONFOUNDER_RISK]
    for route in both:
        data_gap_rules._verify_t10_7_ways_past(
            _report("unmeasured_confounder_risk", str(route)))


def test_a_gap_may_still_offer_the_same_way_past_twice():
    """Measured while building this gate and left open on purpose.

    One answer in the corpus offers the same way past twice, and the two
    are not a duplicate: a dispatch conflict leaves the reader a choice of
    WHICH layer to drop, and both directions are ``DROP_THE_OTHER_LAYER``
    with the wanted and dropped layers swapped in the words it quotes.
    Deduplicating by route would delete one of two real options.

    What is wrong is that the route names the action and not its
    direction, so a reader keyed on the route alone is offered one thing
    twice. Closing it means either a member per direction or a contract
    saying a route's identity includes the words beside it — a different
    root cause from a route belonging to another species, and putting
    both behind this gate would be two claims at one door."""
    twice = [
        (name, gap["kind"])
        for name in sorted(SHAPES)
        for result in _results(SHAPES[name]["result"])
        if isinstance(result.get("data_gap_report"), dict)
        for gap in result["data_gap_report"].get("gaps") or []
        for routes in [[p["route"]
                        for p in gap.get("alternative_paths") or []]]
        if len(routes) != len(set(routes))
    ]
    assert [kind for _, kind in twice] == [
        "unattempted_layer_due_to_dispatch_conflict"]
