"""Iter 126 — independent verification for ``bounds_result`` payloads.

Phase 12 (Manski natural, Balke-Pearl IV) and iter 119 (Manski-Tamer
monotonicity) both produce ``bounds_result`` blocks via
``themis/output/bounds.py``. Until iter 126 those payloads were
unverified — ``themis.verify`` walked the derivation chain but never
re-derived the bounds.

This module re-implements the bounds expressions independently from
program shape + query metadata + (for MTR) the
``program.extensions['monotonicity']`` declaration. It MUST NOT
import ``themis.output.bounds`` — same posture as T10 verifier
independence (see ``data_gap_rules.py``).

Current scope (iter 126):

- ``verify_manski_tamer_bounds_result`` — the iter 119 producer.
  Re-derives which side tightens (lower vs upper) based on
  monotonicity direction and intervention value, asserts the
  ``lower_expression`` and ``upper_expression`` strings match
  the canonical pattern.

Out of scope this iter (deliberate, well-scoped):

- ``manski_natural`` and ``balke_pearl_iv`` verification are
  follow-ups; kernel.verify continues to leave their bounds
  unaudited until those rules are added.
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

    extensions = program.get("extensions") or {}
    decls = extensions.get("monotonicity")
    if decls is None:
        raise VerificationError(
            "MTR bounds emitted but program.extensions.monotonicity "
            "missing — producer should not have triggered",
            step_index=None, rule="bounds_manski_tamer",
        )
    if isinstance(decls, dict):
        decls = [decls]
    if not isinstance(decls, list):
        raise VerificationError(
            "program.extensions.monotonicity must be a dict or list of "
            "dicts; got " + type(decls).__name__,
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


def _fmt_value(v: object) -> str:
    """Stringify a bool / numeric / str value the same way bounds.py
    does — but re-implemented here so the verifier doesn't import the
    producer (independence pin)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
