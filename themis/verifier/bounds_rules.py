"""Independent verification for one ``bounds_results`` row.

Manski natural, Balke-Pearl IV and Manski-Tamer monotonicity all produce
rows via ``themis/output/bounds.py``. Walking the
derivation chain says nothing about them: a chain can be well-formed
around an interval nobody re-computed.

This module re-implements the bounds expressions independently from
program shape + query metadata + (for MTR) the
``program.extensions['monotonicity']`` declaration. It MUST NOT
import ``themis.output.bounds`` — same posture as T10 verifier
independence (see ``data_gap_rules.py``).

Current scope (verifier trilogy complete for the 3 implemented
BoundsMethod producers; the 4th enum value ``frontdoor_partial`` is
aspirational with no producer yet):

- ``verify_manski_tamer_bounds_result`` — re-derives which side
  tightens (lower vs upper) based on monotonicity direction and
  intervention value.
- ``verify_manski_natural_bounds_result`` — re-derives the canonical
  ``P(Y | X) · P(X)`` lower / ``+ P(¬X)`` upper.
- ``verify_balke_pearl_iv_bounds_result`` — reads the row's facts
  (estimand, instrument, iv1/iv2/iv3 tag set) and checks the instrument
  against what the graph offers, rather than recovering it out of the
  expression with a regular expression; the expressions are then held
  only to naming what they render. For the NUMERIC end (when data was
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

    # Prefer the first-class query.assumptions.monotonicity; fall back
    # to the older program.extensions.monotonicity side channel.
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

    # Independent re-derivation of which side tightens, from TWO facts about
    # two different variables.
    #
    # ``up`` is about X: does intervening at this arm move Y up, for the units
    # observed at the other one. The outcome's order is about Y: MTR is a
    # claim about that order, the bound is on the EVENT ``Y=y``, and
    # ``1{Y=y}`` is monotone in Y only at the TOP of the order — reversed at
    # the bottom, monotone in neither direction in between. So the polarity
    # deciding the side is ``up`` XOR "y is the extreme in that direction".
    #
    # This rule used to read ``up`` alone, here and in both producer layers —
    # three independent derivations reaching the same wrong answer, because
    # all three lacked the same input and each substituted the one polarity it
    # did hold. Which is why the order is read here from the program rather
    # than taken from the payload: a fact that nobody has is not made present
    # by being asked for three times.
    up = bool(intervention_val) == (direction == "non_decreasing")
    levels = _declared_outcome_order(program, target_pred, target_val, rule=(
        "bounds_manski_tamer"))
    y_rank = levels.index(target_val)
    forces = y_rank == (len(levels) - 1 if up else 0)
    collapses = y_rank == (0 if up else len(levels) - 1)

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
    reachable_mass = (
        f"P({target_pred} {'≤' if up else '≥'} {target_val_str}, "
        f"{intervention_pred}={other_arm_val_str})"
    )

    expected_lower = target_marginal if forces else same_arm
    if forces:
        expected_upper = f"{same_arm} + {other_arm_mass}"
    elif collapses:
        expected_upper = target_marginal
    else:
        expected_upper = f"{same_arm} + {reachable_mass}"

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

    # The words the note beside it shows a reader, held to what was just
    # derived here rather than to a second derivation of it — this is the
    # one fact in the file whose absence made three surfaces agree on a
    # wrong answer, so the side is passed, never recomputed.
    from .bounds_account_rules import verify_the_words_a_tightened_side_uses
    verify_the_words_a_tightened_side_uses(
        bounds_result,
        direction=direction,
        side="lower" if forces else "upper" if collapses else None,
        tightened_to=target_marginal if (forces or collapses) else None,
    )

    _audit_numeric_bounds(
        bounds_result, method="manski_tamer_monotonicity",
        rule="bounds_manski_tamer",
    )
    _rederive_manski_tamer_numeric(
        bounds_result, levels=levels, y_rank=y_rank, up=up,
        rule="bounds_manski_tamer",
    )


def _declared_outcome_order(
    program: dict, predicate: str, value: object, *, rule: str,
) -> list:
    """The outcome's levels low to high, as this module reads the program.

    Restated rather than imported, like every other re-derivation here, and
    for once that duplication is the point: the order is the fact whose
    absence made three surfaces agree on a wrong rule, so the check that
    matters is whether a SECOND reader of the program arrives at the same one.

    The type's own order wins where the type has one — ``domain: [true,
    false]`` is how these programs habitually list a boolean and does not make
    ``false`` the higher level — and the declaration's written order stands
    where it does not, because for a labelled column that is the only order
    there is. ``scale: nominal`` is how a program says there is none.

    A bound that got this far without an order is not a looser bound but an
    arbitrary one, so it is rejected rather than skipped.
    """
    scale = None
    domain = None
    for stmt in program.get("statements", []):
        if not isinstance(stmt, dict) or stmt.get("kind") != "variable":
            continue
        if stmt.get("predicate") == predicate:
            scale = stmt.get("scale")
            domain = stmt.get("domain")
            break
    if scale == "nominal":
        raise VerificationError(
            f"MTR bounds were emitted for outcome {predicate!r}, which the "
            f"program declares nominal — its levels have no order, and "
            f"'monotone in an unordered variable' is not a weaker assumption "
            f"but an empty one",
            step_index=None, rule=rule,
        )
    if domain is None:
        if not isinstance(value, bool):
            raise VerificationError(
                f"MTR bounds were emitted for outcome {predicate!r} with no "
                f"declared domain and a non-boolean target {value!r}; which "
                f"side the assumption tightens depends on where that value "
                f"sits in the outcome's order, and nothing here states one",
                step_index=None, rule=rule,
            )
        domain = [False, True]
    levels = list(domain)
    if all(isinstance(v, (bool, int, float)) for v in levels):
        levels = sorted(levels)
    if len(levels) < 2 or value not in levels:
        raise VerificationError(
            f"MTR bounds were emitted for the event {predicate}={value!r}, "
            f"which is not among the outcome's declared levels {levels!r}; "
            f"where it sits in the order is what decides the bound",
            step_index=None, rule=rule,
        )
    return levels


def _rederive_manski_tamer_numeric(
    bounds_result: dict, *, levels: list, y_rank: int, up: bool, rule: str,
) -> None:
    """Strong re-derivation of the MTR arm interval — and of the contrast —
    from the recorded ``(X, Y)`` counts.

    The producer records the joint table together with the level lists it read
    it in, so this rule can recompute the closed form instead of auditing the
    payload's shape. The level lists are checked against the order derived
    HERE from the program: a producer that read a different order is the exact
    failure this item was about, and it is now a disagreement rather than a
    second silent answer.

    A self-consistent forgery of the counts is the honest ceiling — the
    verifier has no data to re-count from, same posture as
    :func:`_rederive_balke_pearl_numeric`.
    """
    contrast = bounds_result.get("contrast")
    raw = bounds_result.get("sufficient_statistics")
    stats: dict = raw if isinstance(raw, dict) else {}
    table = stats.get("n_xy")
    if table is None:
        if contrast is not None:
            raise VerificationError(
                "Manski-Tamer reported a contrast without the joint counts it "
                "is derived from; the interval a reader is shown for the "
                "quantity they asked about would rest on nothing this "
                "verifier can recompute",
                step_index=None, rule=rule,
            )
        return
    recorded = stats.get("outcome_levels")
    if list(recorded or []) != [
            _envelope_like(v) for v in levels]:
        raise VerificationError(
            f"Manski-Tamer recorded the outcome order as {recorded!r}; the "
            f"program declares {levels!r}. Which side the assumption tightens "
            f"is decided by where the target event sits in that order, so two "
            f"orders are two different bounds",
            step_index=None, rule=rule,
        )
    x_levels = stats.get("treatment_levels")
    if not isinstance(x_levels, list) or not x_levels:
        raise VerificationError(
            "Manski-Tamer sufficient_statistics.treatment_levels must list "
            "the arms the counts are indexed by",
            step_index=None, rule=rule,
        )
    if not isinstance(table, list) or len(table) != len(x_levels) or not all(
            isinstance(row, list) and len(row) == len(levels) for row in table):
        raise VerificationError(
            f"Manski-Tamer sufficient_statistics.n_xy must be a "
            f"{len(x_levels)}×{len(levels)} table over the recorded levels",
            step_index=None, rule=rule,
        )
    counts = [[_require_nonneg_int(
        c, label="Manski-Tamer sufficient_statistics.n_xy", rule=rule)
        for c in row] for row in table]
    n = _require_nonneg_int(
        stats.get("n"), label="Manski-Tamer sufficient_statistics.n", rule=rule)
    total = sum(sum(row) for row in counts)
    if total != n:
        raise VerificationError(
            f"Manski-Tamer counts total {total} but sufficient_statistics.n is "
            f"{n}; every row of the sample falls in exactly one cell",
            step_index=None, rule=rule,
        )
    if n == 0:
        raise VerificationError(
            "Manski-Tamer sufficient_statistics.n is 0 (empty sample); the "
            "arm interval is undefined", step_index=None, rule=rule,
        )
    sample_size = bounds_result.get("sample_size")
    if isinstance(sample_size, int) and not isinstance(sample_size, bool) \
            and sample_size != n:
        raise VerificationError(
            f"Manski-Tamer sufficient_statistics.n ({n}) disagrees with "
            f"sample_size ({sample_size}); both should be the row count",
            step_index=None, rule=rule,
        )
    xi = stats.get("arm_treatment_index")
    yi = stats.get("arm_outcome_index")
    if not isinstance(xi, int) or isinstance(xi, bool) \
            or not 0 <= xi < len(x_levels):
        raise VerificationError(
            f"Manski-Tamer sufficient_statistics.arm_treatment_index {xi!r} "
            f"does not name a row of the recorded table",
            step_index=None, rule=rule,
        )
    if yi != y_rank:
        raise VerificationError(
            f"Manski-Tamer recorded the target event at position {yi!r} of the "
            f"outcome order; the program's own order puts it at {y_rank}",
            step_index=None, rule=rule,
        )

    def arm(index: int, pushes_up: bool) -> tuple[float, float]:
        same = counts[index][y_rank]
        other = [row for i, row in enumerate(counts) if i != index]
        if pushes_up:
            reach = sum(sum(row[: y_rank + 1]) for row in other)
            extreme = y_rank == len(levels) - 1
        else:
            reach = sum(sum(row[y_rank:]) for row in other)
            extreme = y_rank == 0
        forced = sum(row[y_rank] for row in other) if extreme else 0
        return (same + forced) / n, (same + reach) / n

    exp_lo, exp_hi = arm(xi, up)
    for key, want in (("lower_value", exp_lo), ("upper_value", exp_hi)):
        got = bounds_result.get(key)
        if not isinstance(got, (int, float)) or isinstance(got, bool) \
                or abs(want - got) > 1e-9 + 1e-9 * abs(got):
            raise VerificationError(
                f"Manski-Tamer {key} is {got!r}; the recorded counts and the "
                f"declared outcome order give {want}",
                step_index=None, rule=rule,
            )
    if contrast is None:
        return
    if len(x_levels) != 2:
        raise VerificationError(
            f"Manski-Tamer reported an ACE contrast on a {len(x_levels)}-arm "
            f"treatment; with no single other arm there is no baseline the "
            f"difference is against",
            step_index=None, rule=rule,
        )
    other_index = 1 - xi
    if contrast.get("reference_value") != x_levels[other_index]:
        raise VerificationError(
            f"Manski-Tamer contrast names {contrast.get('reference_value')!r} "
            f"as the baseline arm; the recorded levels make it "
            f"{x_levels[other_index]!r}",
            step_index=None, rule=rule,
        )
    # The other arm's interval is this same bound with the push reversed —
    # intervening there moves Y the other way for the units observed here.
    # Subtracting is sharp because the two arms' unknowns live in DISJOINT
    # sub-populations, each confined only by its own unit's observation, so
    # every pair of points is jointly attainable.
    lo_b, hi_b = arm(other_index, not up)
    for key, want in (("lower_value", exp_lo - hi_b),
                      ("upper_value", exp_hi - lo_b)):
        got = contrast.get(key)
        if not isinstance(got, (int, float)) or isinstance(got, bool) \
                or abs(want - got) > 1e-9 + 1e-9 * abs(got):
            raise VerificationError(
                f"Manski-Tamer contrast.{key} is {got!r}; the recorded counts "
                f"give {want}. The contrast is the quantity the effect query "
                f"asked for, so this is the reported number furthest from "
                f"what the data support",
                step_index=None, rule=rule,
            )


def _envelope_like(v: object) -> object:
    """A declared level as it appears once written to the envelope — the
    producer's ``envelope_scalar`` seen from this side, restated so the two
    level lists are compared on equal terms rather than across an encoding."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    return v


