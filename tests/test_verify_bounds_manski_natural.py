"""Verifier rule for the Manski natural bounds (Phase 12 producer).

Parallel to the MTR verifier — closes the audit gap for the
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
    """Re-assert the independence pin for this second function. The
    pin is on the MODULE, not per-function, and an explicit re-test
    is what makes a new function's import visible here."""
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


def _v(val):
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _expected_mn_bounds(target_val=True, intervention_val=True):
    target_str = "true" if target_val else "false"
    int_str = _v(intervention_val)
    # Bool treatment → single concrete other arm P(x=¬x); multi-valued
    # numeric level → pooled inequality P(x≠x).
    if isinstance(intervention_val, bool):
        other = f"P(x={'false' if intervention_val else 'true'})"
    else:
        other = f"P(x≠{int_str})"
    lower = (
        f"P(y={target_str} | x={int_str}) · P(x={int_str})"
    )
    upper = f"{lower} + {other}"
    return {
        "method": "manski_natural",
        "lower_expression": lower,
        "upper_expression": upper,
        "assumptions": [],
        "data_required": ["P(y, x)"],
        "width_when_uninformative": False,
        "notes": "Manski (1990) natural bounds...",
    }


def _numeric_mn_bounds(n, n_joint, n_other, *, target_val=True,
                       intervention_val=True):
    """A Manski natural bounds_result carrying the numeric end + the arm
    counts, for exercising the strong count re-derivation."""
    b = _expected_mn_bounds(target_val, intervention_val)
    lower = n_joint / n
    upper = (n_joint + n_other) / n
    b.update({
        "estimand": "arm_probability",
        "lower_value": lower,
        "upper_value": upper,
        "width": upper - lower,
        "numeric_uninformative": (n_other / n) >= 1.0 - 1e-9,
        "sample_size": n,
        "numeric_data_hash": "a" * 64,
        "sufficient_statistics": {
            "n": n, "n_joint_target_arm": n_joint, "n_other_arm": n_other},
    })
    return b


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


def test_rejects_binary_shaped_expr_for_multivalued_intervention():
    # A multi-valued intervention paired with binary-shaped expressions
    # (P(x=false)) is a genuine mismatch — the complement is P(x≠42).
    bounds = _expected_mn_bounds()  # binary shape
    query = _query_dict(intervention_val=42)
    with pytest.raises(VerificationError, match="expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=query,
        )


def test_rejects_string_intervention_value():
    # A non-bool, non-numeric intervention has no well-defined arm event.
    bounds = _expected_mn_bounds(intervention_val="high")
    query = _query_dict(intervention_val="high")
    with pytest.raises(VerificationError, match="bool or numeric"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=query,
        )


# ---------------------------------------------------------------------------
# Multi-valued treatment (candidate C) — symbolic
# ---------------------------------------------------------------------------


def test_accepts_multivalued_intervention():
    # do(x=2) on a 3-level treatment: complement is the pooled P(x≠2).
    bounds = _expected_mn_bounds(intervention_val=2)
    assert bounds["upper_expression"].endswith("+ P(x≠2)")
    verify_manski_natural_bounds_result(
        bounds, query_dict=_query_dict(intervention_val=2),
    )


