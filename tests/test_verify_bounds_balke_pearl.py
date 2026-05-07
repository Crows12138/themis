"""Iter 130 — verifier rule for Balke-Pearl IV bounds (Phase 12 producer).

Completes the verifier-layer trilogy for the 3 implemented BoundsMethod
producers (MN + MTR + BP-IV ✓; frontdoor_partial is aspirational).

Producer emits a compact symbolic reference (not 16 spelled-out linear
combinations); verifier audits:
- canonical 'max over 8' / 'min over 8' phrase intact
- target / treatment predicates from query appear in expression
- iv1/iv2/iv3 assumption tag set is exact
- conditioning slot after '|' has a non-empty instrument variable
"""
from __future__ import annotations

import ast
import inspect

import pytest

from themis.verifier.bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# Byte-code independence (parallel to T10 + iter 126/127 pin)
# ---------------------------------------------------------------------------


def test_bounds_rules_independence_pin_holds_for_bp_too():
    """Module-level pin: never import themis.output.bounds (parallel
    to T10's independence pin). Iter 130 added a third function;
    re-test ensures it didn't accidentally import."""
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


def _expected_bp_bounds(target_pred="y", treatment_pred="x", z="z"):
    return {
        "method": "balke_pearl_iv",
        "lower_expression": (
            f"max over 8 Balke-Pearl lower terms "
            f"(linear combos of P({target_pred}, {treatment_pred} | {z}); "
            f"see Balke-Pearl 1997 §3)"
        ),
        "upper_expression": (
            f"min over 8 Balke-Pearl upper terms "
            f"(linear combos of P({target_pred}, {treatment_pred} | {z}); "
            f"same observables as lower)"
        ),
        "assumptions": [
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ],
        "data_required": [
            f"P({target_pred}, {treatment_pred} | {z})  # 8 probabilities for binary triple",
        ],
        "width_when_uninformative": False,
        "notes": "Balke-Pearl (1997) bounds on ACE = ...",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_accepts_canonical_bp_bounds():
    bounds = _expected_bp_bounds()
    verify_balke_pearl_iv_bounds_result(
        bounds, query_dict=_query_dict(),
    )


def test_accepts_alternative_predicate_names():
    """Verifier must work for any (target, treatment, z) substitution."""
    bounds = _expected_bp_bounds(
        target_pred="cancer", treatment_pred="smoking", z="card_lottery",
    )
    query = _query_dict(
        target_pred="cancer", intervention_pred="smoking",
    )
    verify_balke_pearl_iv_bounds_result(bounds, query_dict=query)


# ---------------------------------------------------------------------------
# Tampered bounds — verifier must catch
# ---------------------------------------------------------------------------


def test_rejects_wrong_method_field():
    bounds = _expected_bp_bounds()
    bounds["method"] = "manski_natural"
    with pytest.raises(VerificationError, match="expected 'balke_pearl_iv'"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_lower_with_wrong_phrase():
    """Tamper the canonical phrase → reject."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = bounds["lower_expression"].replace(
        "max over 8 Balke-Pearl lower terms",
        "min over 8 fake phrase",
    )
    with pytest.raises(VerificationError, match="canonical 'max over 8"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_upper_with_wrong_phrase():
    bounds = _expected_bp_bounds()
    bounds["upper_expression"] = "garbage upper expression"
    with pytest.raises(VerificationError, match="canonical 'min over 8"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_lower_swapped_with_upper():
    """Swap lower/upper → at least one starting-phrase check fires."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"], bounds["upper_expression"] = (
        bounds["upper_expression"],
        bounds["lower_expression"],
    )
    with pytest.raises(VerificationError, match="canonical"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_lower_missing_target_predicate():
    """Tampering: keep canonical phrase but strip target pred → catch."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = (
        "max over 8 Balke-Pearl lower terms (some other content)"
    )
    with pytest.raises(VerificationError, match="reference target predicate"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_lower_missing_treatment_predicate():
    bounds = _expected_bp_bounds()
    # Construct lower that has y but not x.
    bounds["lower_expression"] = (
        "max over 8 Balke-Pearl lower terms (P(y, other | z); ...)"
    )
    bounds["upper_expression"] = (
        "min over 8 Balke-Pearl upper terms (P(y, other | z); ...)"
    )
    with pytest.raises(VerificationError, match="reference treatment predicate"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_lower_missing_instrument_conditioning():
    """Lower expression has P(y, x) but no | <z> → reject."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = (
        "max over 8 Balke-Pearl lower terms (P(y, x); see ...)"
    )
    with pytest.raises(VerificationError, match="instrument variable"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_missing_iv1_assumption():
    bounds = _expected_bp_bounds()
    bounds["assumptions"] = [
        a for a in bounds["assumptions"] if "iv1" not in a
    ]
    with pytest.raises(VerificationError, match="iv1/iv2/iv3 set"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_extra_assumption_tag():
    bounds = _expected_bp_bounds()
    bounds["assumptions"] = list(bounds["assumptions"]) + [
        "monotonicity_first_stage_for_late",  # not BP's set
    ]
    with pytest.raises(VerificationError, match="iv1/iv2/iv3 set"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=_query_dict(),
        )


def test_rejects_non_string_target_predicate():
    bounds = _expected_bp_bounds()
    query = {
        "target": {"atom": {"predicate": 42}, "value": True},
        "intervention": {"atom": {"predicate": "x"}, "value": True},
        "given": [],
    }
    with pytest.raises(VerificationError, match="string target / treatment"):
        verify_balke_pearl_iv_bounds_result(
            bounds, query_dict=query,
        )


# ---------------------------------------------------------------------------
# E2E via real producer output
# ---------------------------------------------------------------------------


def _bp_program():
    """ADMG with binary IV: z → x, x → y, latent u between x and y
    (declared as bidirected). BP-IV bounds fire on the effect query."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "bidirected", "forall": ["I"],
             "left": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "bp_e2e",
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


def test_real_bp_program_bounds_pass_verifier_e2e():
    """themis.run on a real BP-IV program emits balke_pearl_iv bounds;
    the new verifier audits cleanly via direct call (themis.verify
    rejects derivation-less results so the wired path is dormant for
    needs_investigation status — same posture as iter 126/127)."""
    import themis

    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == "balke_pearl_iv"
    verify_balke_pearl_iv_bounds_result(
        result["bounds_result"],
        query_dict=program["statements"][-1]["query"],
    )


def test_real_bp_program_tampered_phrase_caught_e2e():
    import themis

    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "fake lower"
    with pytest.raises(VerificationError, match="canonical 'max over 8"):
        verify_balke_pearl_iv_bounds_result(
            result["bounds_result"],
            query_dict=program["statements"][-1]["query"],
        )


def test_re_exported_from_themis_verifier():
    import themis.verifier as v
    assert "verify_balke_pearl_iv_bounds_result" in v.__all__
    assert v.verify_balke_pearl_iv_bounds_result is \
        verify_balke_pearl_iv_bounds_result


# ---------------------------------------------------------------------------
# Trilogy completion sanity
# ---------------------------------------------------------------------------


def test_all_implemented_bounds_methods_have_verifier():
    """Iter 130 milestone: every BoundsMethod value with a real
    producer in themis/output/bounds.py has a dedicated verifier
    function in themis/verifier/bounds_rules.py.

    BoundsMethod values (4 total):
    - manski_natural ✓ producer (Phase 12) ✓ verifier (iter 127)
    - balke_pearl_iv ✓ producer (Phase 12) ✓ verifier (iter 130)
    - manski_tamer_monotonicity ✓ producer (iter 119) ✓ verifier (iter 126)
    - frontdoor_partial ✗ producer (aspirational) → no verifier needed
    """
    from themis.types import BoundsMethod
    import themis.verifier.bounds_rules as br

    # Producers: read bounds.py for "method=BoundsMethod.X" patterns.
    import re
    bounds_src = inspect.getsource(
        __import__("themis.output.bounds", fromlist=["bounds"])
    )
    produced_names = set(re.findall(
        r"method=BoundsMethod\.([A-Z_]+)", bounds_src
    ))
    name_to_value = {bm.name: bm.value for bm in BoundsMethod}
    produced_values = {name_to_value[n] for n in produced_names}

    # Each produced method must have a verify_X_bounds_result function.
    name_map = {
        "manski_natural": "verify_manski_natural_bounds_result",
        "balke_pearl_iv": "verify_balke_pearl_iv_bounds_result",
        "manski_tamer_monotonicity": "verify_manski_tamer_bounds_result",
    }
    missing = []
    for value in produced_values:
        verifier_name = name_map.get(value)
        if verifier_name is None:
            missing.append(f"{value} (no expected verifier name mapped)")
            continue
        if not hasattr(br, verifier_name):
            missing.append(f"{value} → {verifier_name}")

    assert not missing, (
        f"BoundsMethod producers missing dedicated verifiers: {missing}. "
        "Iter 126/127/130 trilogy invariant violated."
    )