def verify_manski_natural_bounds_result(
    bounds_result: dict,
    *,
    query_dict: dict,
) -> None:
    """Re-derive the expected Manski natural (1990) bounds
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

    # The note beside it tells a reader the width IS that off-arm mass.
    # Passed rather than re-derived, for the reason the MTR rule below
    # states: the string was just built here, and a second construction
    # would only be a second chance to build it wrong.
    from .bounds_account_rules import verify_the_mass_a_width_is_laid_to
    verify_the_mass_a_width_is_laid_to(bounds_result, mass=other_arm_mass)

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


def _require_nonneg_int(value: object, *, label: str, rule: str) -> int:
    """Return ``value`` as a non-negative ``int``, or raise.

    A count pulled out of an untyped payload is ``object``; asserting
    about it in a separate loop leaves the arithmetic below still holding
    ``object``. Returning the checked value hands the caller the narrowed
    type, so the closed form that consumes the counts is checkable.
    ``bool`` is rejected explicitly — ``True`` is an ``int`` but never a
    row count.
    """
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerificationError(
            f"{label} must be a non-negative int; got {value!r}",
            step_index=None, rule=rule,
        )
    return value


def _rederive_manski_natural_numeric(bounds_result: dict) -> None:
    """Strong re-derivation of the Manski natural arm interval from the
    recorded arm counts — the treatment-cardinality-agnostic analogue of
    the Balke-Pearl P_xyz re-derivation.

    The producer records ``sufficient_statistics``
    ``{"n", "n_joint_target_arm", "n_other_arm", "n_joint_other_arm"}`` — the
    counts the closed form consumes: ``lower = n_joint/n``, ``upper =
    (n_joint + n_other)/n``, ``width = n_other/n``, and the fourth one the
    contrast needs (:func:`_rederive_manski_natural_contrast`). This
    verifier re-derives the
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
    rule = "bounds_manski_natural"
    contrast = bounds_result.get("contrast")
    raw = bounds_result.get("sufficient_statistics")
    stats: dict = raw if isinstance(raw, dict) else {}
    if "n_joint_target_arm" not in stats and "n_other_arm" not in stats:
        # Symbolic-only, or a different method's stats shape (Balke-Pearl's
        # P_xyz). Either way there is nothing here to re-derive from — and a
        # contrast that arrived anyway is the number the query actually asked
        # for, resting on counts this verifier was never given.
        if contrast is not None:
            raise VerificationError(
                "Manski natural reported a contrast without the arm counts "
                "it is derived from; the interval a reader is shown for the "
                "quantity they asked about would rest on nothing this "
                "verifier can recompute",
                step_index=None, rule=rule,
            )
        return
    n = _require_nonneg_int(
        stats.get("n"),
        label="Manski natural sufficient_statistics.n", rule=rule,
    )
    n_joint = _require_nonneg_int(
        stats.get("n_joint_target_arm"),
        label="Manski natural sufficient_statistics.n_joint_target_arm",
        rule=rule,
    )
    n_other = _require_nonneg_int(
        stats.get("n_other_arm"),
        label="Manski natural sufficient_statistics.n_other_arm", rule=rule,
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
    if contrast is not None:
        _rederive_manski_natural_contrast(
            contrast, stats, n=n, n_joint=n_joint, n_other=n_other, rule=rule,
        )


def _rederive_manski_natural_contrast(
    contrast: dict, stats: dict, *,
    n: int, n_joint: int, n_other: int, rule: str,
) -> None:
    """Re-derive the ACE interval an ``effect`` query asked for, from the
    same counts, and reject a reported one that does not match.

    Under the assumption-free model the two arms' unobserved masses are
    disjoint sub-populations with nothing tying them together, so the sharp
    interval on the difference is the difference of the two arms' intervals::

        lower = (n_joint − n_joint_other − n_arm) / n
        upper = (n_joint − n_joint_other + n_other) / n

    with ``n_arm = n − n_other``. Re-derived here rather than read from the
    producer, which this module must not import.

    The width follows from the same two counts and is ``(n_arm + n_other)/n
    = 1`` on every dataset — checked separately from the endpoints because it
    is a theorem about the model rather than an identity in the recorded
    numbers: a producer that arrives at this interval some other way and gets
    a width other than 1 has not bounded a Manski ACE, whatever it recorded.
    """
    n_joint_other = _require_nonneg_int(
        stats.get("n_joint_other_arm"),
        label="Manski natural sufficient_statistics.n_joint_other_arm",
        rule=rule,
    )
    if n_joint_other > n_other:
        raise VerificationError(
            f"Manski natural counts violate the off-arm partition: "
            f"n_joint_other_arm ({n_joint_other}) exceeds n_other_arm "
            f"({n_other}); the off-arm's joint count is a subset of it",
            step_index=None, rule=rule,
        )
    n_arm = n - n_other
    expected = {
        "lower_value": (n_joint - n_joint_other - n_arm) / n,
        "upper_value": (n_joint - n_joint_other + n_other) / n,
    }
    for key, want in expected.items():
        got = contrast.get(key)
        if not isinstance(got, (int, float)) or isinstance(got, bool) \
                or abs(want - got) > 1e-9 + 1e-9 * abs(got):
            raise VerificationError(
                f"Manski natural contrast.{key} is {got!r}; the recorded arm "
                f"counts give {want}. The contrast is the quantity the effect "
                f"query asked for, so this is the reported number furthest "
                f"from what the data support",
                step_index=None, rule=rule,
            )
    width = expected["upper_value"] - expected["lower_value"]
    if abs(width - 1.0) > 1e-9:
        raise VerificationError(
            f"Manski natural contrast has width {width}; the assumption-free "
            f"ACE interval is exactly 1 wide on every dataset "
            f"(P(X≠x) + P(X≠x') = 1), so this is not one",
            step_index=None, rule=rule,
        )


_BP_EXPECTED_ASSUMPTIONS = frozenset({
    "iv1_relevance",
    "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
    "iv3_independence_instrument_independent_of_unmeasured_confounders",
})


def _graph_instrument_candidates(
    program: dict, *, treatment: str, outcome: str,
) -> set[str]:
    """Predicates this graph could offer as an instrument for X → Y.

    The instrument's structural half and nothing else, read off the
    programme's ``cause`` statements: an edge into the treatment
    (relevance) and none into the outcome (exclusion). Transcribed here
    rather than imported, for the same reason the response-function
    partition below is transcribed here — a producer and an auditor that
    share one implementation of a criterion agree by construction, and
    agreement by construction is not evidence.

    NECESSARY, not sufficient. Whether a candidate has a finite domain to
    enumerate, and whether the model that follows is inside the
    producer's size cap, are questions about the declaration and the
    method's own limits; neither is the graph's to answer, and a rule
    auditing WHICH variable was named has no business deciding them. What
    a necessary condition still refuses is the thing worth refusing: a
    row naming a variable that could not be an instrument in this graph
    at all.
    """
    into_treatment: set[str] = set()
    into_outcome: set[str] = set()
    for stmt in program.get("statements") or []:
        if not isinstance(stmt, dict) or stmt.get("kind") != "cause":
            continue
        frm = (stmt.get("from") or {}).get("predicate")
        to = (stmt.get("to") or {}).get("predicate")
        if not isinstance(frm, str) or not isinstance(to, str):
            continue
        if to == treatment:
            into_treatment.add(frm)
        if to == outcome:
            into_outcome.add(frm)
    return (into_treatment - into_outcome) - {treatment, outcome}


def verify_balke_pearl_iv_bounds_result(
    bounds_result: dict,
    *,
    program: dict,
    query_dict: dict,
) -> None:
    """Audit the Balke-Pearl IV bounds (Phase 12 producer).

    The producer emits a reference to the linear programme rather than a
    closed form, because at a general cardinality there is no closed form
    to print — the "max/min of 8 linear combinations" that can be printed
    is the binary case's analytic solution:

        lower = "min of P({target}={y} | do({treatment}={x})) over the
                 response-function polytope fitted to
                 P({target}, {treatment} | {z}) (Balke-Pearl LP, N
                 response types)"
        upper = "max of ... (same polytope, same observables as lower)"

    Which is a sentence, and a sentence is a rendering. This rule used to
    recover the instrument out of it with a regular expression, because
    the row named the instrument nowhere else: the audit of WHICH
    variable the polytope was fitted around was a search for a bracket in
    a sentence. So a producer that reworded the sentence broke the audit,
    and a producer that fitted around the wrong variable did not. The
    instrument is a field now, and this reads it.

    Checked as facts:

    - ``method``, and ``estimand``. The estimand is the field the
      canonical opening phrase was standing in for — the phrase carried
      "this brackets one arm, not the ACE", and a phrase carries that
      only until someone rewords it.
    - ``instrument``, against what the graph offers. See
      :func:`_graph_instrument_candidates` for why that condition is
      necessary rather than sufficient.
    - the assumption tag set is exactly iv1/iv2/iv3.
    - the numbers, when the producer recorded the table its LP consumed —
      see :func:`_rederive_balke_pearl_numeric`.

    Checked as renderings, and only that: each expression names the facts
    it renders — the target, the intervened arm, the instrument. Wording
    and order are the producer's. One arm is named once: an expression
    carrying two ``do(X=…)`` clauses brackets a difference, whatever the
    estimand field says.

    Which end of the interval a rendering is, is not audited, and the
    reason is worth writing down rather than leaving as an omission. The
    direction is carried by the slot — that is what ``lower_expression``
    means — and the operator word in the sentence is a rendering of it.
    Auditing that word by looking for it refuses any programme whose
    predicates happen to contain it: ``vitamin`` contains ``min``. What
    would make it auditable is the operator becoming a token in the
    vocabulary registry with a rendering per language — the machinery
    the closed vocabularies already go through, rather than something
    for one rule to invent one slot at a time.
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

    if bounds_result.get("estimand") != "arm_probability":
        raise VerificationError(
            f"Balke-Pearl IV bounds bracket the single arm the query named; "
            f"this row declares estimand {bounds_result.get('estimand')!r}. "
            f"The ACE is a different quantity, and this block has shipped "
            f"one under a question that asked for an arm.",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    instrument = bounds_result.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        raise VerificationError(
            f"Balke-Pearl IV bounds must name the instrument the polytope "
            f"was fitted around; this row carries {instrument!r}. A bound "
            f"whose instrument is only inside its own sentence can be "
            f"audited only by reading that sentence, which makes the audit "
            f"a check on the wording.",
            step_index=None, rule="bounds_balke_pearl_iv",
        )
    offered = _graph_instrument_candidates(
        program, treatment=treatment_pred, outcome=target_pred,
    )
    if instrument not in offered:
        raise VerificationError(
            f"Balke-Pearl IV bounds name {instrument!r} as the instrument "
            f"for {treatment_pred!r} → {target_pred!r}, which this graph "
            f"does not offer: an instrument needs an edge into the "
            f"treatment and none into the outcome, and the predicates with "
            f"both are {sorted(offered)!r}",
            step_index=None, rule="bounds_balke_pearl_iv",
        )

    actual_lower = bounds_result.get("lower_expression") or ""
    actual_upper = bounds_result.get("upper_expression") or ""

    # What is left on the expressions is a rendering obligation: a
    # sentence shown to a reader as this bound has to name what it is a
    # bound on. Nothing here constrains how it says so.
    for expr_name, expr in (("lower", actual_lower), ("upper", actual_upper)):
        if target_pred not in expr:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression must reference "
                f"target predicate {target_pred!r}; got: {expr!r}",
                step_index=None, rule="bounds_balke_pearl_iv",
            )
        arms = expr.count(f"do({treatment_pred}=")
        if arms == 0:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression must name the "
                f"intervened arm as 'do({treatment_pred}=<level>)' — the "
                f"bound is on one arm, and an expression that does not say "
                f"which arm does not identify what it brackets; got: "
                f"{expr!r}",
                step_index=None, rule="bounds_balke_pearl_iv",
            )
        if arms > 1:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression names "
                f"{arms} levels of {treatment_pred!r}, so it brackets a "
                f"difference between arms; the row declares the estimand "
                f"'arm_probability', which is one arm. got: {expr!r}",
                step_index=None, rule="bounds_balke_pearl_iv",
            )
        if instrument not in expr:
            raise VerificationError(
                f"Balke-Pearl IV {expr_name}_expression must name the "
                f"instrument it was fitted around, {instrument!r} — a "
                f"reader shown the bound and not the instrument cannot "
                f"tell what it rests on; got: {expr!r}",
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


# The response-function model, transcribed INDEPENDENTLY here (this module
# must not import estimation/bounds_numeric.py). Under IV exclusion +
# independence a unit is two maps: which treatment it takes at each instrument
# level, and which outcome it shows at each treatment level. Enumerating both
# families gives the canonical partition; nothing here is written as a
# constant, so a producer that quietly changed a cardinality cannot be matched
# by a verifier that quietly changed the same one.
def _v_response_types(nx: int, ny: int, nz: int):
    import itertools

    return (
        list(itertools.product(range(nx), repeat=nz)),   # fx[z] = x
        list(itertools.product(range(ny), repeat=nx)),   # gy[x] = y
    )


def _rederive_balke_pearl_numeric(bounds_result: dict) -> None:
    """Strong re-derivation of the Balke-Pearl interval from the recorded
    P(X=x, Y=y | Z=z) table.

    The producer records ``sufficient_statistics.P_xyz`` (the empirical
    conditional table the response-function LP consumed) together with the
    level lists that say what the table's axes mean and which arm was asked
    about. This verifier re-runs an INDEPENDENTLY-transcribed LP over that
    table and rejects a mismatch with the reported ``lower_value`` /
    ``upper_value`` — so a tampered bound (e.g. a falsely-tight interval) is
    caught, not just range/width-audited. The ``contrast`` interval, when the
    producer reports one, is re-derived the same way and against its OWN
    objective rather than by subtracting the arm's endpoints: the two agree
    on the binary IV model but the agreement is a measured fact about that
    model, not something a verifier should assume on the producer's behalf.

    Also re-checks that the recorded table is a valid conditional
    distribution and satisfies the instrumental inequality — a closed-form
    witness of refutation, computed without the LP. Skipped when no P_xyz is
    recorded (symbolic-only, or an older producer). Independence pin: does
    not import the producer.

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
            "Balke-Pearl sufficient_statistics.P_xyz must be a numeric "
            f"|Z|x|X|x|Y| array; got {raw!r}", step_index=None, rule=rule,
        )
    if P.ndim != 3 or min(P.shape) < 2:
        raise VerificationError(
            f"Balke-Pearl P_xyz must be a 3-d |Z|x|X|x|Y| array with at least "
            f"two levels on each axis; got shape {P.shape}",
            step_index=None, rule=rule,
        )
    nz, nx, ny = (int(d) for d in P.shape)

    # The axes are only meaningful if the producer said what they are. A
    # 2x3x2 table read as 3x2x2 re-derives a different interval and calls an
    # honest producer a liar, so the level lists are required, not optional.
    declared = (
        ("instrument_levels", nz), ("treatment_levels", nx),
        ("outcome_levels", ny),
    )
    for key, size in declared:
        levels = stats.get(key)
        if not isinstance(levels, list) or len(levels) != size:
            raise VerificationError(
                f"Balke-Pearl sufficient_statistics.{key} must list the "
                f"{size} levels the recorded P_xyz axis has; got {levels!r}",
                step_index=None, rule=rule,
            )
    xi = stats.get("arm_treatment_index")
    yi = stats.get("arm_outcome_index")
    if not isinstance(xi, int) or not 0 <= xi < nx:
        raise VerificationError(
            f"Balke-Pearl sufficient_statistics.arm_treatment_index must be a "
            f"level position in [0,{nx}); got {xi!r}",
            step_index=None, rule=rule,
        )
    if not isinstance(yi, int) or not 0 <= yi < ny:
        raise VerificationError(
            f"Balke-Pearl sufficient_statistics.arm_outcome_index must be a "
            f"level position in [0,{ny}); got {yi!r}",
            step_index=None, rule=rule,
        )

    if np.any(P < -1e-9):
        raise VerificationError(
            "Balke-Pearl P_xyz has a negative probability entry",
            step_index=None, rule=rule,
        )
    # Each Z-slice is a conditional distribution over (X, Y): must sum to 1.
    for z in range(nz):
        s = float(P[z].sum())
        if abs(s - 1.0) > 1e-6:
            raise VerificationError(
                f"Balke-Pearl P_xyz[Z={z}] sums to {s}, not 1 (not a "
                "conditional distribution)", step_index=None, rule=rule,
            )

    # Pearl's instrumental inequality: for each treatment level,
    # Σ_y max_z P(Y=y, X=x | Z=z) ≤ 1. A violation refutes the IV model
    # outright, independently of the LP; it reduces to Balke-Pearl (1997)
    # eq 6's four checks when everything is binary.
    worst = max(
        float(sum(P[:, x, y].max() for y in range(ny))) for x in range(nx)
    )
    if worst > 1.0 + 1e-6:
        raise VerificationError(
            f"Balke-Pearl recorded P_xyz violates the instrumental inequality "
            f"(max = {worst:.4f} > 1); the table is incompatible with a valid "
            "IV model, so the bounds could not have come from it",
            step_index=None, rule=rule,
        )

    fxs, gys = _v_response_types(nx, ny, nz)
    arm_obj = [
        1.0 if gy[xi] == yi else 0.0 for _fx in fxs for gy in gys
    ]
    lo, hi = _verifier_response_lp(P, nx, ny, nz, arm_obj, rule)
    reported_lo = bounds_result.get("lower_value")
    reported_hi = bounds_result.get("upper_value")
    if reported_lo is None or reported_hi is None:
        raise VerificationError(
            "Balke-Pearl recorded sufficient_statistics but no numeric "
            "lower_value / upper_value to verify against",
            step_index=None, rule=rule,
        )
    _match(lo, reported_lo, "lower_value", rule)
    _match(hi, reported_hi, "upper_value", rule)

    contrast = bounds_result.get("contrast")
    if contrast is None:
        return
    if not isinstance(contrast, dict):
        raise VerificationError(
            f"Balke-Pearl contrast must be an object naming a second bounded "
            f"quantity; got {contrast!r}", step_index=None, rule=rule,
        )
    if nx != 2:
        raise VerificationError(
            f"Balke-Pearl reported an ACE contrast on a {nx}-level treatment; "
            "with more than two levels the difference has no baseline arm and "
            "the quantity is undefined",
            step_index=None, rule=rule,
        )
    other = 1 - xi
    contrast_obj = [
        (1.0 if gy[xi] == yi else 0.0) - (1.0 if gy[other] == yi else 0.0)
        for _fx in fxs for gy in gys
    ]
    c_lo, c_hi = _verifier_response_lp(P, nx, ny, nz, contrast_obj, rule)
    _match(c_lo, contrast.get("lower_value"), "contrast.lower_value", rule)
    _match(c_hi, contrast.get("upper_value"), "contrast.upper_value", rule)