def test_multivalued_rejects_wrong_complement_level():
    # Tamper the pooled complement to a different level P(x≠1).
    bounds = _expected_mn_bounds(intervention_val=2)
    bounds["upper_expression"] = bounds["upper_expression"].replace(
        "P(x≠2)", "P(x≠1)")
    with pytest.raises(VerificationError, match="upper_expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


def test_multivalued_rejects_binary_complement_form():
    # A multi-valued arm must NOT render the binary "P(x=<other>)" form.
    bounds = _expected_mn_bounds(intervention_val=2)
    bounds["upper_expression"] = bounds["upper_expression"].replace(
        "P(x≠2)", "P(x=0)")
    with pytest.raises(VerificationError, match="upper_expression mismatch"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


# ---------------------------------------------------------------------------
# Numeric end — strong count re-derivation
# ---------------------------------------------------------------------------


def test_numeric_rederivation_accepts_honest_counts():
    bounds = _numeric_mn_bounds(4000, 1605, 2005, intervention_val=2)
    verify_manski_natural_bounds_result(
        bounds, query_dict=_query_dict(intervention_val=2),
    )


def test_numeric_rederivation_rejects_fabricated_count():
    bounds = _numeric_mn_bounds(4000, 1605, 2005, intervention_val=2)
    # Keep lower/upper but lie about the off-arm count → re-derivation fails.
    bounds["sufficient_statistics"]["n_other_arm"] = 1500
    with pytest.raises(VerificationError, match="does not match"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


def test_numeric_rederivation_rejects_partition_violation():
    # Honest in-range interval, but the recorded counts are inflated so
    # n_joint + n_other > n — the metadata audit (range/width) passes and
    # only the partition invariant in the re-derivation catches it.
    bounds = _numeric_mn_bounds(4000, 1605, 2005, intervention_val=2)
    bounds["sufficient_statistics"]["n_joint_target_arm"] = 3000
    bounds["sufficient_statistics"]["n_other_arm"] = 2000  # 5000 > 4000
    with pytest.raises(VerificationError, match="arm partition"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


def test_numeric_rederivation_rejects_count_sample_size_mismatch():
    bounds = _numeric_mn_bounds(4000, 1605, 2005, intervention_val=2)
    bounds["sample_size"] = 3999  # disagrees with recorded n
    with pytest.raises(VerificationError, match="disagrees with sample_size"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


def test_numeric_rederivation_rejects_negative_count():
    bounds = _numeric_mn_bounds(4000, 1605, 2005, intervention_val=2)
    bounds["sufficient_statistics"]["n_other_arm"] = -5
    with pytest.raises(VerificationError, match="non-negative int"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=2),
        )


def test_numeric_rederivation_binary_case_also_covered():
    # The count re-derivation applies to the binary arm too (strengthens the
    # pre-existing metadata-only audit). Tamper the joint count while the
    # reported interval stays self-consistent (width = n_other/n untouched):
    # only the re-derivation catches the divergence from the reported point.
    bounds = _numeric_mn_bounds(2000, 700, 900, intervention_val=True)
    verify_manski_natural_bounds_result(
        bounds, query_dict=_query_dict(intervention_val=True),
    )
    bounds["sufficient_statistics"]["n_joint_target_arm"] = 500
    with pytest.raises(VerificationError, match="does not match"):
        verify_manski_natural_bounds_result(
            bounds, query_dict=_query_dict(intervention_val=True),
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
    needs_investigation status — same posture as its sibling)."""
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


def _confounded_multivalued_program(intervention_val=2):
    """Hidden u → x and u → y, plus x → y, with x a 3-level discrete
    treatment {0,1,2}. Point ID fails; Manski natural fires on do(x=2)."""
    prog = _confounded_program()
    prog["statements"].insert(
        0, {"kind": "variable", "predicate": "x", "domain": [0, 1, 2]})
    prog["statements"][-1]["query"]["intervention"]["value"] = intervention_val
    return prog


def test_real_multivalued_manski_natural_bounds_pass_verifier_e2e():
    import themis

    program = _confounded_multivalued_program(2)
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == "manski_natural"
    assert "P(x≠2)" in result["bounds_result"]["upper_expression"]
    verify_manski_natural_bounds_result(
        result["bounds_result"],
        query_dict=program["statements"][-1]["query"],
    )


def test_re_exported_from_themis_verifier():
    import themis.verifier as v
    assert "verify_manski_natural_bounds_result" in v.__all__
    assert v.verify_manski_natural_bounds_result is \
        verify_manski_natural_bounds_result
