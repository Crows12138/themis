"""Iter 126 — verifier rule for Manski-Tamer bounds (iter 119 producer).

Phase 12 + iter 119 produce ``bounds_result`` payloads but until iter
126 they were unverified — themis.verify walked the derivation chain
without re-deriving the bounds. This iter closes the audit gap for
the Manski-Tamer monotonicity producer specifically:

- ``verify_manski_tamer_bounds_result`` re-derives the expected
  ``lower_expression`` / ``upper_expression`` from program shape +
  monotonicity declaration in extensions, asserts equality.
- byte-code independence: the verifier MUST NOT import
  ``themis/output/bounds.py`` (same posture as T10 verifier
  independence).

Tampered-bound tests deliberately mutate the producer's output to
prove the verifier catches every shape of tampering.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from themis.verifier.bounds_rules import verify_manski_tamer_bounds_result
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# Byte-code independence (parallel to T10 pin)
# ---------------------------------------------------------------------------


def test_bounds_rules_does_not_import_output_bounds():
    """Same posture as T10 independence pin: the verifier re-implements
    the formula and must NOT short-circuit by importing the producer."""
    import themis.verifier.bounds_rules as br
    src = inspect.getsource(br)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "output.bounds" not in mod and mod != "themis.output.bounds", (
                f"verifier.bounds_rules must not import themis.output.bounds; "
                f"found `from {mod} import ...` at line {node.lineno}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "output.bounds" not in alias.name, (
                    "verifier.bounds_rules imports themis.output.bounds — "
                    "independence pin violated"
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _query_dict(target_pred="y", target_val=True,
                intervention_pred="x", intervention_val=True):
    return {
        "kind": "effect",
        "target": {
            "atom": {"predicate": target_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "value": target_val,
        },
        "intervention": {
            "atom": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "value": intervention_val,
        },
        "given": [],
    }


def _program_with_monotonicity(direction="non_decreasing",
                               target="y", treatment="x"):
    return {
        "version": "0.1",
        "extensions": {
            "monotonicity": {
                "target": target,
                "treatment": treatment,
                "direction": direction,
            }
        },
    }


def _expected_bounds_dict_treating_high_non_decreasing():
    """do(X=true) under Y(1)>=Y(0): lower tightens to marginal."""
    return {
        "method": "manski_tamer_monotonicity",
        "lower_expression": "P(y=true)",
        "upper_expression": "P(y=true | x=true) · P(x=true) + P(x=false)",
        "assumptions": ["mtr_non_decreasing"],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "Manski-Tamer (Manski 1997) MTR ...",
    }


def _expected_bounds_dict_treating_low_non_decreasing():
    """do(X=false) under Y(1)>=Y(0): upper tightens to marginal."""
    return {
        "method": "manski_tamer_monotonicity",
        "lower_expression": "P(y=true | x=false) · P(x=false)",
        "upper_expression": "P(y=true)",
        "assumptions": ["mtr_non_decreasing"],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "Manski-Tamer (Manski 1997) MTR ...",
    }


# ---------------------------------------------------------------------------
# Happy paths — every direction × intervention combination
# ---------------------------------------------------------------------------


def test_accepts_treating_high_non_decreasing():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=True)
    # Should not raise.
    verify_manski_tamer_bounds_result(
        bounds, program=program, query_dict=query,
    )


def test_accepts_treating_low_non_decreasing():
    bounds = _expected_bounds_dict_treating_low_non_decreasing()
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=False)
    verify_manski_tamer_bounds_result(
        bounds, program=program, query_dict=query,
    )


def test_accepts_treating_high_non_increasing():
    """Y(1)<=Y(0), do(X=true): upper tightens to marginal."""
    bounds = {
        "method": "manski_tamer_monotonicity",
        "lower_expression": "P(y=true | x=true) · P(x=true)",
        "upper_expression": "P(y=true)",
        "assumptions": ["mtr_non_increasing"],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "...",
    }
    program = _program_with_monotonicity("non_increasing")
    query = _query_dict(intervention_val=True)
    verify_manski_tamer_bounds_result(
        bounds, program=program, query_dict=query,
    )


def test_accepts_treating_low_non_increasing():
    """Y(1)<=Y(0), do(X=false): lower tightens to marginal."""
    bounds = {
        "method": "manski_tamer_monotonicity",
        "lower_expression": "P(y=true)",
        "upper_expression": "P(y=true | x=false) · P(x=false) + P(x=true)",
        "assumptions": ["mtr_non_increasing"],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "...",
    }
    program = _program_with_monotonicity("non_increasing")
    query = _query_dict(intervention_val=False)
    verify_manski_tamer_bounds_result(
        bounds, program=program, query_dict=query,
    )


# ---------------------------------------------------------------------------
# Tampered bounds — verifier must catch
# ---------------------------------------------------------------------------


def test_rejects_swapped_lower_upper():
    """Swap lower/upper expressions: should fail since the right side
    no longer matches the canonical pattern for treating_high+non_decr."""
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    bounds["lower_expression"], bounds["upper_expression"] = (
        bounds["upper_expression"],
        bounds["lower_expression"],
    )
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=True)
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_wrong_lower_constant():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    bounds["lower_expression"] = "P(y=false)"  # tampered
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=True)
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_missing_assumption_tag():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    bounds["assumptions"] = []  # tampered
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=True)
    with pytest.raises(VerificationError, match="assumptions must include"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_wrong_method_field():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    bounds["method"] = "manski_natural"
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict()
    with pytest.raises(VerificationError, match="expected 'manski_tamer"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_missing_monotonicity_declaration():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = {"version": "0.1"}  # no extensions
    query = _query_dict()
    with pytest.raises(VerificationError, match="neither.*monotonicity.*provided"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_monotonicity_for_other_pair():
    """Declaration's (target, treatment) doesn't match query's pair."""
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = _program_with_monotonicity(
        "non_decreasing", target="other_y", treatment="x",
    )
    query = _query_dict()
    with pytest.raises(VerificationError, match="no monotonicity declaration matches"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_invalid_direction_string():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = _program_with_monotonicity("monotone-ish")  # garbled
    query = _query_dict()
    with pytest.raises(VerificationError, match="must be 'non_decreasing'"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


def test_rejects_non_bool_intervention_value():
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = _program_with_monotonicity("non_decreasing")
    query = _query_dict(intervention_val=42)
    with pytest.raises(VerificationError, match="boolean intervention value"):
        verify_manski_tamer_bounds_result(
            bounds, program=program, query_dict=query,
        )


# ---------------------------------------------------------------------------
# Declaration-list form
# ---------------------------------------------------------------------------


def test_accepts_list_form_monotonicity_declaration():
    """extensions.monotonicity may be a list of dicts; pick matching."""
    bounds = _expected_bounds_dict_treating_high_non_decreasing()
    program = {
        "version": "0.1",
        "extensions": {
            "monotonicity": [
                {"target": "u", "treatment": "v", "direction": "non_increasing"},
                {"target": "y", "treatment": "x", "direction": "non_decreasing"},
            ],
        },
    }
    query = _query_dict()
    verify_manski_tamer_bounds_result(
        bounds, program=program, query_dict=query,
    )


# ---------------------------------------------------------------------------
# End-to-end through themis.verify
# ---------------------------------------------------------------------------


def _mtr_program():
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
            {"kind": "query", "id": "mtr_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_real_mtr_program_bounds_pass_verifier_e2e():
    """themis.run on a real MTR program emits a bounds_result;
    the new verifier audits it cleanly. (themis.verify itself
    requires a derivation chain which MTR's needs_investigation
    status doesn't carry, so this test calls the bounds verifier
    directly — same coverage as the kernel.verify wire would
    provide for any future MTR-with-derivation case.)"""
    import themis

    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == \
        "manski_tamer_monotonicity"

    # Direct verifier call — accepts the producer's actual output.
    verify_manski_tamer_bounds_result(
        result["bounds_result"],
        program=program,
        query_dict=program["statements"][-1]["query"],
    )


def test_real_mtr_program_tampered_bounds_caught_e2e():
    """End-to-end on real producer output, then mutate
    lower_expression and confirm the verifier rejects."""
    import themis

    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "P(y=false)"
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_tamer_bounds_result(
            result["bounds_result"],
            program=program,
            query_dict=program["statements"][-1]["query"],
        )


def test_re_exported_from_themis_verifier():
    import themis.verifier as v
    assert "verify_manski_tamer_bounds_result" in v.__all__
    assert v.verify_manski_tamer_bounds_result is \
        verify_manski_tamer_bounds_result
