"""What repairs a gap depends on why it opened, not on which channel repairs it.

``GapKind`` is the coarse name — ``themis.gaps``' own opening paragraph
says so, and measured it: ten distinct findings arrive as
``unidentifiable_no_admissible_set``, nine as ``missing_structural_input``,
eleven as ``missing_assumption``. ``Need`` is the fine one, and the kind is
read off it so the two cannot disagree.

The escape routes were the one consumer left hanging on the coarse name,
and the three renderers under the three widest kinds show what that costs
in both directions at once. Two noticed and went silent, each saying so in
its own docstring — "these range too widely for one line of advice to fit
them all", "one sentence of generic advice would be wrong for most of
them". The third did not notice and shipped the advice: measure the
confounder, run an RCT past the back door, find an instrument. Handed to a
reader whose effect would not TRANSPORT, the third line sends them to
collect an instrument in the source population, which transports nothing —
and the very same gap already carried ``transport_not_identifiable`` in
the field beside it.

The same trio also reached ``no_c_factor_witness``, whose own sentence
ends "and no instrument route is available either": one gap contradicting
itself in two adjacent fields.
"""
from __future__ import annotations

import pytest

import themis
from themis import gaps as _gaps
from themis.gaps import Need, Route
from themis.output import data_gap_report as _report


def _a(pred: str, obj: str = "me") -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": obj}]}


def _binary(*names: str) -> list[dict]:
    return [
        {"kind": "variable", "predicate": n, "domain": [True, False]}
        for n in names
    ]


def _run(program: dict) -> dict:
    return themis.run(program)["results"][0]


def _routes(result: dict, kind: str) -> list[str]:
    """Every route offered on the gaps of one kind, in the order read.

    ``bounds_already_computed`` is dropped: the scheduler stamps it on
    whatever gaps are open once the interval methods have run, so it is a
    fact about this run and not about the species — the distinction the
    table under test is built on.
    """
    report = result.get("data_gap_report")
    assert report is not None, "no report — a different failure"
    return [
        alt["route"]
        for gap in report["gaps"] if gap["kind"] == kind
        for alt in (gap.get("alternative_paths") or ())
        if alt["route"] != "bounds_already_computed"
    ]


_UNIDENTIFIABLE = "unidentifiable_no_admissible_set"


# ---------------------------------------------------------------------------
# The witness: a transport failure, told to go and find an instrument
# ---------------------------------------------------------------------------


def _transport_program() -> dict:
    """The selection node sits on the outcome, so no S-admissible set
    separates the populations and the source effect does not carry over."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "selection_node", "id": "s_y",
             "source_population": "trial",
             "target_population": "real_world",
             "affects": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target_population": "real_world",
                "target": {"atom": _a("y"), "value": True},
                "intervention": {"atom": _a("x"), "value": True},
                "given": [],
            }},
        ],
    }


def test_a_transport_failure_is_not_offered_an_instrument():
    """The counterexample this table exists to produce. An instrument in
    the source population identifies the SOURCE effect, which is the one
    already refused — so the route is not weaker advice here, it is
    advice for another question."""
    result = _run(_transport_program())
    offered = _routes(result, _UNIDENTIFIABLE)
    assert "find_an_instrument" not in offered
    assert offered == [
        "measure_what_differs_between_the_populations",
        "run_the_study_in_the_target_population",
        "accept_the_source_ate",
    ]


def test_the_transport_gap_and_its_routes_name_the_same_failure():
    """Producer and report were never in disagreement about the reason —
    the species was on the envelope all along. What was missing was any
    path from it to the advice."""
    result = _run(_transport_program())
    gap = next(g for g in result["data_gap_report"]["gaps"]
               if g["kind"] == _UNIDENTIFIABLE)
    said = gap["describes"][0]["words"]["why"]
    assert said["token"] == "transport_not_identifiable"
    assert tuple(a["route"] for a in gap["alternative_paths"]) == tuple(
        str(r) for r in _gaps.ESCAPES[Need.TRANSPORT_NOT_IDENTIFIABLE])


@pytest.mark.parametrize("lang, phrase, absent", [
    ("zh", "在目标人群里做这个研究", "工具变量"),
    ("en", "run the study in the target population", "instrument"),
])
def test_the_transport_routes_reach_the_reader_in_both_languages(
    lang, phrase, absent,
):
    """Both halves in both languages, because a route that only reaches
    one reader is the defect this vocabulary exists to prevent, and the
    wrong advice was wrong in both."""
    result = _run(_transport_program())
    rendered = " ".join(
        _gaps.went(alt, lang)
        for gap in result["data_gap_report"]["gaps"]
        if gap["kind"] == _UNIDENTIFIABLE
        for alt in gap["alternative_paths"]
    )
    assert phrase in rendered
    assert absent not in rendered


# ---------------------------------------------------------------------------
# The species whose own sentence denies the route it was being offered
# ---------------------------------------------------------------------------


def test_no_c_factor_witness_says_there_is_no_instrument_route():
    """Read the two together, because the defect was only visible that
    way: the species text and the routes were both right about their own
    subject and contradicted each other about the reader's next move."""
    assert "no instrument route is available" in Need.NO_C_FACTOR_WITNESS.says
    assert Route.FIND_AN_INSTRUMENT not in _gaps.ESCAPES[
        Need.NO_C_FACTOR_WITNESS]


