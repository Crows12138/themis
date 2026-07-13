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
  query appear in the expression. For the NUMERIC end (when data was
  supplied), it additionally RE-DERIVES the ACE interval: the producer
  records the empirical P(X=x, Y=y | Z=z) table under
  ``sufficient_statistics.P_xyz`` and this module re-runs an
  independently-transcribed response-function LP over it, rejecting a
  bound that isn't what the LP yields — plus a closed-form check of
  Balke-Pearl's instrumental inequalities on the recorded table.
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

    _audit_numeric_bounds(
        bounds_result, method="manski_tamer_monotonicity",
        rule="bounds_manski_tamer",
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

    Cardinality-agnostic in the treatment (candidate C): the bound is on a
    single arm, so the intervention may be a bool OR a multi-valued numeric
    level. For a bool treatment the off-arm mass is the single concrete
    other arm ``P(X=¬x)``; for a multi-valued level it is the pooled
    inequality ``P(X≠x)``.

    Raises ``VerificationError`` on:
    - method-field mismatch
    - non-bool, non-numeric intervention value (no well-defined arm event)
    - lower / upper expression doesn't match the canonical pattern
    - assumptions tuple is non-empty (Manski natural by definition
      makes no claim — non-empty signals tampering)
    - (numeric end) a lower / upper value that isn't what the recorded arm
      counts yield, or counts that violate the arm partition
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

    # bool is a subtype of int, so check bool FIRST — a bool treatment is a
    # valid arm; a non-bool numeric value is a valid multi-valued arm; a
    # string / other has no well-defined arm event.
    if not isinstance(intervention_val, (bool, int, float)):
        raise VerificationError(
            "Manski natural bounds require a bool or numeric intervention "
            f"value (a discrete arm); got {intervention_val!r}",
            step_index=None, rule="bounds_manski_natural",
        )

    target_val_str = _fmt_value(target_val)
    intervention_val_str = _fmt_value(intervention_val)
    other_arm_mass = _complement_mass_expr(intervention_pred, intervention_val)

    expected_lower = (
        f"P({target_pred}={target_val_str} | "
        f"{intervention_pred}={intervention_val_str})"
        f" · P({intervention_pred}={intervention_val_str})"
    )
    expected_upper = f"{expected_lower} + {other_arm_mass}"

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

    _audit_numeric_bounds(
        bounds_result, method="manski_natural", rule="bounds_manski_natural",
    )
    _rederive_manski_natural_numeric(bounds_result)


def _complement_mass_expr(pred: str, value) -> str:
    """Independently transcribed off-arm mass ``P(X≠x)`` for the Manski
    natural interval's width. Bool → the single concrete other arm
    ``P(X=¬x)``; numeric multi-valued level → the pooled inequality
    ``P(X≠x)``. Mirrors ``output/bounds._complement_mass`` but re-derived
    here (verifier independence pin — must not import the producer)."""
    if isinstance(value, bool):
        return f"P({pred}={_fmt_value(not value)})"
    return f"P({pred}≠{_fmt_value(value)})"


def _rederive_manski_natural_numeric(bounds_result: dict) -> None:
    """Strong re-derivation of the Manski natural arm interval from the
    recorded arm counts — the treatment-cardinality-agnostic analogue of
    the Balke-Pearl P_xyz re-derivation.

    The producer records ``sufficient_statistics``
    ``{"n", "n_joint_target_arm", "n_other_arm"}`` — the three counts the
    closed form consumes: ``lower = n_joint/n``, ``upper = (n_joint +
    n_other)/n``, ``width = n_other/n``. This verifier re-derives the
    interval from those counts alone (no DataFrame, no producer import) and
    rejects a reported bound that doesn't match, plus the partition
    invariant ``n_joint + n_other ≤ n`` (the target arm and the off-arm are
    disjoint, and the joint count is a subset of the target arm). This is
    what makes a MULTI-VALUED treatment's pooled off-arm mass auditable: a
    fabricated width that a metadata-only audit would pass is caught because
    ``n_other`` must reproduce it. Skipped when no counts are recorded
    (symbolic-only, or an older producer / a different method's stats).

    A self-consistent forgery of the counts + interval is the honest ceiling
    (the verifier has no data to re-count from) — same posture as
    ``_rederive_balke_pearl_numeric``.
    """
    stats = bounds_result.get("sufficient_statistics")
    if not isinstance(stats, dict):
        return
    if "n_joint_target_arm" not in stats and "n_other_arm" not in stats:
        return  # not the Manski-natural shape (e.g. Balke-Pearl's P_xyz)

    rule = "bounds_manski_natural"
    n = stats.get("n")
    n_joint = stats.get("n_joint_target_arm")
    n_other = stats.get("n_other_arm")
    for name, v in (
        ("n", n), ("n_joint_target_arm", n_joint), ("n_other_arm", n_other),
    ):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise VerificationError(
                f"Manski natural sufficient_statistics.{name} must be a "
                f"non-negative int; got {v!r}", step_index=None, rule=rule,
            )
    if n == 0:
        raise VerificationError(
            "Manski natural sufficient_statistics.n is 0 (empty sample); the "
            "arm interval is undefined", step_index=None, rule=rule,
        )
    # The recorded count total must match the audited sample_size (both are
    # len(data)); a divergence signals tampered statistics.
    sample_size = bounds_result.get("sample_size")
    if isinstance(sample_size, int) and not isinstance(sample_size, bool) \
            and sample_size != n:
        raise VerificationError(
            f"Manski natural sufficient_statistics.n ({n}) disagrees with "
            f"sample_size ({sample_size}); both should be the row count",
            step_index=None, rule=rule,
        )
    if n_joint + n_other > n:
        raise VerificationError(
            f"Manski natural counts violate the arm partition: "
            f"n_joint_target_arm ({n_joint}) + n_other_arm ({n_other}) "
            f"exceeds n ({n}); the target arm and off-arm are disjoint and "
            "the joint count is a subset of the target arm",
            step_index=None, rule=rule,
        )

    exp_lower = n_joint / n
    exp_upper = (n_joint + n_other) / n
    reported_lo = bounds_result.get("lower_value")
    reported_hi = bounds_result.get("upper_value")
    if reported_lo is None or reported_hi is None:
        raise VerificationError(
            "Manski natural recorded sufficient_statistics but no numeric "
            "lower_value / upper_value to verify against",
            step_index=None, rule=rule,
        )
    tol = 1e-9
    if abs(exp_lower - reported_lo) > tol + 1e-9 * abs(reported_lo):
        raise VerificationError(
            f"Manski natural lower_value {reported_lo} does not match the "
            f"value re-derived from the recorded arm counts "
            f"(n_joint/n = {exp_lower}); the reported bound is not what the "
            "closed form yields on those counts",
            step_index=None, rule=rule,
        )
    if abs(exp_upper - reported_hi) > tol + 1e-9 * abs(reported_hi):
        raise VerificationError(
            f"Manski natural upper_value {reported_hi} does not match the "
            f"value re-derived from the recorded arm counts "
            f"((n_joint+n_other)/n = {exp_upper})",
            step_index=None, rule=rule,
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

    _audit_numeric_bounds(
        bounds_result, method="balke_pearl_iv", rule="bounds_balke_pearl_iv",
    )
    _rederive_balke_pearl_numeric(bounds_result)


# Balke-Pearl response-function model, transcribed INDEPENDENTLY here (this
# module must not import estimation/bounds_numeric.py). X responds to Z with 4
# canonical types, Y responds to X with 4 — 16 joint types.
#   X-type i: 0 never (X≡0)  1 complier (X≡Z)  2 defier (X≡1−Z)  3 always (X≡1)
#   Y-type j: 0 (Y≡0)        1 (Y≡X)           2 (Y≡1−X)         3 (Y≡1)
def _v_fx(i: int, z: int) -> int:
    return (0, z, 1 - z, 1)[i]


def _v_gy(j: int, x: int) -> int:
    return (0, x, 1 - x, 1)[j]


def _rederive_balke_pearl_numeric(bounds_result: dict) -> None:
    """Strong re-derivation of the Balke-Pearl ACE interval from the recorded
    P(X=x, Y=y | Z=z) table.

    The producer records ``sufficient_statistics.P_xyz`` (the empirical 2x2x2
    conditional table the response-function LP consumed). This verifier
    re-runs an INDEPENDENTLY-transcribed response-function LP over that table
    and rejects a mismatch with the reported ``lower_value`` / ``upper_value``
    — so a tampered bound (e.g. a falsely-tight interval) is caught, not just
    range/width-audited. Also re-checks that the recorded table is a valid
    conditional distribution and satisfies Balke-Pearl's instrumental
    inequalities (eq 6) — the closed-form falsifiability test, computed
    without the LP. Skipped when no P_xyz is recorded (symbolic-only, or an
    older producer). Independence pin: does not import the producer.

    A self-consistent forgery of the whole table + interval is the honest
    ceiling (the verifier has no DataFrame to re-count the table from).
    """
    stats = bounds_result.get("sufficient_statistics")
    if not isinstance(stats, dict):
        return
    raw = stats.get("P_xyz")
    if raw is None:
        return

    import numpy as np

    rule = "bounds_balke_pearl_iv"
    try:
        P = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        raise VerificationError(
            "Balke-Pearl sufficient_statistics.P_xyz must be a numeric 2x2x2 "
            f"array; got {raw!r}", step_index=None, rule=rule,
        )
    if P.shape != (2, 2, 2):
        raise VerificationError(
            f"Balke-Pearl P_xyz must have shape (2,2,2); got {P.shape}",
            step_index=None, rule=rule,
        )
    if np.any(P < -1e-9):
        raise VerificationError(
            "Balke-Pearl P_xyz has a negative probability entry",
            step_index=None, rule=rule,
        )
    # Each Z-slice is a conditional distribution over (X, Y): must sum to 1.
    for z in (0, 1):
        s = float(P[z].sum())
        if abs(s - 1.0) > 1e-6:
            raise VerificationError(
                f"Balke-Pearl P_xyz[Z={z}] sums to {s}, not 1 (not a "
                "conditional distribution)", step_index=None, rule=rule,
            )

    # Closed-form instrumental inequalities (Balke-Pearl 1997 eq 6): the
    # binary IV model is refuted if any exceeds 1. Independent of the LP.
    ineqs = (
        P[0, 0, 0] + P[1, 0, 1],
        P[0, 1, 0] + P[1, 1, 1],
        P[0, 0, 1] + P[1, 0, 0],
        P[0, 1, 1] + P[1, 1, 0],
    )
    worst = max(ineqs)
    if worst > 1.0 + 1e-6:
        raise VerificationError(
            f"Balke-Pearl recorded P_xyz violates an instrumental inequality "
            f"(max = {worst:.4f} > 1); the table is incompatible with a valid "
            "binary IV model, so the bounds could not have come from it",
            step_index=None, rule=rule,
        )

    lo, hi = _verifier_bp_bounds_from_P(P, rule)
    reported_lo = bounds_result.get("lower_value")
    reported_hi = bounds_result.get("upper_value")
    if reported_lo is None or reported_hi is None:
        raise VerificationError(
            "Balke-Pearl recorded sufficient_statistics but no numeric "
            "lower_value / upper_value to verify against",
            step_index=None, rule=rule,
        )
    tol = 1e-6
    if abs(lo - reported_lo) > tol + 1e-6 * abs(reported_lo):
        raise VerificationError(
            f"Balke-Pearl lower_value {reported_lo} does not match the interval "
            f"re-derived from the recorded P(X,Y|Z) table ({lo}); the reported "
            "bound is not what the response-function LP yields on that table",
            step_index=None, rule=rule,
        )
    if abs(hi - reported_hi) > tol + 1e-6 * abs(reported_hi):
        raise VerificationError(
            f"Balke-Pearl upper_value {reported_hi} does not match the interval "
            f"re-derived from the recorded P(X,Y|Z) table ({hi})",
            step_index=None, rule=rule,
        )


def _verifier_bp_bounds_from_P(P, rule: str) -> tuple[float, float]:
    """Sharp ACE bounds by an independently-transcribed LP over the 16-type
    simplex. ``P[z,x,y] = P(X=x, Y=y | Z=z)``. Returns (lower, upper)."""
    import numpy as np
    from scipy.optimize import linprog

    # ACE contribution per (i, j) type = g(j,1) − g(j,0) = [0, 1, −1, 0][j].
    ace_coef = np.array(
        [_v_gy(j, 1) - _v_gy(j, 0) for _i in range(4) for j in range(4)],
        dtype=float,
    )
    rows: list = []
    b: list = []
    for z in (0, 1):
        for x in (0, 1):
            for y in (0, 1):
                row = np.zeros(16)
                for i in range(4):
                    for j in range(4):
                        if _v_fx(i, z) == x and _v_gy(j, _v_fx(i, z)) == y:
                            row[i * 4 + j] = 1.0
                rows.append(row)
                b.append(float(P[z, x, y]))
    rows.append(np.ones(16))
    b.append(1.0)
    A_eq = np.asarray(rows)
    b_eq = np.asarray(b)
    simplex = [(0.0, None)] * 16
    lo = linprog(ace_coef, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    hi = linprog(-ace_coef, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    if not (lo.success and hi.success):
        raise VerificationError(
            "Balke-Pearl re-derivation LP is infeasible on the recorded "
            "P(X,Y|Z) table — no response-type distribution reproduces it, so "
            "the table cannot have produced sharp bounds",
            step_index=None, rule=rule,
        )
    return float(lo.fun), float(-hi.fun)


_NUMERIC_ESTIMAND_BY_METHOD = {
    "manski_natural": ("arm_probability", (0.0, 1.0)),
    "manski_tamer_monotonicity": ("arm_probability", (0.0, 1.0)),
    "balke_pearl_iv": ("ace", (-1.0, 1.0)),
}


def _audit_numeric_bounds(bounds_result: dict, *, method: str, rule: str) -> None:
    """Metadata self-consistency audit of the numeric end of a bounds_result
    (produced by ``estimation/bounds_numeric.py`` when data is supplied).

    The verifier has NO DataFrame, so this is a relaxed audit — direction,
    admissible range, estimand/method agreement, CI containment, hash +
    sample-size shape — NOT a re-evaluation on data (same posture as the
    numeric_estimate verifier rules). Skipped entirely when the numeric
    fields are absent (symbolic-only bounds). Independence pin preserved:
    does not import the producer.
    """
    lower = bounds_result.get("lower_value")
    upper = bounds_result.get("upper_value")
    if lower is None and upper is None:
        return  # symbolic-only; nothing numeric to audit
    eps = 1e-9
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        raise VerificationError(
            f"numeric bounds must have numeric lower_value / upper_value; got "
            f"{lower!r} / {upper!r}", step_index=None, rule=rule,
        )
    if lower > upper + eps:
        raise VerificationError(
            f"numeric bounds inverted: lower_value {lower} > upper_value "
            f"{upper}", step_index=None, rule=rule,
        )
    estimand_expected, (lo_r, hi_r) = _NUMERIC_ESTIMAND_BY_METHOD[method]
    if lower < lo_r - eps or upper > hi_r + eps:
        raise VerificationError(
            f"numeric bounds [{lower}, {upper}] fall outside the admissible "
            f"range [{lo_r}, {hi_r}] for estimand {estimand_expected!r}",
            step_index=None, rule=rule,
        )
    estimand = bounds_result.get("estimand")
    if estimand != estimand_expected:
        raise VerificationError(
            f"numeric bounds estimand {estimand!r} does not match method "
            f"{method!r} (expected {estimand_expected!r})",
            step_index=None, rule=rule,
        )
    width = bounds_result.get("width")
    if width is not None and abs(width - (upper - lower)) > 1e-6:
        raise VerificationError(
            f"numeric bounds width {width} != upper_value − lower_value "
            f"{upper - lower}", step_index=None, rule=rule,
        )
    ci_lower = bounds_result.get("ci_lower")
    ci_upper = bounds_result.get("ci_upper")
    if ci_lower is not None and ci_upper is not None:
        # The outer band must ENCLOSE the point-estimated interval.
        if ci_lower > lower + 1e-6 or ci_upper < upper - 1e-6:
            raise VerificationError(
                f"numeric bounds CI [{ci_lower}, {ci_upper}] does not enclose "
                f"the interval [{lower}, {upper}] (outer band must contain it)",
                step_index=None, rule=rule,
            )
        if ci_lower > ci_upper + eps:
            raise VerificationError(
                f"numeric bounds CI inverted: {ci_lower} > {ci_upper}",
                step_index=None, rule=rule,
            )
        ci_level = bounds_result.get("ci_level")
        if not isinstance(ci_level, (int, float)) or not (0.0 < ci_level < 1.0):
            raise VerificationError(
                f"numeric bounds ci_level must be in (0, 1); got {ci_level!r}",
                step_index=None, rule=rule,
            )
    h = bounds_result.get("numeric_data_hash")
    if h is not None and (not isinstance(h, str) or len(h) != 64):
        raise VerificationError(
            f"numeric_data_hash must be a 64-char hex string; got {h!r}",
            step_index=None, rule=rule,
        )
    ss = bounds_result.get("sample_size")
    if ss is not None and (not isinstance(ss, int) or isinstance(ss, bool) or ss < 10):
        raise VerificationError(
            f"numeric bounds sample_size must be an int ≥ 10; got {ss!r}",
            step_index=None, rule=rule,
        )
    if method == "balke_pearl_iv":
        instrument = bounds_result.get("instrument")
        if not isinstance(instrument, str) or not instrument:
            raise VerificationError(
                "numeric Balke-Pearl bounds must name the instrument column",
                step_index=None, rule=rule,
            )


def _fmt_value(v: object) -> str:
    """Stringify a bool / numeric / str value the same way bounds.py
    does — but re-implemented here so the verifier doesn't import the
    producer (independence pin)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
