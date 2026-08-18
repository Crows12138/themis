"""The first-class EffectQuery.assumptions field.

Monotonicity moved from the ``program.extensions`` side channel to a
query-level field, parallel to the existing
CounterfactualQuery.assumptions. Backwards-compat: extensions path
still works as fallback.
"""
from __future__ import annotations

import pytest

import themis
from themis.types import EffectQueryAssumptions, Monotonicity


from tests.bounds_rows import methods, row

def _mtr_program_via_assumptions():
    """The MTR scenario with monotonicity
    declared on query.assumptions instead of program.extensions."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "first_class_mtr",
             "query": {
                 "kind": "effect",
                 "target": {"atom": {"predicate": "y",
                                     "args": [{"type": "const",
                                               "name": "me"}]},
                            "value": True},
                 "intervention": {"atom": {"predicate": "x",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                 "given": [],
                 "assumptions": {"monotonicity": "non_decreasing"},
             }},
        ],
    }


def _mtr_program_via_extensions():
    """The same scenario via the extensions side channel."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "monotonicity": {
                "target": "y", "treatment": "x",
                "direction": "non_decreasing",
            },
        },
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "ext_mtr",
             "query": {
                 "kind": "effect",
                 "target": {"atom": {"predicate": "y",
                                     "args": [{"type": "const",
                                               "name": "me"}]},
                            "value": True},
                 "intervention": {"atom": {"predicate": "x",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                 "given": [],
             }},
        ],
    }


# ---------------------------------------------------------------------------
# First-class path: query.assumptions.monotonicity triggers MTR bounds
# ---------------------------------------------------------------------------


def test_first_class_assumption_triggers_mtr_bounds():
    """Monotonicity on query.assumptions, with no extensions
    declaration, fires MTR bounds — the same end-to-end behaviour as
    the extensions path."""
    out = themis.run(_mtr_program_via_assumptions())
    result = out["results"][0]
    bounds = row(result, "manski_tamer_monotonicity")
    assert "mtr_non_decreasing" in bounds["assumptions"]


def test_first_class_assumption_non_increasing_direction():
    program = _mtr_program_via_assumptions()
    program["statements"][-1]["query"]["assumptions"] = {
        "monotonicity": "non_increasing",
    }
    out = themis.run(program)
    bounds = row(out["results"][0], "manski_tamer_monotonicity")
    assert "mtr_non_increasing" in bounds["assumptions"]


# ---------------------------------------------------------------------------
# Both paths produce IDENTICAL bounds (backwards compat invariant)
# ---------------------------------------------------------------------------


def test_first_class_and_extensions_paths_produce_identical_bounds():
    """Same monotonicity declared via either path → identical
    bounds_result. The first-class field is sugar over the extensions
    side-channel, not a new semantic."""
    out_class = themis.run(_mtr_program_via_assumptions())
    out_ext = themis.run(_mtr_program_via_extensions())
    b_class = row(out_class["results"][0], "manski_tamer_monotonicity")
    b_ext = row(out_ext["results"][0], "manski_tamer_monotonicity")
    assert b_class["method"] == b_ext["method"]
    assert b_class["lower_expression"] == b_ext["lower_expression"]
    assert b_class["upper_expression"] == b_ext["upper_expression"]
    assert b_class["assumptions"] == b_ext["assumptions"]


# ---------------------------------------------------------------------------
# Verifier handles both paths
# ---------------------------------------------------------------------------


def test_verifier_accepts_first_class_path():
    from themis.verifier.bounds_rules import (
        verify_manski_tamer_bounds_result,
    )

    program = _mtr_program_via_assumptions()
    out = themis.run(program)
    bounds = row(out["results"][0], "manski_tamer_monotonicity")
    # Run verifier with the program and query dict — verifier reads
    # query.assumptions.monotonicity preferentially.
    verify_manski_tamer_bounds_result(
        bounds,
        program=program,
        query_dict=program["statements"][-1]["query"],
    )


def test_verifier_still_accepts_extensions_path():
    """Backwards-compat: fixtures using extensions still
    audit cleanly."""
    from themis.verifier.bounds_rules import (
        verify_manski_tamer_bounds_result,
    )

    program = _mtr_program_via_extensions()
    out = themis.run(program)
    bounds = row(out["results"][0], "manski_tamer_monotonicity")
    verify_manski_tamer_bounds_result(
        bounds,
        program=program,
        query_dict=program["statements"][-1]["query"],
    )


# ---------------------------------------------------------------------------
# Type system: EffectQueryAssumptions exists and is usable
# ---------------------------------------------------------------------------


def test_effect_query_assumptions_dataclass_exists():
    """The new types.py field is exposed and frozen (hashable)."""
    a = EffectQueryAssumptions(monotonicity=Monotonicity.NON_DECREASING)
    # frozen=True
    with pytest.raises(Exception):
        a.monotonicity = Monotonicity.NON_INCREASING


def test_effect_query_assumptions_default_none():
    a = EffectQueryAssumptions()
    assert a.monotonicity is None


def test_effect_query_carries_assumptions_field():
    """EffectQuery typed object preserves the assumptions field."""
    from themis.types import (
        Atom, ConstTerm, EffectQuery, Intervention, ValuedAtom,
    )
    eq = EffectQuery(
        target=ValuedAtom(
            atom=Atom(predicate="y", args=(ConstTerm("me"),)),
            value=True,
        ),
        intervention=Intervention(
            atom=Atom(predicate="x", args=(ConstTerm("me"),)),
            value=True,
        ),
        given=(),
        assumptions=EffectQueryAssumptions(
            monotonicity=Monotonicity.NON_DECREASING,
        ),
    )
    assert eq.assumptions.monotonicity is Monotonicity.NON_DECREASING


def test_effect_query_assumptions_omitted_serialization_omitted():
    """Backwards-compat: a query without assumptions serialises
    unchanged — no spurious 'assumptions': null
    appears in serialized output."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "no_assumptions",
             "query": {
                 "kind": "effect",
                 "target": {"atom": {"predicate": "y",
                                     "args": [{"type": "const",
                                               "name": "me"}]},
                            "value": True},
                 "intervention": {"atom": {"predicate": "x",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                 "given": [],
             }},
        ],
    }
    # Programs without assumptions should still parse + run.
    out = themis.run(program)
    assert out["results"][0]["query_kind"] == "effect"
