"""Phase 6.mediation S.M.2: scheduler integration for mediation queries.

End-to-end tests that `themis.run` correctly routes effect queries with
a ``mediator`` field to the mediation identification path, producing
STRUCTURALLY_SOLVED with ``extensions.mediation_decomposition``.
"""
from __future__ import annotations

import themis


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _effect_query_with_mediator(x, y, m, value=True):
    return {
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom(x), "value": value},
            "target": {"atom": _atom(y), "value": value},
            "given": [],
            "mediator": _atom(m),
        },
    }


def _program(statements):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ================================================= bare mediator


def test_bare_mediator_succeeds_with_nde_nie():
    """X → M → Y, nothing else. Both NDE/NIE and CDE identifiable."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True

    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["mediator"] == "m(me)"
    assert mediation["mediator_valid"] is True
    assert mediation["strategy"] == "nde_nie"
    assert mediation["nde_nie"]["identifiable"] is True
    assert mediation["cde"]["identifiable"] is True

    # Derivation pattern: nde_nie_check → cde_check → identify_via_mediation
    rules = [step["rule"] for step in result["derivation"]["steps"]]
    assert "mediation_nde_nie_check" in rules
    assert "mediation_cde_check" in rules
    assert "identify_via_mediation" in rules


def test_structural_mediation_surfaces_assumptions_when_identifiable():
    """Real-test caught: structural mediation_decomposition reported
    'identifiable: true' without naming what identifiability rests on
    (Pearl 2001 cross-world conditions, sequential ignorability, no
    intermediate confounder, consistency). Renderers had to render
    '可识别' as if unconditional. Now each branch carries an
    `assumptions` list of glossary IDs the renderer translates."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    mediation = out["results"][0]["extensions"]["mediation_decomposition"]

    # NDE/NIE assumptions: Pearl 2001 four conditions + cross-world
    # ignorability + no intermediate confounder + consistency.
    nde_assumptions = mediation["nde_nie"]["assumptions"]
    assert "pearl_2001_four_conditions_hold_on_the_graph" in nde_assumptions
    assert "sequential_ignorability_treatment_and_mediator" in nde_assumptions
    assert "no_intermediate_confounder_affected_by_treatment" in nde_assumptions
    assert "consistency_of_potential_outcomes" in nde_assumptions

    # CDE assumptions: backdoor adjustment for M→Y given X + consistency.
    cde_assumptions = mediation["cde"]["assumptions"]
    assert "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment" in cde_assumptions
    assert "consistency_of_potential_outcomes" in cde_assumptions


def test_structural_mediation_assumptions_empty_when_not_identifiable():
    """Companion: when a branch is not identifiable, no claim is being
    made — the assumptions list is empty rather than misleadingly
    listing unmet preconditions."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("w")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    mediation = out["results"][0]["extensions"]["mediation_decomposition"]
    assert mediation["nde_nie"]["identifiable"] is False
    assert mediation["nde_nie"]["assumptions"] == []
    assert mediation["cde"]["identifiable"] is False
    assert mediation["cde"]["assumptions"] == []


# ===================================== intermediate confounder (M4 violation)


def test_intermediate_confounder_blocks_nde_nie():
    """X → W → M, X → W → Y, X → M, M → Y. W is an X-descendant required
    to block M-Y backdoor. NDE/NIE fails M3 or M4; CDE also fails (W is
    X-descendant so C2 excludes it)."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("w")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["strategy"] == "none"
    assert mediation["nde_nie"]["identifiable"] is False
    assert mediation["nde_nie"]["failed_condition"] in ("M3", "M4")
    assert mediation["cde"]["identifiable"] is False


# ================================================= invalid mediator


def test_invalid_mediator_returns_needs_investigation():
    """Mediator atom is in the graph but not on any X → ... → Y path."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "extra", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        # M connected only to "extra" — in graph but not on X→Y path
        {"kind": "cause", "from": _atom("m"), "to": _atom("extra")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "needs_investigation"
    missing_names = [m["name"] for m in result["missing_information"]]
    assert "mediation:invalid_mediator" in missing_names

    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["mediator_valid"] is False


# ================================================= mediator atom missing


def test_missing_mediator_atom_reports_structure_error():
    """Mediator references an undeclared atom."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "undeclared_mediator"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "needs_investigation"
    missing_names = [m["name"] for m in result["missing_information"]]
    assert any("undeclared_mediator" in n for n in missing_names)


# ================================================= observed M-Y confounder


def test_observed_my_confounder_adjustment_in_extensions():
    """U → M, U → Y, X → M → Y. NDE/NIE succeeds with W = {U}."""
    ast = _program([
        {"kind": "variable", "predicate": "u", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("u"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("u"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        _effect_query_with_mediator("x", "y", "m"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["strategy"] == "nde_nie"
    assert "u(me)" in mediation["nde_nie"]["adjustment"]


# ================================================= no mediator field == no mediation path


def test_effect_without_mediator_still_runs_total_effect():
    """Sanity: an effect query without ``mediator`` still takes the
    normal backdoor path and doesn't accidentally hit mediation."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {
            "kind": "query",
            "id": "q",
            "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            },
        },
    ])

    out = themis.run(ast)
    result = out["results"][0]
    # No mediation extensions leak in
    if "extensions" in result and result["extensions"] is not None:
        assert "mediation_decomposition" not in result["extensions"]
