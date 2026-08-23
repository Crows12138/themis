# -*- coding: utf-8 -*-
"""#438 — ``alternative_paths`` holds routes, and a pass may not read prose.

The field named ways past a gap and stored finished sentences, so the three
passes that had to know WHICH way out an entry was recovered it from the
rendered text: one rebuilt the string and compared, one searched it for
``"bounds"`` / ``"Manski"`` / ``"Balke-Pearl bounds"``, and a third — the
module that writes the replacement the second one looks for — carried a
comment saying its wording had been chosen so those substrings would not
appear in it. The wording of a user-facing Chinese sentence was a
load-bearing input to kernel control flow, and the second language would
have decided it differently.

So the entry is ``{route, said?, words?}``: the token IS the identity, the
occasion's facts travel beside it, and the sentence belongs to whichever
surface knows who is reading. What this file holds is that shape — the
vocabulary total in both directions, the sentence complete in every
language this build writes, the schema admitting exactly the members, and
the one property a pass asks about a route answered by the route rather
than by its spelling.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from themis import gaps, language
from themis.gaps import BY_ROUTE, ROUTES, Route
from themis.types import GapBlocks, GapKind, GapRoute, GapSeverity, DataGap

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The longest a way out may be. A route is one sentence a reader acts on;
#: past this it is the paragraph the field used to hold, arriving under a
#: new name. Measured rather than guessed — the longest today is 256 — and
#: the headroom is for a route with more to say, not for a second one.
LONGEST = 300

#: The three substrings the scheduler used to search a rendered path for.
#: Kept here as what the rule REPLACED, so the two tests at the bottom can
#: construct the cases where the answer and the text disagree.
GREPPED = ("Balke-Pearl bounds", "Manski", "bounds")


# --------------------------------------------------------------- vocabulary


@pytest.mark.parametrize("member", sorted(Route))
def test_every_route_has_a_sentence(member):
    """No route is offered that no surface can say."""
    assert str(member) in ROUTES, (
        f"{member.name} is a route nothing can render; give it a sentence "
        f"in themis.gaps.ROUTES beside the member"
    )


def test_no_sentence_belongs_to_no_route():
    """The other direction. A sentence with no member is one no writer can
    reach — dead wording that reads, to whoever adds the next route, like
    an option already taken."""
    orphans = sorted(set(ROUTES) - {str(r) for r in Route})
    assert not orphans, orphans


@pytest.mark.parametrize("member", sorted(Route))
def test_a_route_is_written_in_every_language(member):
    """Completeness by the build's own denominator, not by a list here."""
    missing = sorted(set(language.written()) - set(ROUTES[str(member)]))
    assert not missing, f"{member.name} has no text in {missing}"


@pytest.mark.parametrize("member", sorted(Route))
def test_the_languages_of_a_route_have_the_same_holes(member):
    """A hole one language has and another does not is a fact one reader is
    given and the other is not. The union is what :func:`language.holes`
    answers, and rendering an unfilled hole is visible rather than silent —
    but a template that never had the hole cannot even do that.

    ``test_the_language_is_a_parameter_not_a_name`` holds this across the
    whole package already. Stated again here because the two fail
    differently: that one names a file and a line, this one names the route,
    and a route is what somebody adding the next one is looking at."""
    words = ROUTES[str(member)]
    per = {lang: frozenset(re.findall(r"\{(\w+)\}", text))
           for lang, text in words.items()}
    assert len(set(per.values())) == 1, f"{member.name}: {per}"


@pytest.mark.parametrize("member", sorted(Route))
def test_a_route_stays_a_sentence(member):
    """The size gate. What this field used to hold had a median of 1518
    characters on the corpus, which is the shape a reader skips."""
    for lang, text in ROUTES[str(member)].items():
        assert len(text) <= LONGEST, (
            f"{member.name}[{lang}] is {len(text)} characters"
        )


def test_the_schema_admits_exactly_these_routes():
    """The browser's denominator. Its table is generated from the schema, so
    a member the schema does not name is a route no envelope may carry and a
    name the schema has that the vocabulary lost is a table row for a route
    nothing offers."""
    schema = json.loads(
        (REPO / "themis/schemas/query_result.schema.json")
        .read_text(encoding="utf-8"))
    assert schema["$defs"]["route"]["enum"] == [str(r) for r in Route]


def test_every_route_is_offered_somewhere():
    """A route nothing constructs is a way out no reader is ever shown. The
    denominator is the package, because the point of naming a route is that
    the site offering it stops writing the sentence itself."""
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (REPO / "themis").rglob("*.py"))
    named = set(re.findall(r"Route\.([A-Z][A-Z_0-9]*)", src))
    assert not [r.name for r in Route if r.name not in named]


# ------------------------------------------------------------------- doors


def test_the_writers_door_refuses_a_route_it_cannot_name():
    """The counterexample the door exists for: a way out offered under a
    name nothing declares reaches the envelope, and the surface that has to
    render it has nothing to render."""
    with pytest.raises(ValueError, match="not a route"):
        gaps.route("collect_more_data")


