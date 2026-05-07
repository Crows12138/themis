"""Iter 126/127/130 — independent verification for ``bounds_result`` payloads.

Phase 12 (Manski natural, Balke-Pearl IV) and iter 119 (Manski-Tamer
monotonicity) all produce ``bounds_result`` blocks via
``themis/output/bounds.py``. Before iter 126 those payloads were
unverified — ``themis.verify`` walked the derivation chain but never
re-derived the bounds.

This module re-implements the bounds expressions independently from
program shape + query metadata + (for MTR) the
``program.extensions['monotonicity']`` declaration. It MUST NOT
import ``themis.output.bounds`` — same posture as T10 verifier
independence (see ``data_gap_rules.py``).

Current scope (verifier trilogy complete for the 3 implemented
BoundsMethod producers; the 4th enum value ``frontdoor_partial`` is
aspirational with no producer yet):

- ``verify_manski_tamer_bounds_result`` (iter 126) — re-derives
  which side tightens (lower vs upper) based on monotonicity
  direction and intervention value.
- ``verify_manski_natural_bounds_result`` (iter 127) — re-derives
  the canonical ``P(Y | X) · P(X)`` lower / ``+ P(¬X)`` upper.
- ``verify_balke_pearl_iv_bounds_result`` (iter 130) — checks the
  canonical reference-shape lower/upper expressions, the iv1/iv2/iv3
  assumption tag set, and that target/treatment predicates from the
  query appear in the expression. Doesn't re-derive the 16 linear
  combinations (the producer emits a compact reference rather than
  spelling them out — auditing that reference's shape is a smaller
  but real check).
"""
from __future__ import annotations

from .errors import VerificationError