def test_no_species_offers_a_route_its_own_sentence_denies():
    """The general form, so the next species to say "and no X either"
    cannot quietly offer X. Written against the sentence rather than a
    list, since a list would be one more thing to keep in step."""
    denied = {
        "no instrument route is available": Route.FIND_AN_INSTRUMENT,
    }
    for need, routes in _gaps.ESCAPES.items():
        for phrase, route in denied.items():
            if phrase in need.says:
                assert route not in routes, (
                    f"{need} says {phrase!r} and offers {route}")


# ---------------------------------------------------------------------------
# Where the trio was right, it stays
# ---------------------------------------------------------------------------


def test_a_bow_arc_keeps_the_advice_that_was_written_for_it():
    """``x → y`` with ``x ↔ y``. The species the old constants were
    written for, and the claim this change makes is about the other nine:
    they were being told this one's answer."""
    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "bidirected", "left": _a("x"), "right": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _a("x"), "value": True},
                "target": {"atom": _a("y"), "value": True},
                "given": [],
            }},
        ],
    })
    offered = _routes(result, _UNIDENTIFIABLE)
    assert offered[-3:] == [
        "measure_the_confounder_and_reidentify",
        "run_an_rct_past_the_backdoor",
        "find_an_instrument",
    ]


def test_a_conditional_estimand_idc_cannot_reach_is_offered_the_marginal():
    """IDC hit a hedge on the conditional and the marginal is explicitly
    NOT substituted for it — so asking for the unconditional effect is a
    question the reader can put, and the one route the old trio had no
    way to name."""
    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y", "c") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "cause", "from": _a("c"), "to": _a("y")},
            {"kind": "bidirected", "left": _a("x"), "right": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _a("y"), "value": True},
                "intervention": {"atom": _a("x"), "value": True},
                "given": [{"atom": _a("c"), "value": True}],
            }},
        ],
    })
    offered = _routes(result, _UNIDENTIFIABLE)
    assert "ask_the_unconditional_effect" in offered


def test_an_identify_query_with_no_witness_is_not_offered_an_instrument():
    """``no_c_factor_witness`` end to end — the species whose sentence
    says an instrument route is unavailable. The two claims that used to
    sit in one gap are now one claim: the escape list ends where the
    sentence says it ends."""
    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("x", "y", "c") + [
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "cause", "from": _a("c"), "to": _a("y")},
            {"kind": "bidirected", "left": _a("x"), "right": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "identify",
                "target": _a("y"),
                "intervention": {"atom": _a("x"), "value": True},
                "given": [_a("c")],
            }},
        ],
    })
    offered = _routes(result, _UNIDENTIFIABLE)
    assert "find_an_instrument" not in offered
    assert offered == [
        "measure_the_confounder_and_reidentify",
        "run_an_rct_past_the_backdoor",
    ]


# ---------------------------------------------------------------------------
# The two renderers that went silent rather than say something wrong
# ---------------------------------------------------------------------------


def test_a_layer_combination_defect_is_offered_the_route_written_for_it():
    """``drop_the_other_layer`` was in the vocabulary, worded for exactly
    this program, and unreachable from the species that raises it —
    because the renderer under this kind offered nothing to anybody."""
    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("a", "b", "m", "y") + [
            {"kind": "cause", "from": _a("a"), "to": _a("m")},
            {"kind": "cause", "from": _a("m"), "to": _a("y")},
            {"kind": "cause", "from": _a("b"), "to": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _a("a"), "value": True},
                "extra_interventions": [{"atom": _a("b"), "value": True}],
                "mediator": _a("m"),
                "target": {"atom": _a("y"), "value": True},
                "given": [],
            }},
        ],
    })
    assert _routes(result, "missing_structural_input") == [
        "drop_the_other_layer"]


def test_a_repeated_treatment_atom_is_still_offered_nothing():
    """The other half of the same renderer, and the reason an empty tuple
    is not allowed to be the way a species says this: ``do(a=T, a=F)`` is
    a defect whose sentence already names the repair, and a route
    restating it would be the same line under a second heading. That is a
    declared position now, in ``NO_SPECIES_ESCAPE``, rather than a
    consequence of where the constants happened to hang."""
    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": _binary("a", "y") + [
            {"kind": "cause", "from": _a("a"), "to": _a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _a("a"), "value": True},
                "extra_interventions": [{"atom": _a("a"), "value": False}],
                "target": {"atom": _a("y"), "value": True},
                "given": [],
            }},
        ],
    })
    assert _routes(result, "missing_structural_input") == []
    assert Need.DUPLICATE_TREATMENT_ATOM in _gaps.NO_SPECIES_ESCAPE


# ---------------------------------------------------------------------------
# The table is total, and each half means something different
# ---------------------------------------------------------------------------