def test_the_writers_door_refuses_a_route_with_no_sentence():
    """The second half. Declaring the member and forgetting the sentence is
    the likelier slip, and it fails at the site rather than at the reader."""
    class _Mute(str):
        pass

    saved = ROUTES.pop(str(Route.FIND_AN_INSTRUMENT))
    try:
        with pytest.raises(ValueError, match="no sentence"):
            gaps.route(Route.FIND_AN_INSTRUMENT)
    finally:
        ROUTES[str(Route.FIND_AN_INSTRUMENT)] = saved


def test_the_readers_door_answers_nothing_for_a_route_it_has_not_heard_of():
    """Not an error, because the passes that ask are deciding whether to
    WITHDRAW something, and withdrawing what you cannot name is worse than
    leaving it standing."""
    assert gaps.taken({"route": "from_a_later_build"}) is None
    assert gaps.taken({}) is None
    assert gaps.taken({"route": "find_an_instrument"}) is Route.FIND_AN_INSTRUMENT


def test_a_route_survives_the_round_trip_through_json():
    """Written by :func:`gaps.route_fields` and read by
    :func:`gaps.route_entry` — one shape, two halves, stated together."""
    original = gaps.route(Route.BOUNDS_ALREADY_COMPUTED, methods="manski")
    written = gaps.route_fields(original)
    assert written == {"route": "bounds_already_computed",
                       "said": {"methods": "manski"}}
    assert gaps.route_entry(written) == original


def test_an_occasion_with_nothing_to_say_writes_no_empty_keys():
    """"There is nothing here" has one spelling and the door picks it."""
    assert gaps.route_fields(gaps.route(Route.FIND_AN_INSTRUMENT)) == {
        "route": "find_an_instrument"}


def test_a_word_in_a_hole_travels_as_its_set_and_its_token():
    """The slot that holds a scale holds a WORD: its text is the reader's
    language, so it leaves as the pair a reader looks up rather than as one
    language's adjective."""
    from themis.output.envelope_glossary import Scale

    entry = gaps.route(Route.FIX_THE_DATA_TO_MATCH_THE_DECLARATION,
                       variable="bmi", scale=Scale.NOMINAL)
    assert entry.said == {"variable": "bmi"}
    assert entry.words == {
        "scale": {"vocabulary": "measurement_scale", "token": "nominal"}}
    assert "名义" in gaps.went(entry, "zh")
    assert "nominal" in gaps.went(entry, "en")


# ------------------------------------------- the property, not the spelling


def _reconciled(route: Route, methods=("manski_natural",)):
    """The ROUTES one gap is left with, after the scheduler's bounds pass."""
    return [a.route for a in _reconciled_entries(route, methods)]


def _reconciled_entries(route: Route, methods=("manski_natural",)):
    """One gap carrying one route, through the scheduler's bounds pass.

    Entries rather than routes, because what a pointer NAMES is half of
    what the pass decides: replacing a route with a pointer to bounds it
    does not accept and replacing it with one it does are the same route
    on the way out.
    """
    from themis.runtime import scheduler
    from themis.types import (
        BoundsMethod, BoundsResult, QueryKind, QueryResult, ResultStatus,
    )
    from themis.types import DataGapReport

    report = DataGapReport(gaps=(DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        severity=GapSeverity.IMPORTANT,
        blocks=GapBlocks.IDENTIFICATION,
        describes=(),
        alternative_paths=(GapRoute(route=route),),
        provenance=(),
    ),))
    result = QueryResult(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        data_gap_report=report,
        bounds_results=tuple(
            BoundsResult(method=BoundsMethod(m), lower_expression="0",
                         upper_expression="1", estimand="ATE")
            for m in methods),
    )
    out = scheduler._reconcile_alt_paths_with_bounds(result, None)
    return list(out.data_gap_report.gaps[0].alternative_paths)


def test_a_bounds_route_is_reconciled_even_when_its_words_say_nothing_of_bounds():
    """The counterexample the property exists for.

    Reword the route so none of the three substrings the scheduler used to
    search for appear in it, in either language. The route is the same route
    — it still offers this question's interval — so the pass must still
    replace it with the interval that has arrived. The implementation this
    replaced answers no here, and its own docstring says why: the answer
    depended on the wording of a user-facing sentence.
    """
    key = str(Route.FALL_BACK_TO_IV_BOUNDS)
    saved = ROUTES[key]
    ROUTES[key] = {"zh": "退回到只给区间的答案", "en": "take the interval instead"}
    try:
        assert not any(tok in ROUTES[key][lang]
                       for lang in ROUTES[key] for tok in GREPPED)
        assert _reconciled(Route.FALL_BACK_TO_IV_BOUNDS) == [
            Route.BOUNDS_ALREADY_COMPUTED]
    finally:
        ROUTES[key] = saved