def verify_manski_tamer_bounds_result(
    bounds_result: dict,
    *,
    program: dict,
    query_dict: dict,
) -> None:
    """Re-derive the expected MTR bounds expressions and assert
    agreement with the claimed payload.

    Raises ``VerificationError`` on:
    - missing / malformed ``program.extensions.monotonicity`` declaration
      that should have triggered MTR
    - declaration's (target, treatment) doesn't match the query
    - lower / upper expression doesn't match the canonical pattern
      for the given monotonicity direction × intervention value combo
    - method field is wrong (caller bug; defensive guard)
    """
    if bounds_result.get("method") != "manski_tamer_monotonicity":
        raise VerificationError(
            f"verify_manski_tamer_bounds_result called with method "
            f"{bounds_result.get('method')!r}; expected "
            "'manski_tamer_monotonicity'",
            step_index=None, rule="bounds_manski_tamer",
        )

    target = query_dict.get("target", {})
    intervention = query_dict.get("intervention", {})
    target_atom = target.get("atom", {})
    intervention_atom = intervention.get("atom", {})

    target_pred = target_atom.get("predicate")
    intervention_pred = intervention_atom.get("predicate")
    target_val = target.get("value")
    intervention_val = intervention.get("value")

    if not isinstance(intervention_val, bool):
        raise VerificationError(
            "MTR bounds require a boolean intervention value; "
            f"got {intervention_val!r}",
            step_index=None, rule="bounds_manski_tamer",
        )

    # Iter 131: prefer first-class query.assumptions.monotonicity;
    # fall back to iter 119's program.extensions.monotonicity hack.
    direction = None
    query_assumptions = query_dict.get("assumptions")
    if isinstance(query_assumptions, dict):
        direction = query_assumptions.get("monotonicity")

    if direction is None:
        extensions = program.get("extensions") or {}
        decls = extensions.get("monotonicity")
        if decls is None:
            raise VerificationError(
                "MTR bounds emitted but neither "
                "query.assumptions.monotonicity nor "
                "program.extensions.monotonicity provided — "
                "producer should not have triggered",
                step_index=None, rule="bounds_manski_tamer",
            )
        if isinstance(decls, dict):
            decls = [decls]
        if not isinstance(decls, list):
            raise VerificationError(
                "program.extensions.monotonicity must be a dict or "
                "list of dicts; got " + type(decls).__name__,
                step_index=None, rule="bounds_manski_tamer",
            )
        matching = None
        for d in decls:
            if not isinstance(d, dict):
                continue
            if (
                d.get("target") == target_pred
                and d.get("treatment") == intervention_pred
            ):
                matching = d
                break
        if matching is None:
            raise VerificationError(
                f"no monotonicity declaration matches the query's "
                f"(target={target_pred!r}, treatment={intervention_pred!r}) "
                "pair — MTR bounds shouldn't have fired",
                step_index=None, rule="bounds_manski_tamer",
            )
        direction = matching.get("direction")

    if direction not in ("non_decreasing", "non_increasing"):
        raise VerificationError(
            f"monotonicity direction must be 'non_decreasing' or "
            f"'non_increasing'; got {direction!r}",
            step_index=None, rule="bounds_manski_tamer",
        )

    # Independent re-derivation of which side tightens.
    # MTR Y(1) >= Y(0) (non_decreasing):
    #   - do(X=1): lower tightens to marginal; upper unchanged
    #   - do(X=0): upper tightens to marginal; lower unchanged
    # MTR Y(1) <= Y(0) (non_increasing): direction-flipped.
    treating_high = bool(intervention_val)
    direction_increases_y = direction == "non_decreasing"
    tighten_lower = treating_high == direction_increases_y

    # Canonical expressions (must match bounds.py output verbatim — the
    # producer and verifier agree on the symbolic form, but each derives
    # it independently from the same input metadata).
    target_val_str = _fmt_value(target_val)
    intervention_val_str = _fmt_value(intervention_val)
    other_arm_val_str = _fmt_value(not intervention_val)

    same_arm = (
        f"P({target_pred}={target_val_str} | "
        f"{intervention_pred}={intervention_val_str})"
        f" · P({intervention_pred}={intervention_val_str})"
    )
    other_arm_mass = f"P({intervention_pred}={other_arm_val_str})"
    target_marginal = f"P({target_pred}={target_val_str})"
    manski_upper = f"{same_arm} + {other_arm_mass}"

    if tighten_lower:
        expected_lower = target_marginal
        expected_upper = manski_upper
    else:
        expected_lower = same_arm
        expected_upper = target_marginal

    actual_lower = bounds_result.get("lower_expression")
    actual_upper = bounds_result.get("upper_expression")

    if actual_lower != expected_lower:
        raise VerificationError(
            f"MTR bounds lower_expression mismatch.\n"
            f"  expected: {expected_lower!r}\n"
            f"  actual:   {actual_lower!r}",
            step_index=None, rule="bounds_manski_tamer",
        )
    if actual_upper != expected_upper:
        raise VerificationError(
            f"MTR bounds upper_expression mismatch.\n"
            f"  expected: {expected_upper!r}\n"
            f"  actual:   {actual_upper!r}",
            step_index=None, rule="bounds_manski_tamer",
        )

    # Assumption tag must name the MTR direction so the renderer can
    # surface "under direction X" without re-reading the program.
    assumptions = bounds_result.get("assumptions") or []
    expected_assumption_tag = f"mtr_{direction}"
    if expected_assumption_tag not in assumptions:
        raise VerificationError(
            f"MTR bounds assumptions must include {expected_assumption_tag!r}; "
            f"got {list(assumptions)!r}",
            step_index=None, rule="bounds_manski_tamer",
        )