def _match(derived: float, reported, field: str, rule: str) -> None:
    """Reject a reported endpoint that is not what the LP yields."""
    if not isinstance(reported, (int, float)) or isinstance(reported, bool):
        raise VerificationError(
            f"Balke-Pearl {field} must be a number to verify against; got "
            f"{reported!r}", step_index=None, rule=rule,
        )
    if abs(derived - reported) > 1e-6 + 1e-6 * abs(reported):
        raise VerificationError(
            f"Balke-Pearl {field} {reported} does not match the value "
            f"re-derived from the recorded P(X,Y|Z) table ({derived}); the "
            "reported bound is not what the response-function LP yields on "
            "that table",
            step_index=None, rule=rule,
        )


def _verifier_response_lp(
    P, nx: int, ny: int, nz: int, objective, rule: str,
    forbidden: "list[int] | None" = None,
) -> tuple[float, float]:
    """Range of a linear functional over every response-type distribution
    reproducing ``P[z,x,y] = P(X=x, Y=y | Z=z)``, by an independently-
    transcribed LP. Returns (lower, upper).

    ``forbidden`` lists response types a declared assumption says the
    population does not contain — an upper bound of zero on their mass, which
    is what "no unit is of this type" means to a program over type
    frequencies."""
    import numpy as np
    from scipy.optimize import linprog

    fxs, gys = _v_response_types(nx, ny, nz)
    ntypes = len(fxs) * len(gys)
    rows: list = []
    b: list = []
    for z in range(nz):
        for x in range(nx):
            for y in range(ny):
                row = np.zeros(ntypes)
                for i, fx in enumerate(fxs):
                    for j, gy in enumerate(gys):
                        if fx[z] == x and gy[fx[z]] == y:
                            row[i * len(gys) + j] = 1.0
                rows.append(row)
                b.append(float(P[z, x, y]))
    rows.append(np.ones(ntypes))
    b.append(1.0)
    A_eq = np.asarray(rows)
    b_eq = np.asarray(b)
    c = np.asarray(objective, dtype=float)
    blocked = set(forbidden or ())
    simplex = [
        (0.0, 0.0) if k in blocked else (0.0, None) for k in range(ntypes)
    ]
    lo = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    hi = linprog(-c, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    if not (lo.success and hi.success):
        raise VerificationError(
            "Balke-Pearl re-derivation LP is infeasible on the recorded "
            "P(X,Y|Z) table — no response-type distribution reproduces it"
            + (
                " under the declared assumption's restriction of the type "
                "space, so an answer could not have come out of it"
                if blocked else
                ", so the table cannot have produced sharp bounds"
            ),
            step_index=None, rule=rule,
        )
    return float(lo.fun), float(-hi.fun)


#: How tight each method's interval is, per bracketed quantity. This
#: verifier's own copy, like :data:`_NUMERIC_ESTIMAND_BY_METHOD` below and
#: for the same reason: sharpness is a claim about the PROCEDURE and is
#: invisible in the numbers — an outer bound and the identified set are
#: both valid intervals over the same quantity — so a check that read the
#: producer's table would agree with it by construction, including when the
#: table is the thing that is wrong (#419).
#:
#: A pair absent from this table is "this verifier cannot vouch for a
#: tightness there", and a row claiming one anyway is refused rather than
#: believed. Every pair a method can report is present today; the entry that
#: was not was Manski-Tamer's contrast, held back on the reasoning that MTR
#: ties the two arms at the unit level. It does, and that does not make the
#: difference unsharp: the two arms' UNKNOWNS sit in disjoint sub-populations
#: and nothing couples the endpoints (#424).
_TIGHTNESS_BY_METHOD: dict[tuple[str, str], str | None] = {
    ("manski_natural", "arm"): "sharp",
    ("manski_natural", "contrast"): "sharp",
    ("manski_tamer_monotonicity", "arm"): "sharp",
    ("manski_tamer_monotonicity", "contrast"): "sharp",
    ("balke_pearl_iv", "arm"): "sharp",
    ("balke_pearl_iv", "contrast"): "sharp",
}


def _audit_tightness(row: dict, *, method: str, pair: str, rule: str) -> None:
    """The row's claim about tightness, against what the procedure earns.

    Unstated is refused, not waved through. The word decides what a reader
    does next — a sharp interval says no better procedure narrows it, an
    outer one says there may be room without any further assumption — and
    an interval shipped without it is the one a reader has to guess about,
    which is the whole of what this field was added for.
    """
    said = row.get("tightness")
    expected = _TIGHTNESS_BY_METHOD.get((method, pair))
    if expected is None:
        raise VerificationError(
            f"method {method!r} reported a {pair} tightness {said!r}, and "
            f"this verifier has no tightness it can vouch for on that pair "
            f"(themis.verifier.bounds_rules._TIGHTNESS_BY_METHOD)",
            step_index=None, rule=rule,
        )
    if said != expected:
        raise VerificationError(
            f"{pair} of method {method!r} states tightness {said!r}; this "
            f"procedure yields {expected!r}. Whether a narrower set is "
            f"consistent with the same assumptions is not readable off the "
            f"endpoints, so a wrong word here is not recoverable downstream",
            step_index=None, rule=rule,
        )


_NUMERIC_ESTIMAND_BY_METHOD = {
    "manski_natural": ("arm_probability", (0.0, 1.0)),
    "manski_tamer_monotonicity": ("arm_probability", (0.0, 1.0)),
    # All three bound the arm the query named. The ACE, where it is defined,
    # travels in `contrast` with its own endpoints and its own range.
    "balke_pearl_iv": ("arm_probability", (0.0, 1.0)),
}

# Which methods may report a contrast beside the arm. Declared rather than
# left to whoever emits one, because the contrast is the quantity an
# ``effect`` query actually asked for: an unaudited one would be the least
# supervised number in the block and the one a reader leans on hardest.
# Manski-Tamer's is sharp for the same reason Manski natural's is: the
# assumption ties each unit's two potential outcomes, but the two arms'
# UNKNOWNS sit in disjoint sub-populations, so nothing couples the endpoints
# and the difference of the intervals is the interval of the difference.
_MAY_REPORT_CONTRAST = frozenset({
    "manski_natural", "manski_tamer_monotonicity", "balke_pearl_iv",
})

# An ACE is a difference of two probabilities, whatever bracketed it.
_ACE_RANGE = (-1.0, 1.0)


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
    eps = 1e-9
    _audit_tightness(bounds_result, method=method, pair="arm", rule=rule)
    _audit_contrast(bounds_result, method=method, rule=rule, eps=eps)
    lower = bounds_result.get("lower_value")
    upper = bounds_result.get("upper_value")
    if lower is None and upper is None:
        return  # symbolic-only; nothing numeric to audit
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


def _audit_contrast(
    bounds_result: dict, *, method: str, rule: str, eps: float,
) -> None:
    """The shape audit every contrast gets, whichever method reported it.

    Ahead of the numeric end's early return rather than inside it: a row that
    brackets nothing numerically has nothing to contrast either, so a
    contrast sitting on one is a number with no interval under it.

    What the arithmetic must be is the method's own business and is checked
    where that method's re-derivation lives — over the polytope for
    Balke-Pearl, from the recorded arm counts for Manski natural. What is
    common to both is that an ACE is a difference of two probabilities.
    """
    contrast = bounds_result.get("contrast")
    if contrast is None:
        return
    if method not in _MAY_REPORT_CONTRAST:
        raise VerificationError(
            f"method {method!r} reported a contrast, and no rule here can "
            f"re-derive one for it. The contrast is the quantity an effect "
            f"query asks for, so an unchecked one is the number a reader "
            f"leans on hardest and nothing has audited "
            f"(themis.verifier.bounds_rules._MAY_REPORT_CONTRAST)",
            step_index=None, rule=rule,
        )
    if not isinstance(contrast, dict):
        raise VerificationError(
            f"contrast must be an object naming a second bounded quantity; "
            f"got {contrast!r}", step_index=None, rule=rule,
        )
    _audit_tightness(contrast, method=method, pair="contrast", rule=rule)
    c_lo = contrast.get("lower_value")
    c_hi = contrast.get("upper_value")
    if not isinstance(c_lo, (int, float)) or isinstance(c_lo, bool) \
            or not isinstance(c_hi, (int, float)) or isinstance(c_hi, bool):
        raise VerificationError(
            f"contrast must carry numeric lower_value / upper_value; got "
            f"{c_lo!r} / {c_hi!r}", step_index=None, rule=rule,
        )
    if c_lo > c_hi + eps:
        raise VerificationError(
            f"contrast inverted: lower_value {c_lo} > upper_value {c_hi}",
            step_index=None, rule=rule,
        )
    lo_r, hi_r = _ACE_RANGE
    if c_lo < lo_r - eps or c_hi > hi_r + eps:
        raise VerificationError(
            f"contrast [{c_lo}, {c_hi}] falls outside [{lo_r}, {hi_r}]; an "
            f"average causal effect is a difference of two probabilities and "
            f"cannot leave that range",
            step_index=None, rule=rule,
        )


def _fmt_value(v: object) -> str:
    """Stringify a bool / numeric / str value the same way bounds.py
    does — but re-implemented here so the verifier doesn't import the
    producer (independence pin)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