def test_every_species_is_on_exactly_one_table():
    on_both = {n for n in _gaps.ESCAPES if n in _gaps.NO_SPECIES_ESCAPE}
    assert not on_both
    assert set(_gaps.ESCAPES) | set(_gaps.NO_SPECIES_ESCAPE) == set(Need)


def test_a_species_on_neither_table_refuses_to_import(monkeypatch):
    """The counterexample for the gate itself. Dropping one species is
    exactly what adding one without an escape looks like."""
    thinned = dict(_gaps.ESCAPES)
    del thinned[Need.TRANSPORT_NOT_IDENTIFIABLE]
    monkeypatch.setattr(_gaps, "ESCAPES", thinned)
    with pytest.raises(ValueError, match="transport_not_identifiable"):
        _gaps._bind_escapes()


def test_a_species_on_both_tables_refuses_to_import(monkeypatch):
    """Which one the reader sees would depend on lookup order, and a
    reader cannot tell that from a report."""
    monkeypatch.setattr(_gaps, "NO_SPECIES_ESCAPE", {
        **_gaps.NO_SPECIES_ESCAPE,
        Need.TRANSPORT_NOT_IDENTIFIABLE: "two authors for one answer",
    })
    with pytest.raises(ValueError, match="both routes and a reason"):
        _gaps._bind_escapes()


def test_an_empty_route_tuple_refuses_to_import(monkeypatch):
    """An absence that says nothing is the state this whole table
    replaces, so it cannot be spelled here."""
    monkeypatch.setattr(_gaps, "ESCAPES", {
        **_gaps.ESCAPES, Need.TRANSPORT_NOT_IDENTIFIABLE: (),
    })
    with pytest.raises(ValueError, match="empty route tuple"):
        _gaps._bind_escapes()


def test_every_declared_absence_gives_a_reason():
    for need, because in _gaps.NO_SPECIES_ESCAPE.items():
        assert isinstance(because, str) and len(because) > 20, need


def test_every_declared_route_has_a_sentence_for_the_reader():
    """``route()`` raises on a route with no entry in ``ROUTES``; running
    it over the table is what makes that check reach these."""
    for need, routes in _gaps.ESCAPES.items():
        for r in routes:
            assert _gaps.route(r).route is r, need


def test_an_unknown_species_name_is_an_error_not_an_absence():
    """A typo and a declared absence read the same at the call site and
    are not the same thing, so only one of them is quiet."""
    with pytest.raises(ValueError, match="not a species"):
        _gaps.escapes("transport_not_identifialbe")


def test_a_species_with_no_escape_declared_yields_no_routes():
    assert _gaps.escapes(Need.DUPLICATE_TREATMENT_ATOM) == ()


# ---------------------------------------------------------------------------
# What stayed at the site, and why that is the same rule
# ---------------------------------------------------------------------------


def test_routes_naming_this_program_are_not_on_the_species_table():
    """The split the table draws: a route the REASON settles is declared
    beside the reason; a route naming this occasion's variables is built
    where those names are known. The loop species are the check, since
    their routes are real and carry the loop's two variable names."""
    for need in (Need.FEEDBACK_LOOP_NEEDS_AN_INSTRUMENT,
                 Need.FEEDBACK_LOOP_OUTSIDE_THE_SIMULTANEOUS_CASE):
        assert need in _gaps.NO_SPECIES_ESCAPE
        assert "name" in _gaps.NO_SPECIES_ESCAPE[need]


def test_the_instrument_repair_pass_still_owns_the_occasion():
    """``_rewrite_iv_aware_alternatives`` replaces "go find an
    instrument" when IV bounds already came out of one. It reads
    ``bounds_results``, not the species — an occasion fact — so moving
    the species facts out from under it leaves it whole, and the species
    that no longer offer that route simply give it nothing to rewrite."""
    assert _report._rewrite_iv_aware_alternatives([], []) == []


def test_both_names_for_the_instrument_channel_are_rewritten_together():
    """Whether the caller has to go and FIND an instrument is the
    species' business; what to do once an interval has come out of one is
    the run's. The pass read for a single route name, so the moment a
    species sent the reader to that channel under the other name it went
    quiet and left "an instrument is your way past this" standing beside
    an interval that already came from one."""
    assert Route.FIND_AN_INSTRUMENT in _gaps.INSTRUMENT_CHANNEL
    assert (Route.TAKE_THE_INSTRUMENT_ROUTE_THE_GRAPH_OFFERS
            in _gaps.INSTRUMENT_CHANNEL)
    offered = {
        r for routes in _gaps.ESCAPES.values() for r in routes
        if r in _gaps.INSTRUMENT_CHANNEL
    }
    assert offered == _gaps.INSTRUMENT_CHANNEL, (
        "a member no species offers is a rewrite that can never fire")


def test_no_species_table_entry_needs_a_slot_filled():
    """Every route on the species table renders with no occasion values,
    which is what lets the table be about the species. A route wanting a
    slot would raise here rather than reach a reader with a brace in it."""
    for need, routes in _gaps.ESCAPES.items():
        for r in routes:
            for lang in ("zh", "en"):
                text = _gaps.went({"route": str(r)}, lang)
                assert "{" not in text, (need, r, lang)