def verify_manski_natural_bounds_result(
    bounds_result: dict,
    *,
    query_dict: dict,
) -> None:
    """Iter 127 — re-derive the expected Manski natural (1990) bounds
    expressions and assert agreement with the claimed payload.

    Manski natural is the assumption-free baseline:
    ``P(Y=y | do(X=x)) ∈ [P(Y=y|X=x)·P(X=x),
                          P(Y=y|X=x)·P(X=x) + P(X≠x)]``

    Raises ``VerificationError`` on:
    - method-field mismatch
    - non-bool intervention value (Manski natural for non-binary X is
      out of scope per the producer)
    - lower / upper expression doesn't match the canonical pattern
    - assumptions tuple is non-empty (Manski natural by definition
      makes no claim — non-empty signals tampering)
    """
    if bounds_result.get("method") != "manski_natural":
        raise VerificationError(
            f"verify_manski_natural_bounds_result called with method "
            f"{bounds_result.get('method')!r}; expected 'manski_natural'",
            step_index=None, rule="bounds_manski_natural",
        )

    target = query_dict.get("target", {})
    intervention = query_dict.get("intervention", {})
    target_atom = target.get("atom", {})
    intervention_atom = intervention.get("atom", {})

    target_pred = target_atom.get("predicate")
    intervention_pred = intervention_atom.get("predicate")
    target_val = target.get("value")
    intervention_val = intervention.get("value")

    if not isinstance(intervention_val, bool):
        raise VerificationError(
            "Manski natural bounds require a boolean intervention value; "
            f"got {intervention_val!r}",
            step_index=None, rule="bounds_manski_natural",
        )

    target_val_str = _fmt_value(target_val)
    intervention_val_str = _fmt_value(intervention_val)
    other_arm_val_str = _fmt_value(not intervention_val)

    expected_lower = (
        f"P({target_pred}={target_val_str} | "
        f"{intervention_pred}={intervention_val_str})"
        f" · P({intervention_pred}={intervention_val_str})"
    )
    expected_upper = (
        f"{expected_lower} + P({intervention_pred}={other_arm_val_str})"
    )

    actual_lower = bounds_result.get("lower_expression")
    actual_upper = bounds_result.get("upper_expression")

    if actual_lower != expected_lower:
        raise VerificationError(
            f"Manski natural lower_expression mismatch.\n"
            f"  expected: {expected_lower!r}\n"
            f"  actual:   {actual_lower!r}",
            step_index=None, rule="bounds_manski_natural",
        )
    if actual_upper != expected_upper:
        raise VerificationError(
            f"Manski natural upper_expression mismatch.\n"
            f"  expected: {expected_upper!r}\n"
            f"  actual:   {actual_upper!r}",
            step_index=None, rule="bounds_manski_natural",
        )

    # Manski natural is the assumption-free baseline; the producer
    # emits assumptions=() (or []). Anything non-empty signals tampering
    # or a producer bug.
    assumptions = bounds_result.get("assumptions") or []
    if assumptions:
        raise VerificationError(
            f"Manski natural is the assumption-free baseline; "
            f"assumptions tuple must be empty, got {list(assumptions)!r}",
            step_index=None, rule="bounds_manski_natural",
        )


_BP_EXPECTED_ASSUMPTIONS = frozenset({
    "iv1_relevance",
    "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
    "iv3_independence_instrument_independent_of_unmeasured_confounders",
})


