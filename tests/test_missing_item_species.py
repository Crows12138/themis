"""The species a kernel refusal declares is the species the user reads.

``MissingItem.gap`` states what kind of shortfall the kernel hit, next to
``MissingKind``, which states which channel repairs it. Before it existed
the report recovered the species from ``MissingItem.name`` with prefix and
substring tests, and recovered it wrongly whenever a name happened to read
like another species.

The producer branches exercised here had no behavioural test at all — a
run of the whole suite with the declaration recorded on every item showed
five of the thirty name templates never appearing. Nothing would have
caught a wrong species on those, which is exactly the position the string
matching was in: silently wrong on the paths nobody runs.
"""
from __future__ import annotations

import pytest

import themis


def _a(pred: str, obj: str = "me") -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": obj}]}


def _binary(*names: str) -> list[dict]:
    return [
        {"kind": "variable", "predicate": n, "domain": [True, False]}
        for n in names
    ]


def _run(program: dict) -> dict:
    return themis.run(program)["results"][0]


def _species(result: dict) -> dict[str, str]:
    return {
        m["name"]: m["gap"] for m in (result.get("missing_information") or [])
    }


def _gap_kinds_citing(result: dict, target: str) -> set[str]:
    report = result.get("data_gap_report")
    assert report is not None, "no report — a different failure"
    return {
        gap["kind"]
        for gap in report["gaps"]
        for ref in (gap.get("provenance") or [])
        if ref["ref_kind"] == "investigation_request" and ref["ref_id"] == target
    }


def _assert_declared_species_reaches_the_report(
    result: dict, name: str, species: str,
) -> None:
    assert _species(result)[name] == species
    assert species in _gap_kinds_citing(result, name)


# ---------------------------------------------------------------------------
# Not identifiable — the estimand is out of reach on this graph
# ---------------------------------------------------------------------------


def test_a_conditional_query_idc_cannot_reach_is_not_identifiable():
    """``x ↔ y`` with a conditioning covariate. IDC finds no witness, and
    the instrumental escape is not consulted for a conditional query, so
    the kernel reports the estimand out of reach rather than a defect in
    the program."""
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
    _assert_declared_species_reaches_the_report(
        result, "query:identify_unreachable",
        "unidentifiable_no_admissible_set",
    )
    assert result["data_gap_report"]["answer_tier"] == "none"


def test_transport_with_no_admissible_selection_set_is_not_identifiable():
    """The selection node sits on the outcome itself, so no S-admissible
    set separates the populations and the trial's effect does not carry
    over. Collecting more data in the source population cannot fix it.

    The species declared here is the one the report infers today, which
    is ``missing_structural_input`` — and that is wrong, in a way this
    file's subject makes visible rather than causes: ``answer_tier``
    reads only ``unidentifiable_no_admissible_set`` to decide the point
    estimand is blocked, so this query comes back ``answer_tier ==
    "point"`` with no formula and no structural result. Recorded as it
    stands so the correction is a visible change of species and not a
    quiet edit."""
    result = _run({
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
    })
    _assert_declared_species_reaches_the_report(
        result, "transport:real_world", "missing_structural_input",
    )
    assert "not transportable" in result["data_gap_report"]["summary"]


# ---------------------------------------------------------------------------
# Defects in the program — the graph is not what blocks these
# ---------------------------------------------------------------------------


def test_a_joint_intervention_repeating_an_atom_is_a_program_defect():
    """``do(a=True, a=False)`` is not a query the graph can fail to
    answer. Reporting it as an identification failure would tell
    ``answer_tier`` no estimand exists and offer the user an RCT."""
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
    _assert_declared_species_reaches_the_report(
        result, "joint:duplicate_treatment", "missing_structural_input",
    )


def test_a_joint_intervention_asking_for_a_decomposition_too_is_a_defect():
    """Joint multi-treatment and mediation decomposition are separate
    operations; a query naming both asks for something v1 does not
    define. Unlike the two above, no amount of graph or data changes
    it."""
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
    _assert_declared_species_reaches_the_report(
        result, "joint:unsupported_layer_combination",
        "missing_structural_input",
    )


def test_a_longitudinal_spec_naming_an_undeclared_variable_is_a_defect():
    """The spec's covariate block references a variable the graph never
    declares. The g-formula is not unidentified here — it was never
    given a well-formed history to check."""
    def _s(pred: str) -> dict:
        return _a(pred, "subj")

    result = _run({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "subj"}]},
        "options": {"longitudinal": {
            "estimator": "gformula",
            "treatments": ["A0", "A1"],
            "confounders_by_time": [["L0"], ["NOPE"]],
            "outcome": "Y",
            "strategy_treated": 1, "strategy_control": 0,
            "n_sim": 100, "ci_bootstrap": 0,
        }},
        "statements": [
            {"kind": "variable", "predicate": "L0"},
            {"kind": "variable", "predicate": "A0", "domain": [True, False]},
            {"kind": "variable", "predicate": "A1", "domain": [True, False]},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": _s("A0"), "to": _s("Y")},
            {"kind": "cause", "from": _s("A1"), "to": _s("Y")},
            {"kind": "cause", "from": _s("L0"), "to": _s("A0")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _s("Y"), "value": True},
                "intervention": {"atom": _s("A1"), "value": True},
                "given": [],
            }},
        ],
    })
    _assert_declared_species_reaches_the_report(
        result, "longitudinal:atom_not_in_graph:NOPE",
        "missing_structural_input",
    )


# ---------------------------------------------------------------------------
# The vocabulary is closed
# ---------------------------------------------------------------------------


def test_a_missing_item_cannot_name_a_species_outside_the_vocabulary():
    """``GapKind`` also covers caveats read off the program — a learned
    graph, a weak instrument. Those are not shortfalls anything ran into,
    and an item claiming one would bind to a renderer that has no item to
    render."""
    from themis.types import GapKind, MissingItem, MissingKind, Priority

    with pytest.raises(ValueError, match="not one of the species"):
        MissingItem(
            kind=MissingKind.STRUCTURE,
            name="whatever",
            priority=Priority.HIGH,
            gap=GapKind.GRAPH_LEARNED_FROM_DATA,
        )


def test_the_species_is_required():
    """A producer that leaves it out is the defect the field removes, so
    it is not something a default can quietly stand in for."""
    from themis.types import MissingItem, MissingKind, Priority

    with pytest.raises(TypeError, match="gap"):
        MissingItem(
            kind=MissingKind.STRUCTURE,
            name="whatever",
            priority=Priority.HIGH,
        )
