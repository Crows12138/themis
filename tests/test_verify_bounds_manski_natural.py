"""Iter 127 — verifier rule for Manski natural bounds (Phase 12 producer).

Parallel to iter 126's MTR verifier — closes the audit gap for the
second BoundsMethod producer. Manski natural is the assumption-free
baseline:

    P(Y=y | do(X=x)) ∈ [P(Y=y|X=x)·P(X=x),  P(Y=y|X=x)·P(X=x) + P(X≠x)]

The verifier re-derives both expressions from the query metadata and
asserts equality with the producer's output. Byte-code independence
pin: the verifier MUST NOT import themis.output.bounds.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from themis.verifier.bounds_rules import (
    verify_manski_natural_bounds_result,
)
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# Byte-code independence (still holds — checks the MN function too)
# ---------------------------------------------------------------------------


def test_bounds_rules_does_not_import_output_bounds_for_mn_either():
    """Re-assert iter 126's independence pin now that iter 127 added
    a second function. The pin is on the MODULE, not per-function,
    but explicit re-test ensures iter 127 didn't accidentally import."""
    import themis.verifier.bounds_rules as br
    src = inspect.getsource(br)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "output.bounds" not in mod
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "output.bounds" not in alias.name


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


def _expected_mn_bounds(target_val=True, intervention_val=True):
    target_str = "true" if target_val else "false"
    int_str = "true" if intervention_val else "false"
    other_str = "false" if intervention_val else "true"
    lower = (
        f"P(y={target_str} | x={int_str}) · P(x={int_str})"
    )
    upper = f"{lower} + P(x={other_str})"
    return {
        "method": "manski_natural",
        "lower_expression": lower,
        "upper_expression": upper,
        "assumptions": [],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "Manski (1990) natural bounds...",
    }


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_accepts_canonical_treating_high():
    bounds = _expected_mn_bounds(target_val=True, intervention_val=True)
    query = _query_dict(intervention_val=True)
    verify_manski_natural_bounds_result(bounds, query_dict=query)


def test_accepts_canonical_treating_low():
    bounds = _expected_mn_bounds(target_val=True, intervention_val=False)
    query = _query_dict(intervention_val=False)
    verify_manski_natural_bounds_result(bounds, query_dict=query)


def test_accepts_target_value_false():
    bounds = _expected_mn_bounds(target_val=False, intervention_val=True)
    query = _query_dict(target_val=False, intervention_val=True)
    verify_manski_natural_bounds_result(bounds, query_dict=query)


# ---------------------------------------------------------------------------
# Tampered bounds — verifier must catch
# ---------------------------------------------------------------------------


def test_rejects_swapped_lower_upper():
    bounds = _expected_mn_bounds()
    bounds["lower_expression"], bounds["upper_expression"] = (
        bounds["upper_expression"],
        bounds["lower_expression"],
    )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_wrong_lower_constant():
    bounds = _expected_mn_bounds()
    bounds["lower_expression"] = "P(y=false | x=true) · P(x=true)"  # tampered
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_wrong_upper_other_arm_term():
    bounds = _expected_mn_bounds()
    # Replace P(x=false) with P(x=true) — invalid.
    bounds["upper_expression"] = bounds["upper_expression"].replace(
        "P(x=false)", "P(x=true)",
    )
    with pytest.raises(VerificationError, match="upper_expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_non_empty_assumptions_tuple():
    """Manski natural is the no-assumption baseline; non-empty
    assumptions signals tampering or producer bug."""
    bounds = _expected_mn_bounds()
    bounds["assumptions"] = ["mtr_non_decreasing"]  # tampered
    with pytest.raises(VerificationError, match="assumption-free baseline"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_wrong_method_field():
    bounds = _expected_mn_bounds()
    bounds["method"] = "balke_pearl_iv"
    with pytest.raises(VerificationError, match="expected 'manski_natural'"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_non_bool_intervention_value():
    bounds = _expected_mn_bounds()
    query = _query_dict(intervention_val=42)
    with pytest.raises(VerificationError, match="boolean intervention"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=query,
        )


# ---------------------------------------------------------------------------
# End-to-end through themis.run + themis.verify
# ---------------------------------------------------------------------------


def _confounded_program():
    """Hidden u → x and u → y, plus x → y. Backdoor identification
    fails (no observable adjustment for u); the bounds layer fires
    Manski natural since no MTR / IV declaration exists."""
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
            {"kind": "query", "id": "mn_e2e",
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


def test_real_manski_natural_bounds_pass_verifier_e2e():
    """themis.run on a confounded program emits Manski natural bounds;
    the new verifier audits cleanly via direct call (themis.verify
    rejects derivation-less results so the wired path is dormant for
    needs_investigation status — same posture as iter 126)."""
    import themis

    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == "manski_natural"
    verify_manski_natural_bounds_result(
        result["bounds_result"],
        query_dict=program["statements"][-1]["query"],
    )


def test_real_manski_natural_tampered_caught_e2e():
    import themis

    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "P(y=false)"  # tamper
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        verify_manski_natural_bounds_result(
            result["bounds_result"],
            query_dict=program["statements"][-1]["query"],
        )


def test_re_exported_from_themis_verifier():
    import themis.verifier as v
    assert "verify_manski_natural_bounds_result" in v.__all__
    assert v.verify_manski_natural_bounds_result is \
        verify_manski_natural_bounds_result