def verify_balke_pearl_iv_bounds_result(
    bounds_result: dict,
    *,
    query_dict: dict,
) -> None:
    """Iter 130 — audit the Balke-Pearl IV bounds (Phase 12 producer).

    Producer emits a compact symbolic reference rather than the 16
    linear combinations spelled out:

        lower = "max over 8 Balke-Pearl lower terms (linear combos of
                 P({target}, {treatment} | {z}); see Balke-Pearl
                 1997 §3)"
        upper = "min over 8 Balke-Pearl upper terms (linear combos of
                 P({target}, {treatment} | {z}); same observables as
                 lower)"
        assumptions = (iv1_relevance, iv2_exclusion_..., iv3_
                       independence_...)

    The verifier re-derives the canonical reference-shape and asserts:
    - method == "balke_pearl_iv"
    - lower / upper start with the canonical "max over 8" / "min over 8"
      Balke-Pearl phrase
    - lower / upper expressions reference the query's target and
      treatment predicates
    - assumption tuple contains exactly the iv1/iv2/iv3 tag set

    The instrument predicate Z is not in the EffectQuery — dispatch
    detects it from extensions.iv_identification or graph shape — so
    the verifier doesn't re-derive Z. It does check that the
    expression substring after the ``|`` clause has SOMETHING (any
    non-empty predicate name), as a smoke test that producer didn't
    forget the conditioning variable.

    Does not check the 16 numeric linear combinations themselves —
    those are deferred to a future numeric audit when a Balke-Pearl
    numeric estimator lands. This is conservative-on-purpose: the
    producer emits a reference, the verifier audits the reference's
    structure.
    """
    if bounds_result.get("method") != "balke_pearl_iv":
        raise VerificationError(
            f"verify_balke_pearl_iv_bounds_result called with method "
            f"{bounds_result.get('method')!r}; expected 'balke_pearl_iv'",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    target = query_dict.get("target", {})
    intervention = query_dict.get("intervention", {})
    target_pred = target.get("atom", {}).get("predicate")
    treatment_pred = intervention.get("atom", {}).get("predicate")

    if not isinstance(target_pred, str) or not isinstance(treatment_pred, str):
        raise VerificationError(
            "Balke-Pearl IV bounds require string target / treatment "
            "predicates in the query",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    actual_lower = bounds_result.get("lower_expression") or ""
    actual_upper = bounds_result.get("upper_expression") or ""

    if not actual_lower.startswith("max over 8 Balke-Pearl lower terms"):
        raise VerificationError(
            f"Balke-Pearl IV lower_expression must start with the "
            f"canonical 'max over 8 Balke-Pearl lower terms' phrase; "
            f"got: {actual_lower!r}",
            step_index=None, rule="bounds_balke_pearl_iv",
        )
    if not actual_upper.startswith("min over 8 Balke-Pearl upper terms"):
        raise VerificationError(
            f"Balke-Pearl IV upper_expression must start with the "
            f"canonical 'min over 8 Balke-Pearl upper terms' phrase; "
            f"got: {actual_upper!r}",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    # Both expressions must reference the query's target + treatment
    # predicates (the producer substitutes them into the expression).
    for expr_name, expr in (("lower", actual_lower), ("upper", actual_upper)):
        if target_pred not in expr:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression must reference "
                f"target predicate {target_pred!r}; got: {expr!r}",
                step_index=None, rule="bounds_balke_pearl_iv",
            )
        if treatment_pred not in expr:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression must reference "
                f"treatment predicate {treatment_pred!r}; got: {expr!r}",
                step_index=None, rule="bounds_balke_pearl_iv",
            )

    # The lower expression has the form
    #   "... P(target, treatment | z); see ..."
    # — extract the substring between "| " and ")" to confirm a
    # non-empty conditioning variable name (smoke test for instrument).
    import re
    m = re.search(
        r"P\(" + re.escape(target_pred) + r",\s*"
        + re.escape(treatment_pred) + r"\s*\|\s*([^)]+?)\)",
        actual_lower,
    )
    if m is None or not m.group(1).strip():
        raise VerificationError(
            f"Balke-Pearl IV lower_expression must reference an "
            f"instrument variable in the form "
            f"'P({target_pred}, {treatment_pred} | <z>)'; got: "
            f"{actual_lower!r}",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    actual_assumptions = frozenset(bounds_result.get("assumptions") or [])
    if actual_assumptions != _BP_EXPECTED_ASSUMPTIONS:
        missing = _BP_EXPECTED_ASSUMPTIONS - actual_assumptions
        extra = actual_assumptions - _BP_EXPECTED_ASSUMPTIONS
        raise VerificationError(
            f"Balke-Pearl IV assumptions must be the iv1/iv2/iv3 set. "
            f"Missing: {sorted(missing)!r}; extra: {sorted(extra)!r}",
            step_index=None, rule="bounds_balke_pearl_iv",
        )


def _fmt_value(v: object) -> str:
    """Stringify a bool / numeric / str value the same way bounds.py
    does — but re-implemented here so the verifier doesn't import the
    producer (independence pin)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