def test_a_route_that_merely_mentions_bounds_is_left_where_it_stands():
    """The twin, and the half the substring test got wrong in the other
    direction: a way out that NAMES Manski while offering something else is
    not this question's interval, and replacing it loses the way out."""
    key = str(Route.FIND_AN_INSTRUMENT)
    saved = ROUTES[key]
    ROUTES[key] = {
        "zh": "找一个工具变量 —— Manski 自然界对它没有要求",
        "en": "find an instrument — Manski bounds ask nothing of it"}
    try:
        assert any(tok in ROUTES[key]["en"] for tok in GREPPED)
        assert Route.FIND_AN_INSTRUMENT in _reconciled(
            Route.FIND_AN_INSTRUMENT)
    finally:
        ROUTES[key] = saved


def test_only_the_routes_that_offer_this_questions_interval_point_at_bounds():
    """The property is narrow on purpose. A route that offers an interval to
    a DIFFERENT question — binarise the dose, and then Themis can bracket it
    — is not made redundant by bounds on THIS one, and could not say so
    while the test was a substring."""
    assert {r.name for r in Route if r.answered_by} == {
        "ACCEPT_THE_INTERVAL",
        "BOUNDS_ALREADY_COMPUTED",
        "FALL_BACK_TO_IV_BOUNDS",
        "FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION",
    }
    assert not Route.FALL_BACK_TO_A_BINARY_CONTRAST.answered_by
    assert not Route.BOUND_THE_UNSUPPORTED_REGION.answered_by


# ------------------------------------------ which interval answers which route


def test_a_route_escaping_an_assumption_accepts_no_bound_that_makes_it():
    """The two records held together, and the reason this is a set.

    One route is handed out because an over-identification test REFUTED
    the exclusion restriction. Balke-Pearl's bound assumes it — read off
    the builder rather than asserted here — so accepting that bound would
    answer a refuted assumption with itself. A flag could not hold this
    difference, which is what made the substitution unsound.
    """
    from themis.types import BoundsMethod

    assumes = _methods_that_assume_exclusion()
    assert assumes == {BoundsMethod.BALKE_PEARL_IV}, sorted(
        m.value for m in assumes)
    assert not (
        Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION.answered_by & assumes)
    # And the escape is the only narrowing: every other bound still answers
    # it, so the route does not quietly become one nothing can replace.
    assert (Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION.answered_by
            == set(BoundsMethod) - assumes)


def _methods_that_assume_exclusion():
    """Which bounds methods attach an exclusion assumption, per the builder.

    Read out of ``themis/output/bounds.py`` rather than restated here: the
    route's declaration is one record of this and the builder is the other,
    and a gate that restates the builder is a third.
    """
    import ast
    import pathlib

    from themis.types import BoundsMethod

    tree = ast.parse(
        (pathlib.Path(__file__).resolve().parent.parent
         / "themis" / "output" / "bounds.py").read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and ast.unparse(node.func).endswith("BoundsResult")):
            continue
        said = {k.arg: k.value for k in node.keywords}
        if "method" not in said or "assumptions" not in said:
            continue
        name = ast.unparse(said["method"]).rsplit(".", 1)[-1]
        text = ast.unparse(said["assumptions"])
        if "exclusion" in text:
            found.add(BoundsMethod[name])
    return found


def test_a_pointer_names_only_the_methods_its_route_accepts():
    """The substitution, on the case the sets were introduced for.

    Both bounds are in hand. The route that got away from exclusion is
    answered by one of them, and the pointer that replaces it says so —
    naming both would send the reader to the interval resting on the
    assumption the route exists because the data refuted.
    """
    entries = _reconciled_entries(
        Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION,
        methods=("balke_pearl_iv", "manski_natural"))
    assert [a.route for a in entries] == [Route.BOUNDS_ALREADY_COMPUTED]
    assert entries[0].said == {"methods": "manski_natural"}


def test_a_route_survives_bounds_it_cannot_accept():
    """The other half, and the one a flag got wrong in both directions.

    The only interval computed is the one this route got away from. There
    is nothing to replace it with, and its offer is still open — so it
    stands. Dropping it would lose a live way out; replacing it would be
    the defect above.
    """
    assert _reconciled(Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION,
                       methods=("balke_pearl_iv",)) == [
        Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION]


def test_a_route_that_accepts_everything_is_replaced_by_everything():
    """Unchanged behaviour for the three routes that escape nothing, said
    out loud: the narrowing is one route's, not the mechanism's."""
    entries = _reconciled_entries(
        Route.FALL_BACK_TO_IV_BOUNDS,
        methods=("balke_pearl_iv", "manski_natural"))
    assert [a.route for a in entries] == [Route.BOUNDS_ALREADY_COMPUTED]
    assert entries[0].said == {"methods": "balke_pearl_iv, manski_natural"}


def test_the_lookup_and_the_declaration_are_the_same_set():
    """``BY_ROUTE`` is how every read-side lookup names a route, and a
    lookup table that has drifted from its vocabulary is a route that
    exists and cannot be found."""
    assert BY_ROUTE == {str(r): r for r in Route}
