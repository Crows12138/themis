"""Top-level verifier entries.

- ``verify_identify`` — V0, identify-query structural derivations.
- ``verify_numeric`` — V1, effect/probability numerically-solved
  derivations whose last step is a ``NumericResult``.

Both share a single walk over the derivation. They differ only in:

- which query shape they bind against (IdentifyQuery vs
  EffectQuery / ProbabilityQuery);
- what type the final step's output must match (StructuralResult
  vs NumericResult).

A derivation that raises nothing is ``accepted``. A derivation that
raises any ``VerificationError`` is ``rejected`` and the caller can
inspect ``step_index`` / ``rule`` on the exception.
"""
from __future__ import annotations

from typing import Callable

from ..types import (
    AssocQuery,
    CausationQuery,
    CauseQuery,
    ConstantExpr,
    CounterfactualConjunctionQuery,
    CounterfactualQuery,
    DerivationStep,
    EffectQuery,
    FractionExpr,
    IdentifyQuery,
    NumericInterval,
    NumericResult,
    ProbabilityRefExpr,
    ProbabilityQuery,
    ProductExpr,
    ProximalEffectQuery,
    SCMCounterfactualQuery,
    SumExpr,
    StepRef,
    StructuralResult,
    ValuedAtom,
)
from .context import VerificationContext
from .errors import (
    RuleNotFoundError,
    StepRefError,
    VerificationError,
)
from .rules import _numeric_result_matches, dispatch_rule, known_rule
from .semantic_probe import (
    probe_conditional_counterfactual_formula,
    probe_counterfactual_formula,
    probe_identify_formula,
)


# Phase 15 — nonparametric point-identification terminal rules. For these
# the claimed formula MUST equal the true do-quantity in every model
# consistent with the graph, so the semantic backbone applies. IV
# (assumption-laden), bounds (interval), mediation / transport (different
# estimands) are the escalation layer and are deliberately NOT listed.
_NONPARAM_POINT_ID_RULES = (
    "identify_via_backdoor",
    "identify_via_front_door",
    "identify_via_tian",
    "identify_via_idc",
)


def _extract_identify_formula(derivation: tuple[DerivationStep, ...]):
    """Pull the claimed identification formula out of the terminal step.

    Tian / IDC carry it inline in the step inputs; backdoor / front-door
    reference a formula step whose OUTPUT is the formula. Returns None
    when no formula is recoverable (the caller then skips the probe)."""
    _FORMULA = (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr)
    last = derivation[-1]
    inline = last.inputs.get("formula")
    if isinstance(inline, _FORMULA):
        return inline
    if isinstance(inline, StepRef):
        by_id = {s.step_id: s.output for s in derivation}
        candidate = by_id.get(inline.step_id)
        return candidate if isinstance(candidate, _FORMULA) else None
    return None


# Iter 182/183: rules that may produce a formula referenced by
# subsequent formula_evaluation steps. When the verifier checks an
# effect query's formula_evaluation, the formula must equal the
# output of one of these prior witness steps. Pre-iter-182 only
# backdoor was accepted; iter 182 added front-door for the
# bidirected-loosen case (iter 168). New identification paths that
# emit symbolic formulas (not raw numeric estimates) need to be
# added here — IV / mediation / dose-response use dataframe
# estimators rather than formula_evaluation, so they're not in
# this set today.
IDENTIFICATION_FORMULA_RULES: frozenset[str] = frozenset({
    "backdoor_adjustment_formula",
    "front_door_adjustment_formula",
    # Fix 3+4 §T9.2 (v0.1.5): transport's FormulaExpr witness step,
    # parallel to backdoor / front-door identification-formula rules.
    # The existing transport_formula step (s_t9_2, string output) stays
    # for human-readable rendering; transport_formula_ast is the
    # machine-verifiable FormulaExpr that formula_evaluation matches
    # against in verify_numeric's witness check.
    "transport_formula_ast",
    # Fix 5 (v0.1.5, audit follow-up): Tian-in-effect FormulaExpr
    # witness — bound (target-value-bound) version of the formula
    # that c_factor.identify_via_tian produced. Parallels
    # transport_formula_ast: existing identify_via_tian step still
    # carries the unbound formula in inputs for the identify path;
    # tian_formula_ast emits the q.target.value-bound version that
    # formula_evaluation matches against for the effect path.
    "tian_formula_ast",
    # Phase 2 (conditional general-ID): IDC-in-effect FormulaExpr witness —
    # the identify_via_idc estimand with the query's Y and Z values bound
    # (in both target and given positions). Parallels tian_formula_ast: the
    # identify_via_idc step carries the unbound formula for the identify
    # path; idc_formula_ast emits the value-bound version that
    # formula_evaluation matches against for the conditional-effect path.
    "idc_formula_ast",
})


def _resolve_step_refs(
    inputs: dict,
    step_output_by_id: dict,
    step_index: int,
    rule: str,
) -> dict:
    """Return a new dict with any top-level StepRef values replaced by
    the referenced step's output. StepRefs nested inside tuples / sets
    are left as-is — rules that expect refs at the top level (R5) get
    the unresolved dict and handle refs themselves."""
    # For V0 the resolution is shallow: R5 expects StepRefs at the top
    # level (handled by the rule itself), other rules only receive
    # concrete values. If we detect a stray StepRef at top level for a
    # non-ref rule, leave it; the rule's input check will complain with
    # a clearer message than we could produce here.
    return inputs


def _assert_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Reject derivations that prove *some other* identify query on the
    same graph.

    V0 only supports identify derivations, so the query binding can be
    made explicit:

    - ``backdoor_criterion`` must reason about the active query's
      intervention atom, target atom, and given set.
    - ``backdoor_adjustment_formula`` must build a formula for the
      active query's target / intervention value / observed context.

    This keeps the verifier from accepting a perfectly valid proof for
    a different (X, Y, given, do-value) on the same graph.
    """
    q = context.query

    # Extract target atom + given atoms from either an IdentifyQuery
    # (target is already an Atom) or an EffectQuery (target is a
    # ValuedAtom). Phase 7.1 reuses backdoor_criterion on the effect
    # path for the numeric estimate witness.
    if isinstance(q, EffectQuery):
        q_target_atom = q.target.atom
        q_given_atoms = frozenset(g.atom for g in q.given)
    else:
        q_target_atom = q.target
        q_given_atoms = frozenset(q.given)

    if step.rule == "backdoor_criterion":
        if step.inputs.get("x") != q.intervention.atom:
            raise VerificationError(
                "backdoor_criterion.x does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                "backdoor_criterion.y does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        step_given = step.inputs.get("given", frozenset())
        if frozenset(step_given) != q_given_atoms:
            raise VerificationError(
                "backdoor_criterion.given does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )

    if step.rule == "backdoor_adjustment_formula":
        expected_target = ValuedAtom(atom=q.target, value=None)
        expected_intervention = ValuedAtom(
            atom=q.intervention.atom,
            value=q.intervention.value,
        )
        expected_given = frozenset(
            ValuedAtom(atom=a, value=None) for a in q.given
        )

        if step.inputs.get("target") != expected_target:
            raise VerificationError(
                "backdoor_adjustment_formula.target does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        if step.inputs.get("intervention") != expected_intervention:
            raise VerificationError(
                "backdoor_adjustment_formula.intervention does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        step_given = step.inputs.get("given", ())
        if frozenset(step_given) != expected_given:
            raise VerificationError(
                "backdoor_adjustment_formula.given does not match verification context query",
                step_index=step_index,
                rule=step.rule,
                )

    if step.rule == "unidentifiable_via_backdoor":
        if step.inputs.get("x") != q.intervention.atom:
            raise VerificationError(
                "unidentifiable_via_backdoor.x does not match identify query intervention atom",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q.target:
            raise VerificationError(
                "unidentifiable_via_backdoor.y does not match identify query target",
                step_index=step_index, rule=step.rule,
            )
        step_given = step.inputs.get("given", frozenset())
        if frozenset(step_given) != frozenset(q.given):
            raise VerificationError(
                "unidentifiable_via_backdoor.given does not match identify query given",
                step_index=step_index, rule=step.rule,
            )

    # A6 front-door: same binding shape as backdoor's, but since the
    # front-door formula builder currently does not accept an
    # ``observed`` conditioning set, we require the active query to
    # have ``given == ()``. That keeps the verifier from accepting a
    # front-door proof for a conditioned query it cannot construct.
    if step.rule == "front_door_criterion":
        if step.inputs.get("x") != q.intervention.atom:
            raise VerificationError(
                "front_door_criterion.x does not match identify query intervention atom",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                "front_door_criterion.y does not match identify query target",
                step_index=step_index, rule=step.rule,
            )
        if q_given_atoms:
            raise VerificationError(
                "front_door_criterion requires identify query given to be empty",
                step_index=step_index, rule=step.rule,
            )

    if step.rule == "front_door_adjustment_formula":
        expected_target = ValuedAtom(atom=q.target, value=None)
        expected_intervention = ValuedAtom(
            atom=q.intervention.atom,
            value=q.intervention.value,
        )
        if step.inputs.get("target") != expected_target:
            raise VerificationError(
                "front_door_adjustment_formula.target does not match query",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("intervention") != expected_intervention:
            raise VerificationError(
                "front_door_adjustment_formula.intervention does not match query",
                step_index=step_index, rule=step.rule,
            )
        if q.given:
            raise VerificationError(
                "front_door_adjustment_formula requires identify query given to be empty",
                step_index=step_index, rule=step.rule,
            )

    # Joint (treatment-set) back-door: the criterion step declares the
    # whole treatment vector + target + given it reasons about. Bind them
    # to the active EffectQuery so a joint proof for one (treatments, Y,
    # given) cannot be replayed against another query on the same graph.
    if step.rule == "joint_backdoor_criterion" and isinstance(q, EffectQuery):
        expected_treatments = frozenset(
            (q.intervention.atom, *(iv.atom for iv in q.extra_interventions))
        )
        if frozenset(step.inputs.get("treatments", frozenset())) != expected_treatments:
            raise VerificationError(
                "joint_backdoor_criterion.treatments does not match the "
                "effect query's joint treatment vector",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                "joint_backdoor_criterion.y does not match effect query target",
                step_index=step_index, rule=step.rule,
            )
        if frozenset(step.inputs.get("given", frozenset())) != q_given_atoms:
            raise VerificationError(
                "joint_backdoor_criterion.given does not match effect query given",
                step_index=step_index, rule=step.rule,
            )

    # Phase 15B: Tian / IDC are the primary point-ID path. Their
    # decomposition / Rule-2-exchange steps declare the (x, y) they reason
    # about; require it to match the active query so a derivation built for
    # one (X, Y) cannot be replayed against another query on the same graph.
    if step.rule in ("tian_c_decomposition", "idc_rule2_exchange"):
        if step.inputs.get("x") != q.intervention.atom:
            raise VerificationError(
                f"{step.rule}.x does not match verification context query",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                f"{step.rule}.y does not match verification context query",
                step_index=step_index, rule=step.rule,
            )


def _assert_cause_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    q: CauseQuery = context.query
    if step.rule in ("no_directed_path", "cause_via_directed_path"):
        if step.inputs.get("src") != q.from_atom:
            raise VerificationError(
                f"{step.rule}.src does not match cause query from_atom",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("dst") != q.to_atom:
            raise VerificationError(
                f"{step.rule}.dst does not match cause query to_atom",
                step_index=step_index, rule=step.rule,
            )


def _assert_assoc_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    q: AssocQuery = context.query
    if step.rule in (
        "d_separated",
        "d_connected_via_open_path",
        "m_separation_witness",
        "m_connection_witness",
    ):
        if step.inputs.get("x") != q.left:
            raise VerificationError(
                f"{step.rule}.x does not match assoc query left atom",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q.right:
            raise VerificationError(
                f"{step.rule}.y does not match assoc query right atom",
                step_index=step_index, rule=step.rule,
            )
        if step.rule in ("m_separation_witness", "m_connection_witness"):
            step_cond = step.inputs.get("z", frozenset())
        else:
            step_cond = step.inputs.get("conditioning", frozenset())
        if frozenset(step_cond) != frozenset(q.given):
            raise VerificationError(
                f"{step.rule} conditioning set does not match assoc query given",
                step_index=step_index, rule=step.rule,
            )


def _is_formula_expr(value: object) -> bool:
    return isinstance(value, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr))


def _resolve_formula_input(
    raw_formula: object,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
    step_index: int,
    rule: str,
) -> object:
    """Resolve a formula input that may be a direct FormulaExpr or a
    StepRef to an earlier formula-producing step."""
    if isinstance(raw_formula, StepRef):
        source_step = step_by_id.get(raw_formula.step_id)
        source_out = step_output_by_id.get(raw_formula.step_id)
        if source_step is None or source_out is None:
            raise VerificationError(
                f"{rule}.formula references unknown step {raw_formula.step_id!r}",
                step_index=step_index, rule=rule,
            )
        if not _is_formula_expr(source_out):
            raise VerificationError(
                f"{rule}.formula StepRef({raw_formula.step_id!r}) does not point to a FormulaExpr",
                step_index=step_index, rule=rule,
            )
        return source_out
    return raw_formula


def _assert_numeric_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Numeric counterpart of ``_assert_query_binding``.

    Effect derivations typically contain R3 / R4 structural steps; the
    identify-style binding rules still apply to those steps, but the X,
    Y and given come from ``EffectQuery``'s atoms / values rather than
    from ``IdentifyQuery``. Probability derivations skip R3 / R4 entirely
    and jump straight to ``formula_evaluation`` over the query's direct
    ``ProbabilityRefExpr``.
    """
    q = context.query

    if isinstance(q, EffectQuery):
        if step.rule == "backdoor_criterion":
            if step.inputs.get("x") != q.intervention.atom:
                raise VerificationError(
                    "backdoor_criterion.x does not match effect query intervention atom",
                    step_index=step_index, rule=step.rule,
                )
            if step.inputs.get("y") != q.target.atom:
                raise VerificationError(
                    "backdoor_criterion.y does not match effect query target atom",
                    step_index=step_index, rule=step.rule,
                )
            step_given = step.inputs.get("given", frozenset())
            expected = frozenset(g.atom for g in q.given)
            if frozenset(step_given) != expected:
                raise VerificationError(
                    "backdoor_criterion.given does not match effect query given set",
                    step_index=step_index, rule=step.rule,
                )

        if step.rule == "backdoor_adjustment_formula":
            expected_intervention = ValuedAtom(
                atom=q.intervention.atom, value=q.intervention.value,
            )
            if step.inputs.get("target") != q.target:
                raise VerificationError(
                    "backdoor_adjustment_formula.target does not match effect query target",
                    step_index=step_index, rule=step.rule,
                )
            if step.inputs.get("intervention") != expected_intervention:
                raise VerificationError(
                    "backdoor_adjustment_formula.intervention does not match effect query intervention",
                    step_index=step_index, rule=step.rule,
                )
            step_given = step.inputs.get("given", ())
            if frozenset(step_given) != frozenset(q.given):
                raise VerificationError(
                    "backdoor_adjustment_formula.given does not match effect query given",
                    step_index=step_index, rule=step.rule,
                )

        if step.rule == "formula_evaluation":
            formula = _resolve_formula_input(
                step.inputs.get("formula"),
                step_by_id,
                step_output_by_id,
                step_index,
                step.rule,
            )
            matching_witness = any(
                prev_step.rule in IDENTIFICATION_FORMULA_RULES
                and step_output_by_id.get(step_id) == formula
                for step_id, prev_step in step_by_id.items()
            )
            if not matching_witness:
                raise VerificationError(
                    "formula_evaluation.formula does not match any prior "
                    "identification-formula witness (backdoor / front-door) "
                    "for this effect query",
                    step_index=step_index, rule=step.rule,
                )

    if isinstance(q, ProbabilityQuery):
        if step.rule == "probability_ref_lookup":
            if step.inputs.get("target") != q.target:
                raise VerificationError(
                    "probability_ref_lookup.target does not match probability query",
                    step_index=step_index, rule=step.rule,
                )
            if tuple(step.inputs.get("given", ())) != tuple(q.given):
                raise VerificationError(
                    "probability_ref_lookup.given does not match probability query",
                    step_index=step_index, rule=step.rule,
                )

        if step.rule == "formula_evaluation":
            formula = _resolve_formula_input(
                step.inputs.get("formula"),
                step_by_id,
                step_output_by_id,
                step_index,
                step.rule,
            )
            expected = ProbabilityRefExpr(target=q.target, given=q.given)
            if formula != expected:
                raise VerificationError(
                    "formula_evaluation.formula does not match probability query",
                    step_index=step_index, rule=step.rule,
                )


def _assert_counterfactual_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Current narrow counterfactual derivations have a single rule whose
    semantics come entirely from the verification context.

    The only explicit input we require is the graph, and the rule itself
    rechecks that against ``ctx.graph``. Query-specific binding therefore
    happens inside the rule rather than here.
    """
    return None


def _walk(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    binding_asserter: Callable[
        [DerivationStep, VerificationContext, int, dict[str, DerivationStep], dict[str, object]],
        None,
    ],
) -> tuple[dict[str, DerivationStep], dict[str, object]]:
    """Shared walk used by both ``verify_identify`` and ``verify_numeric``.

    Per-step:
      1. Rule must be known.
      2. Query binding must hold (caller-supplied asserter).
      3. Any ``StepRef`` at the top level of ``inputs`` must point at
         an already-processed step.
      4. Dispatch to the rule handler.
      5. Register the step's output (and step object) for later
         StepRef resolution.

    Does NOT check the final step's output — that's caller-specific.
    """
    if not derivation:
        raise VerificationError(
            "derivation is empty; nothing to verify",
            step_index=None, rule=None,
        )

    step_output_by_id: dict[str, object] = {}
    step_by_id: dict[str, DerivationStep] = {}

    for i, step in enumerate(derivation):
        if not known_rule(step.rule):
            raise RuleNotFoundError(
                f"unknown rule: {step.rule!r}",
                step_index=i, rule=step.rule,
            )

        for key, value in step.inputs.items():
            if isinstance(value, StepRef):
                if value.step_id not in step_output_by_id:
                    raise StepRefError(
                        f"{step.rule}.{key} = StepRef({value.step_id!r}) but "
                        f"no earlier step has that id",
                        step_index=i, rule=step.rule,
                    )

        binding_asserter(step, context, i, step_by_id, step_output_by_id)

        dispatch_rule(
            rule_name=step.rule,
            ctx=context,
            inputs=step.inputs,
            claimed_output=step.output,
            step_index=i,
            step_by_id=step_by_id,
            step_output_by_id=step_output_by_id,
        )

        if step.step_id is not None:
            if step.step_id in step_output_by_id:
                raise VerificationError(
                    f"duplicate step_id {step.step_id!r}",
                    step_index=i, rule=step.rule,
                )
            step_by_id[step.step_id] = step
            step_output_by_id[step.step_id] = step.output

    return step_by_id, step_output_by_id


def verify_identify(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify an identify-query derivation.

    Raises ``VerificationError`` on reject. Returns ``None`` on accept.
    """
    if not isinstance(context.query, IdentifyQuery):
        raise VerificationError(
            "verify_identify requires an IdentifyQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if claimed_result.value is True:
        expected_finals = (
            "identify_via_backdoor",
            "identify_via_front_door",
            "identify_via_iv",
            "identify_via_tian",
            "identify_via_idc",
        )
    else:
        expected_finals = (
            "unidentifiable_via_backdoor",
            "tian_hedge_witness",
        )
    if derivation[-1].rule not in expected_finals:
        raise VerificationError(
            f"identify derivation must end in one of {expected_finals}; "
            f"got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    # Phase 15 — semantic backbone. The per-method rules above prove the
    # METHOD was applied; they do not prove the FORMULA computes the true
    # interventional quantity (Phase 14 shipped a numerically-wrong IDC
    # fraction that passed every structural check). For nonparametric
    # point identification, probe the formula against random SCMs
    # consistent with the graph and reject a numeric mismatch.
    if claimed_result.value is True and derivation[-1].rule in _NONPARAM_POINT_ID_RULES:
        formula = _extract_identify_formula(derivation)
        if formula is not None:
            q = context.query
            domains = context.theta.domains if context.theta is not None else {}
            probe = probe_identify_formula(
                context.graph, context.bidirected,
                x=q.intervention.atom, x_value=q.intervention.value,
                y=q.target, given=q.given, formula=formula, domains=domains,
            )
            if probe.status == "mismatch":
                raise VerificationError(
                    "identify formula fails semantic verification: it does "
                    "not compute the true interventional quantity in a model "
                    f"consistent with the graph. {probe.detail}",
                    step_index=len(derivation) - 1, rule=derivation[-1].rule,
                )


def verify_numeric_estimate(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Phase 7.1 — verify a data-based effect estimate derivation.

    The derivation must end in ``numeric_backdoor_estimate``. The rule
    handler audits metadata self-consistency (method enum, point in CI,
    data_hash format, adjustment matches structural witness) without
    re-training — a deliberate relaxation of the identification-layer
    audits because numerical reproduction is prohibitively expensive
    for a verifier pass.
    """
    if not isinstance(context.query, EffectQuery):
        raise VerificationError(
            "verify_numeric_estimate requires an EffectQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    allowed_finals = (
        "numeric_backdoor_estimate",
        # Doubly-robust estimators on the same backdoor identification:
        # inverse-probability weighting, the augmented (AIPW) form, and
        # the targeted-substitution (TMLE) form.
        "numeric_aipw_estimate",
        "numeric_tmle_estimate",
        "numeric_ipw_estimate",
        "numeric_frontdoor_estimate",
        "numeric_iv_estimate",
        # Over-identified 2SLS (q >= 2 instruments) — metadata + structural
        # licensing terminal; the Sargan / point re-derivation from the
        # recorded moment matrices is verify_iv_overid_numeric (kernel-called).
        "numeric_iv_overid_estimate",
        # General-ID (c-factor) non-parametric plug-in — the effect is
        # point-identified only through the general ID algorithm (e.g. the
        # napkin); the derivation ends in the plug-in terminal atop a
        # general_id_criterion structural witness.
        "numeric_general_id_estimate",
        # Measurement-error correction (frontier E) — confusion-matrix inversion
        # atop a back-door identification (backdoor_criterion witness). Metadata
        # + structural-licensing terminal; the matrix inversion / point
        # re-derivation from the recorded confusion matrix + value-count vectors
        # is verify_measurement_correction_numeric (kernel-called), since those
        # matrices don't fit derivation-input serialization.
        "numeric_measurement_correction_estimate",
        # Joint (treatment-set) back-door data estimate — joint contrast
        # + treatment×treatment interaction via the joint g-formula.
        "numeric_joint_backdoor_estimate",
        # Transport-numeric (Cole-Stuart post-stratification) is a
        # structural transport identification with a numeric value
        # attached — its derivation legitimately ends in the structural
        # identify_via_transport terminal (the same one verify_effect_
        # structural accepts), not a re-derived numeric terminal. Audit it
        # at the relaxed numeric level rather than crashing on the
        # numerically_solved flip.
        "identify_via_transport",
        # Longitudinal g-formula / IPW-MSM (Phase 7.L) — same pattern as
        # transport: the derivation ends in the structural
        # identify_via_gformula terminal and the estimation dispatch flips
        # the result to numerically_solved with the strategy-contrast
        # number attached. The number's own re-derivation is verify_
        # longitudinal_numeric (called from the kernel), not this terminal.
        "identify_via_gformula",
    )
    if derivation[-1].rule not in allowed_finals:
        raise VerificationError(
            f"numeric-estimate derivation must end in one of {allowed_finals}; "
            f"got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


_OVB_TOL = 1e-6


def verify_ovb_sensitivity(block: dict) -> None:
    """Independently re-derive a Cinelli-Hazlett OVB sensitivity block and
    reject on mismatch.

    Unlike the data-refit point estimators (which get a metadata audit
    only, because re-fitting needs the data), every number in this block
    is a CLOSED FORM of the recorded regression statistics — the treatment
    t-value, the residual dof, and each benchmark covariate's partial R²s.
    So the verifier recomputes them from scratch with a SECOND,
    independent transcription of the formulas (it does not import the
    producer's functions) and checks the recorded values match. This is a
    genuine re-derivation: it catches tampering, serialization corruption,
    and any internal inconsistency between the raw statistics and the
    reported robustness value / partial R² / bounds.
    """
    import math
    from scipy.stats import t as _t_dist

    def _close(recomputed, recorded, name):
        if recorded is None or not math.isfinite(recomputed):
            raise VerificationError(
                f"ovb_sensitivity.{name}: recomputed {recomputed}, "
                f"recorded {recorded!r}",
                step_index=None, rule="ovb_sensitivity",
            )
        if abs(recomputed - recorded) > _OVB_TOL + 1e-6 * abs(recorded):
            raise VerificationError(
                f"ovb_sensitivity.{name}: recomputed {recomputed}, "
                f"recorded {recorded}",
                step_index=None, rule="ovb_sensitivity",
            )

    def _partial_r2(t, dof):
        return t * t / (t * t + dof)

    def _rv(t, dof, q, alpha):
        fq = q * abs(t / math.sqrt(dof))
        f_crit = abs(_t_dist.ppf(alpha / 2.0, dof - 1)) / math.sqrt(dof - 1)
        fqa = fq - f_crit
        if fqa < 0:
            return 0.0
        if f_crit > 0 and fq > 1.0 / f_crit:
            return (fq * fq - f_crit * f_crit) / (1.0 + fq * fq)
        return 0.5 * (math.sqrt(fqa ** 4 + 4.0 * fqa ** 2) - fqa ** 2)

    t = block["t_statistic"]
    dof = block["dof"]
    q = block["q"]
    alpha = block["alpha"]
    est = block["estimate"]
    se = block["se"]

    _close(_partial_r2(t, dof), block["partial_r2"], "partial_r2")
    _close(_rv(t, dof, q, 1.0), block["robustness_value_q"], "robustness_value_q")
    _close(_rv(t, dof, q, alpha), block["robustness_value_qa"], "robustness_value_qa")

    for b in block.get("benchmarks", []):
        kd, ky = b["kd"], b["ky"]
        r2dxj, r2yxj = b["r2dxj_x"], b["r2yxj_dx"]
        cov = b.get("covariate", "?")
        # Re-derive the bound; None means the producer flagged it undefined.
        try:
            r2dz = kd * (r2dxj / (1.0 - r2dxj))
            r2zxj = kd * (r2dxj ** 2) / ((1.0 - kd * r2dxj) * (1.0 - r2dxj))
            r2yz = (
                ((math.sqrt(ky) + math.sqrt(r2zxj)) / math.sqrt(1.0 - r2zxj)) ** 2
                * (r2yxj / (1.0 - r2yxj))
            )
            defined = math.isfinite(r2dz) and math.isfinite(r2yz)
        except (ValueError, ZeroDivisionError):
            defined = False
            r2dz = r2yz = float("nan")

        if not defined:
            if b["r2dz_x"] is not None or b["valid"]:
                raise VerificationError(
                    f"ovb_sensitivity.benchmark[{cov}]: bound is undefined "
                    f"but the block reports r2dz_x={b['r2dz_x']!r}, "
                    f"valid={b['valid']}",
                    step_index=None, rule="ovb_sensitivity",
                )
            continue

        _close(r2dz, b["r2dz_x"], f"benchmark[{cov}].r2dz_x")
        _close(r2yz, b["r2yz_dx"], f"benchmark[{cov}].r2yz_dx")

        expected_valid = 0.0 <= r2dz < 1.0 and 0.0 <= r2yz <= 1.0
        if expected_valid != b["valid"]:
            raise VerificationError(
                f"ovb_sensitivity.benchmark[{cov}].valid: recomputed "
                f"{expected_valid}, recorded {b['valid']}",
                step_index=None, rule="ovb_sensitivity",
            )
        if expected_valid:
            bf = math.sqrt(r2yz * r2dz / (1.0 - r2dz))
            bias = bf * se * math.sqrt(dof)
            adj = math.copysign(1.0, est) * (abs(est) - bias)
            _close(adj, b["adjusted_estimate"], f"benchmark[{cov}].adjusted_estimate")


_EVALUE_TOL = 1e-6


def verify_e_value(estimate: dict) -> None:
    """Independently re-derive a VanderWeele-Ding E-value block and reject on
    mismatch.

    Like the OVB block (and unlike the data-refit point estimate, which gets a
    metadata audit only), every number here is a CLOSED FORM of the audited
    headline ATE and one data-derived conversion input the block records — the
    control-arm baseline rate (binary path) or the outcome SD (continuous
    path). So the verifier recomputes the risk ratio and BOTH E-values from
    scratch with a SECOND, independent transcription of the formulas — pairing
    them with the SAME point / CI the pipeline already audits, so a tamper of
    the sensitivity block alone (e.g. inflating a fragile finding's E-value to
    look robust, or hiding a fragile one) cannot pass.

    ``estimate`` is the full ``numeric_estimate`` dict; a missing
    ``sensitivity_analysis`` sub-block is a no-op.
    """
    import math

    block = estimate.get("sensitivity_analysis")
    if block is None:
        return

    # --- second, independent transcription of the formulas ------------------
    def _evalue(rr):
        # VanderWeele & Ding 2017: E = RR + √(RR·(RR−1)), symmetric about RR=1.
        if rr is None or not math.isfinite(rr) or rr <= 0:
            return None
        if rr < 1.0:
            rr = 1.0 / rr
        if rr == 1.0:
            return 1.0
        return rr + math.sqrt(rr * (rr - 1.0))

    def _closer_to_null(point, lo, hi):
        # Whichever CI bound sits on the point's side of zero but nearer to it.
        if point is None or lo is None or hi is None:
            return None
        if point >= 0:
            return lo if lo >= 0 else None
        return hi if hi <= 0 else None

    def _close(recomputed, recorded, name):
        # None must match None; a finite value must match within tolerance.
        if recomputed is None or recorded is None:
            if recomputed is None and recorded is None:
                return
            raise VerificationError(
                f"e_value.{name}: recomputed {recomputed!r}, "
                f"recorded {recorded!r}",
                step_index=None, rule="e_value",
            )
        if not math.isfinite(recomputed):
            raise VerificationError(
                f"e_value.{name}: recomputed non-finite {recomputed}",
                step_index=None, rule="e_value",
            )
        if abs(recomputed - recorded) > _EVALUE_TOL + 1e-6 * abs(recorded):
            raise VerificationError(
                f"e_value.{name}: recomputed {recomputed}, recorded {recorded}",
                step_index=None, rule="e_value",
            )

    # --- pull the SAME audited headline ATE the block was built on ----------
    if "decomposition" in estimate:
        te = estimate["decomposition"]["te"]
        ate, lo, hi = te.get("point"), te.get("ci_lower"), te.get("ci_upper")
    else:
        ate = estimate.get("point")
        lo, hi = estimate.get("ci_lower"), estimate.get("ci_upper")
    ci_bound = _closer_to_null(ate, lo, hi)

    path = block.get("path")
    rr = None
    e_ci = None

    if path == "binary":
        baseline = block.get("baseline_rate")
        if baseline is not None and 0.0 < baseline < 1.0 and ate is not None:
            treated = baseline + ate
            if 0.0 < treated < 1.0:
                rr = treated / baseline
                # Producer computes the CI-bound E-value only once the point
                # RR is defined — mirror that nesting exactly.
                if ci_bound is not None:
                    ci_treated = baseline + ci_bound
                    if 0.0 < ci_treated < 1.0:
                        e_ci = _evalue(ci_treated / baseline)
    elif path == "continuous":
        sd = block.get("outcome_sd")
        if (sd is not None and sd > 0.0 and math.isfinite(sd)
                and ate is not None and math.isfinite(ate)):
            rr = math.exp(0.91 * (ate / sd))   # Chinn 2000 SMD→log-RR = 0.91
            if ci_bound is not None and math.isfinite(ci_bound):
                e_ci = _evalue(math.exp(0.91 * (ci_bound / sd)))
    else:
        raise VerificationError(
            f"e_value.path: unknown conversion path {path!r}",
            step_index=None, rule="e_value",
        )

    _close(rr, block.get("risk_ratio"), "risk_ratio")
    _close(_evalue(rr), block.get("e_value"), "e_value")
    _close(e_ci, block.get("e_value_ci_bound"), "e_value_ci_bound")


def verify_dose_response_curve(estimate: dict) -> None:
    """Audit a dose-response curve's CONSTRUCTION invariants and reject on
    violation.

    The curve values come from a black-box EconML DML / DRLearner fit, so —
    like every data-refit estimator — the verifier cannot re-derive them
    without re-running the fit on the data (prohibitively expensive, and the
    data is not in the envelope). The numeric_backdoor_estimate metadata
    audit only inspects the derivation's headline scalar (the last curve
    point via the adapter), leaving the curve ARRAY — which IS the answer for
    a dose-response query — checked for JSON shape only. This closes that
    hole with the invariants the curve satisfies BY CONSTRUCTION, independent
    of the fitted numbers:

    - one point per sampling point, each x equal to its sampling point;
    - reference_point equals the first sampling point and the first curve x;
    - the reference point's effect is 0 (Y(x_ref) − Y(x_ref) = 0), with an
      interval that brackets 0;
    - every point's effect lies within its own [ci_lower, ci_upper].

    These catch a corrupted / truncated / reordered curve, a point that
    escaped its interval, and a reference effect moved off zero — the tamper
    classes the metadata-only audit misses. It does NOT catch a fully
    self-consistent forged curve (effect + interval moved together to a
    plausible pair): re-deriving ML-fitted values is out of scope for any
    data-refit estimator's verifier, the same ceiling backdoor / IV / TMLE
    point estimates sit at.

    ``estimate`` is the full ``numeric_estimate`` dict; a missing
    ``dose_response_curve`` is a no-op.
    """
    import math

    curve = estimate.get("dose_response_curve")
    if curve is None:
        return

    def _fail(msg):
        raise VerificationError(
            f"dose_response_curve: {msg}",
            step_index=None, rule="dose_response_curve",
        )

    sampling = estimate.get("sampling_points")
    reference = estimate.get("reference_point")
    if not isinstance(curve, list) or not curve:
        _fail(f"curve must be a non-empty list; got {curve!r}")
    if not isinstance(sampling, list) or len(sampling) != len(curve):
        _fail(
            f"curve has {len(curve)} points but sampling_points has "
            f"{len(sampling) if isinstance(sampling, list) else sampling!r}"
        )

    # Exact-by-construction facts get a hair of float tolerance; the
    # point-in-interval bound gets a looser relative slack.
    def _eq(a, b, scale=1.0):
        return a is not None and b is not None and \
            abs(a - b) <= 1e-9 + 1e-9 * abs(scale)

    for i, pt in enumerate(curve):
        x = pt.get("x")
        eff = pt.get("effect")
        lo = pt.get("ci_lower")
        hi = pt.get("ci_upper")
        sp = sampling[i]
        if x is None or eff is None or not math.isfinite(x) or not math.isfinite(eff):
            _fail(f"point[{i}] has a missing / non-finite x or effect: {pt!r}")
        if not _eq(x, sp, sp):
            _fail(f"point[{i}].x = {x} does not match sampling_points[{i}] = {sp}")
        # A real estimator's point always lies inside its own interval
        # (point ± z·se). A point outside it is impossible without tampering.
        if lo is not None and hi is not None:
            if lo > hi + 1e-9:
                _fail(f"point[{i}] interval is inverted: [{lo}, {hi}]")
            slack = 1e-6 * max(1.0, abs(eff), abs(lo), abs(hi))
            if not (lo - slack <= eff <= hi + slack):
                _fail(
                    f"point[{i}].effect = {eff} lies outside its interval "
                    f"[{lo}, {hi}]"
                )

    # Reference point (first) — pinned by construction.
    if not _eq(reference, sampling[0], sampling[0]):
        _fail(
            f"reference_point = {reference} does not equal sampling_points[0] "
            f"= {sampling[0]}"
        )
    ref_pt = curve[0]
    if abs(ref_pt["effect"]) > 1e-6:
        _fail(
            f"reference point effect = {ref_pt['effect']} must be 0 "
            "(Y(x_ref) − Y(x_ref) = 0)"
        )
    rlo, rhi = ref_pt.get("ci_lower"), ref_pt.get("ci_upper")
    if rlo is not None and rhi is not None and not (rlo <= 1e-6 and rhi >= -1e-6):
        _fail(f"reference point interval [{rlo}, {rhi}] must bracket 0")


_MEDIATION_TOL = 1e-6


def verify_mediation_numeric(estimate: dict) -> None:
    """Audit the numeric answer blocks riding on a mediation structural
    result and reject on violation.

    Mediation stays ``structurally_solved`` (routed to
    verify_effect_structural, which checks only the identify_via_mediation
    terminal), so the numbers attached to it — the Imai NDE/NIE
    decomposition and the two four-way splits — otherwise ship with no
    numeric audit at all: today a tampered ``err_cde`` or ``prop_mediated``
    passes ``themis.verify`` untouched.

    Three blocks, two levels of check:

    - ``four_way_ratio`` (STRONG): every ERR component is a closed form of
      the fitted logistic outcome/mediator coefficients, now recorded under
      ``coefficients``. Re-derive each err_* / prop_* from those
      coefficients through VanderWeele's decomposition and confirm the block
      matches — so a tamper of any reported value, even a self-consistent
      one, is caught because it no longer agrees with the recorded fit.
      Independently (not trusting that oracle), the transcription-free
      identities are re-checked: the four ERR pieces sum to total_err,
      total_err = total_rr − 1, and each proportion equals its component
      ratio.
    - ``four_way_decomposition`` (difference scale) (STRONG when the cell
      means are recorded): the split is a closed form of six standardized
      cell means — p_am = E[Y|A=a,M=m] and q_a = E[M|A=a]. Those means are
      now recorded under ``sufficient_statistics.cell_means``, so the
      verifier re-derives CDE / INTref / INTmed / PIE / TE from them with an
      independent transcription of VanderWeele 14.1b and rejects any tamper —
      even a fully self-consistent one, because it no longer agrees with the
      recorded means. When the means are absent (a hand-built or older block)
      it falls back to the construction identities (TE = sum of parts; each
      proportion = its ratio), which catch only a single-component tamper.
    - ``decomposition`` (Imai NDE/NIE) (STRONG on the linear path, INVARIANTS
      on the logit path): the difference-scale PNDE = CDE + INTref and TNIE =
      INTmed + PIE are exact closed forms of the SAME cell means, and on a
      LINEAR outcome they equal the reported nde / nie byte-for-byte
      (linearity makes the plug-in E[M|X] equal the m∈{0,1} mixture). So for
      ``mediation_linear_imai`` the verifier cross-checks nde / nie against
      the cell-mean bridge. On the logit path the reported nde / nie
      integrate M by Monte Carlo and legitimately differ from the {0,1}
      grid — not re-derivable from the cell means without re-running the
      simulation — so only the construction identities are checked there (a
      self-consistent forgery of the logit nde / nie is the honest ceiling).

    ``estimate`` is the full ``numeric_estimate`` dict; each block is
    audited only when present.
    """
    import math

    def _fail(msg, rule):
        raise VerificationError(msg, step_index=None, rule=rule)

    def _isnan_none(v):
        return v is None or (isinstance(v, float) and math.isnan(v))

    def _close(a, b, name, rule):
        # Both undefined (construction gives nan, e.g. total_err == 0) is
        # consistent; one defined and the other not is a mismatch.
        if _isnan_none(a) or _isnan_none(b):
            if _isnan_none(a) and _isnan_none(b):
                return
            _fail(f"{name}: recomputed {a!r}, recorded {b!r}", rule)
        if not math.isfinite(a):
            _fail(f"{name}: recomputed non-finite {a}", rule)
        if abs(a - b) > _MEDIATION_TOL + 1e-6 * abs(b):
            _fail(f"{name}: recomputed {a}, recorded {b}", rule)

    # ---- four_way_ratio: strong re-derivation from recorded coefficients ----
    fr = estimate.get("four_way_ratio")
    if fr is not None:
        coeffs = fr.get("coefficients")
        if coeffs is None:
            _fail("four_way_ratio.coefficients missing — cannot re-derive",
                  "four_way_ratio")
        from ..estimation.four_way import (
            four_way_ratio_decomposition,
            four_way_ratio_decomposition_continuous,
        )
        t1, t2, t3 = coeffs["t1"], coeffs["t2"], coeffs["t3"]
        b0, b1, bcc = coeffs["b0"], coeffs["b1"], coeffs["bcc"]
        mstar = coeffs["mediator_reference"]
        mscale = fr.get("mediator_scale")
        if mscale == "binary":
            comps = four_way_ratio_decomposition(
                t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, bcc=bcc,
                a1=1.0, a0=0.0, mstar=mstar,
            )
        elif mscale == "continuous":
            ss_m = fr.get("mediator_residual_variance")
            if ss_m is None:
                _fail("four_way_ratio: continuous scale needs "
                      "mediator_residual_variance", "four_way_ratio")
            comps = four_way_ratio_decomposition_continuous(
                t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, ss_m=ss_m, bcc=bcc,
                a1=1.0, a0=0.0, mstar=mstar,
            )
        else:
            _fail(f"four_way_ratio.mediator_scale unknown: {mscale!r}",
                  "four_way_ratio")

        for recomputed, key in (
            (comps.err_cde, "err_cde"), (comps.err_intref, "err_intref"),
            (comps.err_intmed, "err_intmed"), (comps.err_pie, "err_pie"),
            (comps.total_err, "total_err"), (comps.total_rr, "total_rr"),
            (comps.prop_mediated, "prop_mediated"),
            (comps.prop_interaction, "prop_interaction"),
            (comps.prop_eliminated, "prop_eliminated"),
        ):
            _close(recomputed, fr[key]["point"],
                   f"four_way_ratio.{key}", "four_way_ratio")

        # transcription-free internal identities (independent of the oracle)
        ec, er = fr["err_cde"]["point"], fr["err_intref"]["point"]
        em, ep = fr["err_intmed"]["point"], fr["err_pie"]["point"]
        te, tr = fr["total_err"]["point"], fr["total_rr"]["point"]
        _close(ec + er + em + ep, te, "four_way_ratio.sum==total_err",
               "four_way_ratio")
        _close(tr - 1.0, te, "four_way_ratio.total_rr-1==total_err",
               "four_way_ratio")
        if abs(te) > _MEDIATION_TOL:
            _close((em + ep) / te, fr["prop_mediated"]["point"],
                   "four_way_ratio.prop_mediated_identity", "four_way_ratio")
            _close((er + em) / te, fr["prop_interaction"]["point"],
                   "four_way_ratio.prop_interaction_identity", "four_way_ratio")
            _close((er + em + ep) / te, fr["prop_eliminated"]["point"],
                   "four_way_ratio.prop_eliminated_identity", "four_way_ratio")

    # ---- four_way_decomposition (difference scale) --------------------------
    fw = estimate.get("four_way_decomposition")
    # PNDE / TNIE re-derived from the cell means, shared with the NDE/NIE
    # cross-check below. None unless the cell means were recorded.
    pnde_cells = tnie_cells = None
    if fw is not None:
        cde, ir = fw["cde"]["point"], fw["intref"]["point"]
        im, pie = fw["intmed"]["point"], fw["pie"]["point"]
        te = fw["te"]["point"]

        cells = (fw.get("sufficient_statistics") or {}).get("cell_means")
        if cells is not None:
            # STRONG: independent transcription of VanderWeele 14.1b
            # (four_way.py's oracle) — re-derive every component from the
            # recorded standardized cell means. A self-consistent tamper of
            # the reported components no longer passes: it must also rewrite
            # the cell means it claims to have been computed from.
            p00, p01 = cells["p00"], cells["p01"]
            p10, p11 = cells["p10"], cells["p11"]
            q0, q1 = cells["q0"], cells["q1"]
            ai = p11 - p10 - p01 + p00
            r_cde = p10 - p00
            r_intref = ai * q0
            r_intmed = ai * (q1 - q0)
            r_pie = (p01 - p00) * (q1 - q0)
            r_te = r_cde + r_intref + r_intmed + r_pie
            _close(r_cde, cde, "four_way_decomposition.cde",
                   "four_way_decomposition")
            _close(r_intref, ir, "four_way_decomposition.intref",
                   "four_way_decomposition")
            _close(r_intmed, im, "four_way_decomposition.intmed",
                   "four_way_decomposition")
            _close(r_pie, pie, "four_way_decomposition.pie",
                   "four_way_decomposition")
            _close(r_te, te, "four_way_decomposition.te",
                   "four_way_decomposition")
            ai_rec = fw.get("additive_interaction")
            if ai_rec is not None:
                _close(ai, ai_rec,
                       "four_way_decomposition.additive_interaction",
                       "four_way_decomposition")
            pnde_cells = r_cde + r_intref   # = NDE on the difference scale
            tnie_cells = r_intmed + r_pie   # = NIE on the difference scale

        # Construction identities — also cover the no-cell-means fallback.
        _close(cde + ir + im + pie, te, "four_way_decomposition.sum==te",
               "four_way_decomposition")
        if abs(te) > _MEDIATION_TOL:
            _close((im + pie) / te, fw["prop_mediated"]["point"],
                   "four_way_decomposition.prop_mediated",
                   "four_way_decomposition")
            _close((ir + im) / te, fw["prop_interaction"]["point"],
                   "four_way_decomposition.prop_interaction",
                   "four_way_decomposition")

    # ---- decomposition (Imai NDE/NIE) --------------------------------------
    dec = estimate.get("decomposition")
    if dec is not None and {"nde", "nie", "te"} <= dec.keys():
        nde, nie = dec["nde"]["point"], dec["nie"]["point"]
        te = dec["te"]["point"]
        # STRONG (linear path only): the reported nde/nie equal the
        # cell-mean bridge exactly for a linear outcome. On the logit path
        # they come from a Monte-Carlo integration over M and legitimately
        # differ, so the bridge is not applied there.
        if (
            pnde_cells is not None
            and estimate.get("method") == "mediation_linear_imai"
        ):
            _close(pnde_cells, nde,
                   "decomposition.nde==PNDE(cell_means)", "decomposition")
            _close(tnie_cells, nie,
                   "decomposition.nie==TNIE(cell_means)", "decomposition")
        # STRONG (JOINT linear path): re-derive the joint NDE/NIE from the
        # recorded outcome coefficients + per-mediator standardized means,
        # independently of the estimator. For a linear outcome with only
        # X:M_j interactions (no M_j:M_l), the joint natural effects are
        #   NDE = beta_x + sum_j gamma_j * q_j0
        #   NIE = sum_j (beta_j + gamma_j) * (q_j1 - q_j0)
        # (the cross-mediator correlation cancels in the expectation). On the
        # joint LOGIT path the reported NDE/NIE come from a Monte-Carlo joint
        # integration over M and are not re-derivable here — only the
        # construction identities below apply (the honest ceiling).
        if estimate.get("method") == "mediation_joint_linear":
            ss = dec.get("sufficient_statistics")
            if ss is None:
                _fail(
                    "mediation_joint_linear decomposition missing "
                    "sufficient_statistics — cannot re-derive",
                    "decomposition",
                )
            oc = ss.get("outcome_coefficients") or {}
            mmeans = ss.get("mediator_means") or {}
            beta_x = oc.get("treatment")
            betas = oc.get("mediators") or {}
            gammas = oc.get("interactions") or {}
            if beta_x is None or not betas or set(betas) != set(mmeans):
                _fail(
                    "mediation_joint_linear sufficient_statistics malformed "
                    "(missing treatment / mediators / mediator_means mismatch)",
                    "decomposition",
                )
            nde_rd = float(beta_x) + sum(
                float(gammas[name]) * float(mmeans[name]["m0"])
                for name in betas
            )
            nie_rd = sum(
                (float(betas[name]) + float(gammas[name]))
                * (float(mmeans[name]["m1"]) - float(mmeans[name]["m0"]))
                for name in betas
            )
            _close(nde_rd, nde,
                   "decomposition.nde==joint_bridge(coeffs,means)",
                   "decomposition")
            _close(nie_rd, nie,
                   "decomposition.nie==joint_bridge(coeffs,means)",
                   "decomposition")
            # STRONG (JOINT linear path) CDE-for-a-set: holding every mediator
            # fixed at m*, the linear outcome gives CDE(m*) = beta_x + sum_j
            # gamma_j * m* exactly (the covariates cancel in the difference).
            # So CDE(m*=0) = beta_x and CDE(m*=1) = beta_x + sum_j gamma_j —
            # re-derived here from the SAME recorded coefficients, independent
            # of the estimator (a self-consistent forgery of a cde point is
            # caught). On the joint LOGIT path CDE is a plug-in over the
            # covariates and is not re-derivable here (construction ceiling).
            cde_blk = dec.get("cde")
            if cde_blk is not None:
                sum_g = sum(float(gammas[name]) for name in betas)
                ctrl = cde_blk.get("reference_control")
                trt = cde_blk.get("reference_treated")
                if ctrl is not None:
                    _close(float(beta_x), ctrl["point"],
                           "decomposition.cde[m*=0]==beta_x", "decomposition")
                if trt is not None:
                    _close(float(beta_x) + sum_g, trt["point"],
                           "decomposition.cde[m*=1]==beta_x+sum_gamma",
                           "decomposition")
        _close(nde + nie, te, "decomposition.nde+nie==te", "decomposition")
        pm = dec.get("proportion_mediated")
        if pm is not None and abs(te) > _MEDIATION_TOL:
            _close(nie / te, pm["point"], "decomposition.proportion_mediated",
                   "decomposition")


_IV_OVERID_TOL = 1e-6


def verify_iv_overid_numeric(estimate: dict) -> None:
    """Re-derive an over-identified 2SLS estimate — the point, the Sargan J, its
    p-value, and (when present) the heteroskedasticity-robust Hansen J — from the
    recorded residualised moment matrices, and reject on mismatch.

    Over-identified 2SLS rides on a ``numerically_solved`` IV result whose
    derivation ends in ``numeric_iv_overid_estimate`` (metadata + structural
    licensing only — the moment MATRICES don't fit the derivation-input
    serialization). This is the strong numeric counterpart: a SECOND,
    independent transcription of the closed forms

        β = (Z'x)' (Z'Z)⁻¹ (Z'y) / (Z'x)' (Z'Z)⁻¹ (Z'x)
        J = n · (a' (Z'Z)⁻¹ a) / (û'û),  a = Z'y − β·Z'x,  û'û = yy − 2β·xy + β²·xx

    from the recorded ``over_identification.sufficient_statistics`` (the
    residualised second moments Z'Z / Z'x / Z'y / xx / xy / yy). When the block
    also carries a Hansen J (``hansen_j`` + ``s_robust``), the efficient two-step
    GMM point and the robust J are re-derived from the recorded weight matrix Ŝ
    with their own independent transcription, and Ŝ is checked to be a valid
    (symmetric PSD) weight-variance matrix. When the numeric_estimate carries a
    multi-instrument ``anderson_rubin_confidence_set``, the q-dimensional
    projection quadratic forms are re-derived from the SAME recorded moments and
    the set is re-solved with the verifier's own quadratic classifier — its kind,
    endpoints, ``kappa = q·F(q, m)``, and 2SLS point are all confirmed (the point
    need NOT lie in the set, so membership is not enforced). When it also carries a
    ``robust_anderson_rubin_confidence_set`` (the heteroskedasticity-robust
    Stock-Wright S set), the robust statistic ``AR_r(β0) = n·ḡ'Ŝ(β0)⁻¹ḡ`` is
    re-transcribed from the recorded ``S0/S1/S2`` (``Ŝ(β0) = S0 − β0·S1 + β0²·S2``);
    each reported crossing is confirmed on the boundary, ``crit = χ²(q)`` and the
    tail asymptote are re-derived, the segments are rebuilt from the crossings, and
    an independent dense-grid membership scan (a different method from the
    producer's exact polynomial roots) confirms nothing was missed. It never
    imports the producer's solve and never touches the raw data. A result that
    isn't an ``iv_2sls_overid`` estimate is a no-op.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    import math

    import numpy as np
    from scipy.stats import chi2 as _chi2

    if not isinstance(estimate, dict) or estimate.get("method") != "iv_2sls_overid":
        return

    def _fail(msg):
        raise VerificationError(
            f"iv_overid_numeric: {msg}", step_index=None, rule="iv_overid_numeric",
        )

    oid = estimate.get("over_identification")
    if not isinstance(oid, dict):
        _fail("numeric_estimate carries no over_identification block")
    suff = oid.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("over_identification carries no sufficient_statistics")

    try:
        q = int(suff["q"]); n = int(suff["n"])
        zz = np.asarray(suff["zz"], dtype=float).reshape(q, q)
        zx = np.asarray(suff["zx"], dtype=float).reshape(q)
        zy = np.asarray(suff["zy"], dtype=float).reshape(q)
        xx = float(suff["xx"]); xy = float(suff["xy"]); yy = float(suff["yy"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    if q < 2:
        _fail(f"over-identified system needs q >= 2 instruments; got q={q}")

    try:
        zz_inv = np.linalg.inv(zz)
    except np.linalg.LinAlgError:
        _fail("recorded Z'Z is singular — cannot re-derive")

    x_pz_x = float(zx @ zz_inv @ zx)
    x_pz_y = float(zx @ zz_inv @ zy)
    if not math.isfinite(x_pz_x) or abs(x_pz_x) < 1e-12:
        _fail("degenerate first stage (x'P_Z x ~ 0)")
    beta = x_pz_y / x_pz_x

    a = zy - beta * zx
    u_pz_u = float(a @ zz_inv @ a)
    u_u = yy - 2.0 * beta * xy + beta * beta * xx
    if not math.isfinite(u_u) or u_u <= 0:
        _fail("non-positive structural residual sum of squares")
    j_stat = n * u_pz_u / u_u
    dof = q - 1
    p_value = float(_chi2.sf(j_stat, dof))

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        _fail(f"missing / non-numeric point {point!r}")
    if abs(beta - float(point)) > _IV_OVERID_TOL * (1 + abs(beta)):
        _fail(f"point mismatch — re-derived 2SLS {beta}, recorded {point}")

    for key, recomputed in (("sargan_j", j_stat), ("sargan_p_value", p_value)):
        claimed = oid.get(key)
        if claimed is None:
            _fail(f"over_identification.{key} missing")
        if abs(recomputed - float(claimed)) > _IV_OVERID_TOL * (1 + abs(recomputed)):
            _fail(f"{key} mismatch — re-derived {recomputed}, recorded {claimed}")

    if oid.get("sargan_dof") != dof:
        _fail(f"sargan_dof mismatch — re-derived {dof}, recorded {oid.get('sargan_dof')}")

    claimed_rej = oid.get("rejected_at_0_05")
    if claimed_rej is not None and bool(claimed_rej) != (p_value < 0.05):
        _fail(
            f"rejected_at_0_05={claimed_rej} inconsistent with re-derived "
            f"p-value {p_value}"
        )

    # --- Hansen (1982) robust J ------------------------------------------------
    # Present only when the producer's robust weight matrix Ŝ was non-singular.
    # A SECOND, independent transcription of the efficient two-step GMM closed
    # forms from the recorded Ŝ (s_robust) + cross-moments Z'x / Z'y:
    #
    #     β̂₂ = (Z'x)' Ŝ⁻¹ (Z'y) / (Z'x)' Ŝ⁻¹ (Z'x)
    #     J  = n · ḡ' Ŝ⁻¹ ḡ,   ḡ = (1/n)(Z'y − β̂₂·Z'x)
    #
    # As with the Sargan block, this audits that the reported J / GMM point are
    # the correct closed forms of the recorded sufficient statistics — not that
    # Ŝ matches raw data the verifier never sees (the declared honest ceiling of
    # the sufficient-statistics pattern). The extra teeth here: Ŝ must be a valid
    # (symmetric, PSD) weight-variance matrix, else the re-derived J is not a
    # legitimate χ² statistic.
    if oid.get("hansen_j") is not None:
        s_raw = suff.get("s_robust")
        if s_raw is None:
            _fail("hansen_j reported but sufficient_statistics.s_robust missing")
        try:
            S = np.asarray(s_raw, dtype=float).reshape(q, q)
        except (TypeError, ValueError) as exc:
            _fail(f"ill-formed robust weight matrix s_robust: {exc}")
        if not np.allclose(S, S.T, atol=1e-8):
            _fail("recorded robust weight matrix Ŝ is not symmetric")
        eig = np.linalg.eigvalsh((S + S.T) / 2.0)
        if float(eig.min()) < -1e-8 * (1.0 + abs(float(eig.max()))):
            _fail("recorded robust weight matrix Ŝ is not positive semidefinite")
        try:
            s_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            _fail("recorded robust weight matrix Ŝ is singular — cannot re-derive")
        denom = float(zx @ s_inv @ zx)
        if not math.isfinite(denom) or abs(denom) < 1e-12:
            _fail("degenerate efficient-GMM first stage (x'Ŝ⁻¹x ~ 0)")
        gmm_point = float(zx @ s_inv @ zy) / denom
        g = (zy - gmm_point * zx) / n
        hansen_j = float(n * (g @ s_inv @ g))
        hansen_dof = q - 1
        hansen_p = float(_chi2.sf(hansen_j, hansen_dof))

        for key, recomputed in (
            ("hansen_j", hansen_j),
            ("hansen_p_value", hansen_p),
            ("hansen_gmm_point", gmm_point),
        ):
            claimed = oid.get(key)
            if claimed is None:
                _fail(f"over_identification.{key} missing")
            if abs(recomputed - float(claimed)) > _IV_OVERID_TOL * (1 + abs(recomputed)):
                _fail(f"{key} mismatch — re-derived {recomputed}, recorded {claimed}")
        if oid.get("hansen_dof") != hansen_dof:
            _fail(
                f"hansen_dof mismatch — re-derived {hansen_dof}, recorded "
                f"{oid.get('hansen_dof')}"
            )
        claimed_hrej = oid.get("hansen_rejected_at_0_05")
        if claimed_hrej is not None and bool(claimed_hrej) != (hansen_p < 0.05):
            _fail(
                f"hansen_rejected_at_0_05={claimed_hrej} inconsistent with "
                f"re-derived p-value {hansen_p}"
            )

    # --- multi-instrument Anderson-Rubin weak-ID-robust set --------------------
    # Present when the numeric_estimate carries an anderson_rubin_confidence_set.
    # A SECOND, independent transcription: re-derive the q-dimensional projection
    # quadratic forms P_yy / P_xy / P_xx from the SAME recorded moments the Sargan
    # rode on, re-solve {β0 : A·β0² + B·β0 + C ≤ 0} with the verifier's OWN
    # quadratic classifier (rules._ar_solve_set_verifier, never the producer's),
    # and confirm the set's kind + endpoints, the F(q, m) critical value
    # kappa = q·F(q, m), and the 2SLS point. Unlike the just-identified AR set,
    # the point need NOT lie in this set (a violated over-identifying restriction
    # pushes N(point) = û'P_Z û > 0, so the point can fall outside) — membership
    # is therefore NOT enforced. Conditional on the block being present, so an
    # estimate without an AR set (degenerate design) still verifies.
    ar = estimate.get("anderson_rubin_confidence_set")
    if isinstance(ar, dict) and ar.get("kind") is not None:
        from scipy.stats import f as _f_dist
        from .rules import _ar_solve_set_verifier

        try:
            n_exog = int(suff["n_exog"])
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"AR set present but n_exog missing from sufficient statistics: {exc}")
        m_denom = n - n_exog - q - 1
        if m_denom < 1:
            _fail("AR set present but residual df m = n - |W| - q - 1 < 1")

        # Projection quadratic forms. x_pz_x = x'P_Z x and x_pz_y = x'P_Z y were
        # already re-derived above (and beta = x_pz_y / x_pz_x verified against the
        # headline point); only y'P_Z y is new.
        p_xx = x_pz_x
        p_xy = x_pz_y
        p_yy = float(zy @ zz_inv @ zy)

        try:
            ci_level = float(ar["ci_level"])
        except (KeyError, TypeError, ValueError):
            _fail("AR set missing / non-numeric ci_level")
        kappa = float(q) * float(_f_dist.ppf(ci_level, q, m_denom))
        claimed_kappa = ar.get("kappa")
        if claimed_kappa is not None and abs(float(claimed_kappa) - kappa) > _IV_OVERID_TOL * (1 + abs(kappa)):
            _fail(
                f"AR kappa mismatch — re-derived q·F(q,m) = {kappa}, recorded "
                f"{claimed_kappa}"
            )
        if ar.get("dof_num") is not None and int(ar["dof_num"]) != q:
            _fail(f"AR dof_num mismatch — q = {q}, recorded {ar.get('dof_num')}")
        if ar.get("dof_denom") is not None and int(ar["dof_denom"]) != m_denom:
            _fail(
                f"AR dof_denom mismatch — m = {m_denom}, recorded "
                f"{ar.get('dof_denom')}"
            )

        G = m_denom + kappa
        A = G * p_xx - kappa * xx
        B = 2.0 * (kappa * xy - G * p_xy)
        C = G * p_yy - kappa * yy
        a_scale = abs(G * p_xx) + abs(kappa * xx) + 1.0
        kind, lower, upper = _ar_solve_set_verifier(A, B, C, atol=1e-9 * a_scale)

        if kind != ar.get("kind"):
            _fail(
                f"AR set kind mismatch — re-solve {kind!r} vs recorded "
                f"{ar.get('kind')!r}"
            )
        for name, recomputed, claimed in (
            ("lower", lower, ar.get("lower")),
            ("upper", upper, ar.get("upper")),
        ):
            if recomputed is None and claimed is None:
                continue
            if (recomputed is None) != (claimed is None):
                _fail(
                    f"AR {name} presence mismatch — re-solve {recomputed} vs "
                    f"recorded {claimed}"
                )
            if abs(recomputed - float(claimed)) > _IV_OVERID_TOL * (1 + abs(recomputed)):
                _fail(
                    f"AR {name} mismatch — re-solve {recomputed} vs recorded "
                    f"{claimed}"
                )

        # The set is centred on the 2SLS point P_xy/P_xx = beta (already verified
        # against the headline point). Cross-check the AR block's own copy.
        claimed_pt = ar.get("point")
        if claimed_pt is not None and abs(beta - float(claimed_pt)) > _IV_OVERID_TOL * (1 + abs(beta)):
            _fail(
                f"AR point mismatch — 2SLS P_xy/P_xx = {beta}, recorded "
                f"{claimed_pt}"
            )

    # --- heteroskedasticity-robust (Stock-Wright S) AR set ---------------------
    # Present when the numeric_estimate carries a robust_anderson_rubin_confidence_set.
    # The verifier re-transcribes AR_r(β0) = n·ḡ(β0)'Ŝ(β0)⁻¹ḡ(β0) from the recorded
    # robust matrices Ŝ(β0) = S0 − β0·S1 + β0²·S2 (never the producer's evaluator),
    # then (a) confirms each reported crossing is on the boundary AR_r ≈ crit, (b)
    # re-derives crit = χ²(q) and the shared tail asymptote (1/n)·zx'S2⁻¹zx, (c)
    # rebuilds the segments from the crossings + asymptote and matches them + the
    # kind, and (d) runs an INDEPENDENT dense-grid membership scan (a different
    # method from the producer's exact polynomial roots) to confirm no crossing
    # was missed and the tails are right. Conditional on the block being present.
    rar = estimate.get("robust_anderson_rubin_confidence_set")
    if isinstance(rar, dict) and rar.get("kind") is not None:
        try:
            s0 = np.asarray(suff["s0"], dtype=float).reshape(q, q)
            s1 = np.asarray(suff["s1"], dtype=float).reshape(q, q)
            s2 = np.asarray(suff["s2"], dtype=float).reshape(q, q)
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"robust AR set present but sufficient_statistics.s0/s1/s2 missing: {exc}")

        def _arr(b0):
            g = (zy - b0 * zx) / n
            S = s0 - b0 * s1 + b0 * b0 * s2
            return float(n * (g @ np.linalg.solve(S, g)))

        try:
            ci_level_r = float(rar["ci_level"])
        except (KeyError, TypeError, ValueError):
            _fail("robust AR set missing / non-numeric ci_level")
        crit = float(_chi2.ppf(ci_level_r, q))
        claimed_crit = rar.get("crit")
        if claimed_crit is None or abs(crit - float(claimed_crit)) > _IV_OVERID_TOL * (1 + crit):
            _fail(f"robust AR crit mismatch — re-derived χ²({q}) {crit}, recorded {claimed_crit}")
        if rar.get("dof") is not None and int(rar["dof"]) != q:
            _fail(f"robust AR dof mismatch — q = {q}, recorded {rar.get('dof')}")

        try:
            asym = float((zx @ np.linalg.solve(s2, zx)) / n)
        except np.linalg.LinAlgError:
            asym = 0.0
        claimed_asym = rar.get("asymptote")
        if claimed_asym is None or abs(asym - float(claimed_asym)) > 1e-5 * (1 + abs(asym)):
            _fail(f"robust AR asymptote mismatch — re-derived {asym}, recorded {claimed_asym}")

        # Parse reported segments + crossings.
        seg_raw = rar.get("segments")
        if not isinstance(seg_raw, list):
            _fail("robust AR set carries no segments list")
        reported_segs = []
        for s in seg_raw:
            if not isinstance(s, dict):
                _fail("robust AR segment is not an object")
            reported_segs.append((s.get("lower"), s.get("upper")))
        reported_cross = sorted(float(c) for c in rar.get("crossings", []))

        # (a) each reported crossing is a genuine boundary point AR_r ≈ crit.
        for c in reported_cross:
            try:
                v = _arr(c)
            except np.linalg.LinAlgError:
                _fail(f"robust AR: Ŝ singular at reported crossing {c}")
            if abs(v - crit) > 1e-3 * (1 + crit):
                _fail(f"robust AR crossing {c} not on the boundary — AR_r={v}, crit={crit}")

        # (c) rebuild segments from crossings + asymptote; must match reported.
        tails_in = asym <= crit
        rebuilt, member, prev = [], tails_in, None
        for c in reported_cross:
            if member:
                rebuilt.append((prev, c))
            member = not member
            prev = c
        if member:
            rebuilt.append((prev, None))

        def _seg_eq(a, b):
            (alo, ahi), (blo, bhi) = a, b
            def _c(x, y):
                if x is None or y is None:
                    return x is None and y is None
                return abs(float(x) - float(y)) <= 1e-6 * (1 + abs(float(x)))
            return _c(alo, blo) and _c(ahi, bhi)

        if len(rebuilt) != len(reported_segs) or not all(
            _seg_eq(a, b) for a, b in zip(rebuilt, reported_segs)
        ):
            _fail(
                f"robust AR segments inconsistent with crossings+asymptote — "
                f"rebuilt {rebuilt}, recorded {reported_segs}"
            )

        # (d) INDEPENDENT dense-grid membership scan (a different method from the
        # producer's exact polynomial roots): {AR_r ≤ crit} on the grid must match
        # the reported cover everywhere, catching a missing/extra crossing or a
        # wrong tail. Far-tail probes pin the asymptote-driven tail membership.
        def _in_reported(b0):
            for lo, hi in reported_segs:
                if (lo is None or b0 >= float(lo) - 1e-9) and (hi is None or b0 <= float(hi) + 1e-9):
                    return True
            return False

        if reported_cross:
            span = max(reported_cross) - min(reported_cross)
            margin = max(1.0, 0.5 * span)
            grid = np.linspace(min(reported_cross) - margin,
                               max(reported_cross) + margin, 4001)
        else:
            centre = float(rar.get("point") or 0.0)
            grid = np.linspace(centre - 50.0, centre + 50.0, 4001)
        for b0 in grid:
            try:
                v = _arr(float(b0))
            except np.linalg.LinAlgError:
                continue
            if (v <= crit) != _in_reported(float(b0)):
                if abs(v - crit) > 1e-3 * (1 + crit):   # not a boundary sliver
                    _fail(
                        f"robust AR membership scan disagrees at β0={b0}: "
                        f"AR_r={v} vs reported-in={_in_reported(float(b0))}"
                    )
        # far tails
        centre = float(rar.get("point") or 0.0)
        for far in (centre - 1e6, centre + 1e6):
            try:
                v = _arr(far)
            except np.linalg.LinAlgError:
                continue
            if (v <= crit) != _in_reported(far) and abs(v - crit) > 1e-3 * (1 + crit):
                _fail(f"robust AR tail membership wrong at β0={far}: AR_r={v}")


_MEASUREMENT_CORRECTION_TOL = 1e-6


def verify_measurement_correction_numeric(estimate: dict) -> None:
    """Re-derive a confusion-matrix-corrected effect — the corrected point, the
    naive (attenuated) point, and det(M) — from the recorded confusion matrix +
    per-stratum outcome value-count vectors, and reject on mismatch.

    The correction rides on a ``numerically_solved`` back-door result whose
    derivation ends in ``numeric_measurement_correction_estimate`` (metadata +
    structural licensing only — the confusion matrix and per-stratum count
    vectors don't fit the derivation-input serialization). This is the strong
    numeric counterpart: a SECOND, independent transcription of the inversion

        p_true(· | x, z) = M⁻¹ p_obs(· | x, z)
        effect = Σ_z [ p_true(y* | 1, z) − p_true(y* | 0, z) ] · P(z)

    from the recorded ``measurement_correction.sufficient_statistics`` (the
    matrix, per-(arm, stratum) value counts, and covariate marginal counts). It
    never imports the producer's estimator and never touches the raw data. A
    result that isn't a ``measurement_error_correction`` estimate is a no-op.

    Tamper checks: forged corrected/naive point, a confusion matrix whose det
    disagrees with the recorded det, a non-column-stochastic matrix, a stratum
    whose counts don't sum to n, a marginal that doesn't sum to the total (a
    dropped stratum), or a covariate stratum missing an arm — each is rejected.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    import numpy as np

    if (
        not isinstance(estimate, dict)
        or estimate.get("method") != "measurement_error_correction"
    ):
        return

    def _fail(msg):
        raise VerificationError(
            f"measurement_correction_numeric: {msg}",
            step_index=None, rule="measurement_correction_numeric",
        )

    mc = estimate.get("measurement_correction")
    if not isinstance(mc, dict):
        _fail("numeric_estimate carries no measurement_correction block")
    suff = mc.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("measurement_correction carries no sufficient_statistics")

    try:
        states = list(suff["states"])
        target_value = suff["target_value"]
        strata = list(suff["strata"])
        marginal_counts = list(suff["marginal_counts"])
        marginal_total = int(suff["marginal_total"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    k = len(states)
    if len(set(map(_state_key, states))) != k:
        _fail("outcome states are not distinct")

    differential = bool(suff.get("differential"))
    if bool(mc.get("differential")) != differential:
        _fail(
            f"measurement_correction.differential {mc.get('differential')} "
            f"disagrees with sufficient_statistics.differential {differential}"
        )

    # Build the inverse-matrix selector. Non-differential: one matrix for both
    # arms (an independent second inversion of the recorded matrix). Differential
    # by the exposure arm (detection bias): a distinct matrix per arm. Differential
    # by a COVARIATE: a distinct matrix per covariate stratum, selected by that
    # covariate's value within each (arm, z) cell — each matrix re-inverted here.
    differential_by = suff.get("differential_by")
    covariate_differential = differential and differential_by is not None
    Minv_by_arm: dict | None = None
    Minv_by_level: dict | None = None
    cov_idx = None
    if covariate_differential:
        if mc.get("differential_by") not in (None, differential_by):
            _fail(
                f"measurement_correction.differential_by {mc.get('differential_by')!r} "
                f"disagrees with sufficient_statistics.differential_by {differential_by!r}"
            )
        adjustment_vars = list(suff.get("adjustment_vars") or [])
        if differential_by not in adjustment_vars:
            _fail(
                f"differential_by {differential_by!r} is not among the recorded "
                f"adjustment_vars {adjustment_vars}"
            )
        cov_idx = adjustment_vars.index(differential_by)
        recs = suff.get("confusion_matrices_by_level")
        if not isinstance(recs, list) or not recs:
            _fail("covariate-differential estimate carries no confusion_matrices_by_level")
        Minv_by_level = {}
        for r in recs:
            try:
                lvl = r["level"]
                mat = r["matrix"]
                rec_det = r.get("det")
            except (KeyError, TypeError, ValueError) as exc:
                _fail(f"ill-formed per-level confusion-matrix record: {exc}")
            Minv_lvl, _d = _reinvert_stochastic(
                mat, k, rec_det, _fail, label=f"{differential_by}={lvl!r}",
            )
            key = _level_key_v(lvl)
            if key in Minv_by_level:
                _fail(f"duplicate differential level {lvl!r} for {differential_by}")
            Minv_by_level[key] = Minv_lvl
    elif differential:
        recs = suff.get("confusion_matrices_by_arm")
        if not isinstance(recs, list) or not recs:
            _fail("differential estimate carries no confusion_matrices_by_arm")
        Minv_by_arm = {}
        for r in recs:
            try:
                arm = int(r["arm"])
                mat = r["matrix"]
                rec_det = r.get("det")
            except (KeyError, TypeError, ValueError) as exc:
                _fail(f"ill-formed per-arm confusion-matrix record: {exc}")
            Minv_arm, _d = _reinvert_stochastic(
                mat, k, rec_det, _fail, label=f"arm {arm}",
            )
            Minv_by_arm[arm] = Minv_arm
        if set(Minv_by_arm) != {0, 1}:
            _fail(
                "differential outcome correction must carry a matrix for each of "
                f"arm 0 and arm 1; got arms {sorted(Minv_by_arm)}"
            )
    else:
        try:
            M = np.asarray(suff["confusion_matrix"], dtype=float)
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"ill-formed sufficient statistics: {exc}")
        if M.shape != (k, k):
            _fail(f"confusion matrix {M.shape} does not match {k} states")
        col_sums = M.sum(axis=0)
        if not np.allclose(col_sums, 1.0, atol=1e-6):
            _fail(
                "confusion matrix is not column-stochastic "
                f"(column sums {[round(float(c), 6) for c in col_sums]})"
            )
        det = float(np.linalg.det(M))
        claimed_det = mc.get("det")
        if claimed_det is not None and abs(det - float(claimed_det)) > 1e-9:
            _fail(f"det mismatch — re-derived {det}, recorded {claimed_det}")
        if abs(suff.get("det", det) - det) > 1e-9:
            _fail(
                f"sufficient_statistics.det {suff.get('det')} inconsistent with the "
                f"recorded confusion matrix (det {det})"
            )
        if abs(det) < 1e-12:
            _fail("recorded confusion matrix is singular — cannot re-invert")
        Minv = np.linalg.inv(M)
        Minv_by_arm = {0: Minv, 1: Minv}

    # Independent target index — do not trust the recorded one.
    try:
        target_index = [_state_key(s) for s in states].index(_state_key(target_value))
    except ValueError:
        _fail(f"target value {target_value!r} not among states {states!r}")

    # Marginal P(z) from the recorded covariate counts; a marginal that doesn't
    # sum to the total means a stratum was dropped from the standardisation.
    marg: dict = {}
    total = 0
    for rec in marginal_counts:
        zk = _z_key(rec["z"])
        marg[zk] = int(rec["count"])
        total += int(rec["count"])
    if total != marginal_total:
        _fail(
            f"marginal counts sum to {total}, not the recorded total "
            f"{marginal_total} (a covariate stratum was dropped)"
        )

    # Per-(arm, z) recovered target risk from the recorded value-count vectors.
    by_z: dict = {}
    for rec in strata:
        zk = _z_key(rec["z"])
        counts = np.asarray(rec["counts"], dtype=float)
        n = int(rec["n"])
        if counts.shape != (k,):
            _fail(f"stratum count vector length {counts.shape} != {k} states")
        if int(counts.sum()) != n:
            _fail(
                f"stratum arm={rec['arm']} z={rec['z']} counts sum to "
                f"{int(counts.sum())}, not n={n}"
            )
        if n <= 0:
            _fail(f"stratum arm={rec['arm']} z={rec['z']} has n={n}")
        arm = int(rec["arm"])
        if covariate_differential:
            lvl_val = rec["z"][cov_idx]
            Minv_sel = Minv_by_level.get(_level_key_v(lvl_val))
            if Minv_sel is None:
                _fail(
                    f"stratum z={rec['z']} has no confusion matrix for "
                    f"{differential_by}={lvl_val!r} in the recorded set"
                )
        else:
            if arm not in Minv_by_arm:
                _fail(f"stratum arm={arm} has no confusion matrix in the recorded set")
            Minv_sel = Minv_by_arm[arm]
        p_obs = counts / n
        p_true = Minv_sel @ p_obs
        by_z.setdefault(zk, {})[arm] = (
            float(p_true[target_index]), float(p_obs[target_index]),
        )

    corrected = 0.0
    naive = 0.0
    for zk, p_z_count in marg.items():
        p_z = p_z_count / marginal_total
        arms = by_z.get(zk)
        if arms is None or 1 not in arms or 0 not in arms:
            _fail(f"covariate stratum {list(zk)} missing an arm in the strata records")
        corrected += (arms[1][0] - arms[0][0]) * p_z
        naive += (arms[1][1] - arms[0][1]) * p_z

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        _fail(f"missing / non-numeric point {point!r}")
    if abs(corrected - float(point)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(corrected)):
        _fail(f"point mismatch — re-derived corrected {corrected}, recorded {point}")

    claimed_naive = mc.get("naive_point")
    if claimed_naive is None:
        _fail("measurement_correction.naive_point missing")
    if abs(naive - float(claimed_naive)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(naive)):
        _fail(f"naive_point mismatch — re-derived {naive}, recorded {claimed_naive}")


def verify_exposure_measurement_correction_numeric(estimate: dict) -> None:
    """Re-derive an EXPOSURE confusion-matrix-corrected effect — the corrected
    point, the naive (attenuated) point, and det(M) — from the recorded matrix +
    per-stratum full 2×k (X, Y) joint count tables, and reject on mismatch.

    The exposure correction rides on a ``numerically_solved`` back-door result
    whose derivation ends in ``numeric_measurement_correction_estimate``
    (metadata + structural licensing only). This is the strong numeric
    counterpart: a SECOND, independent transcription of the matrix method

        p_true(X*, Y | z) = M⁻¹ p_obs(X, Y | z)          (per outcome column)
        P(Y=y* | X*=x, z) = p_true(x, y* | z) / Σ_y p_true(x, y | z)
        effect = Σ_z [ P(Y=y* | X*=1, z) − P(Y=y* | X*=0, z) ] · P(z)

    from the recorded ``measurement_correction.sufficient_statistics`` (the
    matrix, per-stratum 2×k joint tables, outcome states, and covariate marginal
    counts). It never imports the producer's estimator and never touches the raw
    data. A result that isn't an ``exposure_measurement_error_correction``
    estimate is a no-op.

    Under **differential** misclassification the single matrix is replaced by a
    per-level set. By the OUTCOME (recall bias) a distinct M_y inverts each outcome
    column; by a COVARIATE (``differential_by`` names it) a single M_z, selected by
    that covariate's value in each stratum's z, inverts every column — each matrix
    re-inverted here independently.

    Tamper checks: forged corrected/naive point, a confusion matrix whose det
    disagrees with the recorded det, a non-column-stochastic matrix, a joint
    table whose cells don't sum consistently, a marginal that doesn't sum to the
    total (a dropped stratum), a covariate stratum missing from the tables, an
    empty observed arm (positivity), a degenerate recovered exposure marginal, a
    tampered per-level matrix, a ``differential_by`` that disagrees between block
    and sufficient statistics, or a stratum whose covariate value has no matrix —
    each is rejected.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    import numpy as np

    if (
        not isinstance(estimate, dict)
        or estimate.get("method") != "exposure_measurement_error_correction"
    ):
        return

    def _fail(msg):
        raise VerificationError(
            f"exposure_measurement_correction_numeric: {msg}",
            step_index=None, rule="exposure_measurement_correction_numeric",
        )

    mc = estimate.get("measurement_correction")
    if not isinstance(mc, dict):
        _fail("numeric_estimate carries no measurement_correction block")
    if mc.get("side") != "exposure":
        _fail("measurement_correction.side is not 'exposure'")
    suff = mc.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("measurement_correction carries no sufficient_statistics")

    try:
        states = list(suff["states"])
        outcome_states = list(suff["outcome_states"])
        target_value = suff["target_value"]
        strata = list(suff["strata"])
        marginal_counts = list(suff["marginal_counts"])
        marginal_total = int(suff["marginal_total"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    if len(states) != 2 or len(set(map(_state_key, states))) != 2:
        _fail(f"exposure states must be a distinct binary pair; got {states!r}")
    k = len(outcome_states)
    if k < 1:
        _fail("no outcome states recorded")
    if len(set(map(_state_key, outcome_states))) != k:
        _fail("outcome states are not distinct")

    differential = bool(suff.get("differential"))
    if bool(mc.get("differential")) != differential:
        _fail(
            f"measurement_correction.differential {mc.get('differential')} "
            f"disagrees with sufficient_statistics.differential {differential}"
        )

    # Per-column inverse map. Non-differential: one 2×2 matrix for every column
    # (an independent second inversion). Differential by the OUTCOME (recall bias):
    # a distinct M_y per outcome level, covering every recorded outcome level
    # exactly, each outcome column inverted with its own matrix. Differential by a
    # COVARIATE: a distinct M_z per covariate level, selected per stratum by that
    # covariate's value and applied to every column — each matrix re-inverted here.
    differential_by = suff.get("differential_by")
    covariate_differential = differential and differential_by is not None
    Minv_by_outcome: dict | None = None
    Minv_by_level: dict | None = None
    cov_idx = None
    if covariate_differential:
        if mc.get("differential_by") not in (None, differential_by):
            _fail(
                f"measurement_correction.differential_by {mc.get('differential_by')!r} "
                f"disagrees with sufficient_statistics.differential_by {differential_by!r}"
            )
        adjustment_vars = list(suff.get("adjustment_vars") or [])
        if differential_by not in adjustment_vars:
            _fail(
                f"differential_by {differential_by!r} is not among the recorded "
                f"adjustment_vars {adjustment_vars}"
            )
        cov_idx = adjustment_vars.index(differential_by)
        recs = suff.get("confusion_matrices_by_level")
        if not isinstance(recs, list) or not recs:
            _fail("covariate-differential exposure estimate carries no confusion_matrices_by_level")
        Minv_by_level = {}
        for r in recs:
            try:
                lvl = r["level"]
                mat = r["matrix"]
                rec_det = r.get("det")
            except (KeyError, TypeError, ValueError) as exc:
                _fail(f"ill-formed per-level confusion-matrix record: {exc}")
            Minv_lvl, _d = _reinvert_stochastic(
                mat, 2, rec_det, _fail, label=f"{differential_by}={lvl!r}",
            )
            key = _level_key_v(lvl)
            if key in Minv_by_level:
                _fail(f"duplicate differential level {lvl!r} for {differential_by}")
            Minv_by_level[key] = Minv_lvl
    elif differential:
        recs = suff.get("confusion_matrices_by_outcome")
        if not isinstance(recs, list) or not recs:
            _fail("differential estimate carries no confusion_matrices_by_outcome")
        Minv_by_outcome = {}
        for r in recs:
            try:
                lvl = r["outcome"]
                mat = r["matrix"]
                rec_det = r.get("det")
            except (KeyError, TypeError, ValueError) as exc:
                _fail(f"ill-formed per-outcome confusion-matrix record: {exc}")
            Minv_y, _d = _reinvert_stochastic(
                mat, 2, rec_det, _fail, label=f"outcome {lvl!r}",
            )
            Minv_by_outcome[_level_key_v(lvl)] = Minv_y
        needed = {_level_key_v(y) for y in outcome_states}
        if set(Minv_by_outcome) != needed:
            _fail(
                "differential exposure correction must carry a matrix for every "
                f"outcome level {outcome_states!r}; got matrices for "
                f"{sorted(str(kk) for kk in Minv_by_outcome)}"
            )
    else:
        try:
            M = np.asarray(suff["confusion_matrix"], dtype=float)
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"ill-formed sufficient statistics: {exc}")
        if M.shape != (2, 2):
            _fail(f"exposure confusion matrix {M.shape} is not 2×2")
        col_sums = M.sum(axis=0)
        if not np.allclose(col_sums, 1.0, atol=1e-6):
            _fail(
                "confusion matrix is not column-stochastic "
                f"(column sums {[round(float(c), 6) for c in col_sums]})"
            )
        det = float(np.linalg.det(M))
        claimed_det = mc.get("det")
        if claimed_det is not None and abs(det - float(claimed_det)) > 1e-9:
            _fail(f"det mismatch — re-derived {det}, recorded {claimed_det}")
        if abs(suff.get("det", det) - det) > 1e-9:
            _fail(
                f"sufficient_statistics.det {suff.get('det')} inconsistent with the "
                f"recorded confusion matrix (det {det})"
            )
        if abs(det) < 1e-12:
            _fail("recorded confusion matrix is singular — cannot re-invert")
        Minv = np.linalg.inv(M)
        Minv_by_outcome = {_level_key_v(y): Minv for y in outcome_states}

    # Independent target index — do not trust the recorded one.
    try:
        target_index = [_state_key(s) for s in outcome_states].index(
            _state_key(target_value)
        )
    except ValueError:
        _fail(f"target value {target_value!r} not among states {outcome_states!r}")

    # Marginal P(z); a marginal that doesn't sum to the total means a stratum
    # was dropped from the standardisation.
    marg: dict = {}
    total = 0
    for rec in marginal_counts:
        zk = _z_key(rec["z"])
        marg[zk] = int(rec["count"])
        total += int(rec["count"])
    if total != marginal_total:
        _fail(
            f"marginal counts sum to {total}, not the recorded total "
            f"{marginal_total} (a covariate stratum was dropped)"
        )

    # Per-z recovered target risks (corrected + naive) from the 2×k joint tables.
    by_z: dict = {}
    for rec in strata:
        zk = _z_key(rec["z"])
        joint = np.asarray(rec["joint_counts"], dtype=float)
        if joint.shape != (2, k):
            _fail(f"joint table shape {joint.shape} != (2, {k}) for z={rec['z']}")
        if (joint < -1e-9).any():
            _fail(f"joint table for z={rec['z']} has a negative count")
        arm_n = joint.sum(axis=1)                 # observed size of each exposure arm
        if arm_n[0] <= 0 or arm_n[1] <= 0:
            _fail(
                f"covariate stratum {rec['z']} has an empty observed exposure arm "
                f"(arm sizes {[int(a) for a in arm_n]}); positivity is violated"
            )
        Nz = joint.sum()
        p_obs = joint / Nz
        p_true = np.empty_like(p_obs)
        if covariate_differential:
            lvl_val = rec["z"][cov_idx]
            Minv_sel = Minv_by_level.get(_level_key_v(lvl_val))
            if Minv_sel is None:
                _fail(
                    f"stratum z={rec['z']} has no confusion matrix for "
                    f"{differential_by}={lvl_val!r} in the recorded set"
                )
            p_true = Minv_sel @ p_obs        # one M_z for every outcome column
        else:
            for j in range(k):
                p_true[:, j] = Minv_by_outcome[_level_key_v(outcome_states[j])] @ p_obs[:, j]
        px1 = float(p_true[1, :].sum())
        px0 = float(p_true[0, :].sum())
        if px1 <= 1e-12 or px0 <= 1e-12:
            _fail(
                f"stratum {rec['z']} recovers a non-positive true exposure "
                f"marginal (P(X*=1|z)={px1:.3g}, P(X*=0|z)={px0:.3g})"
            )
        corrected_rd = (
            float(p_true[1, target_index]) / px1
            - float(p_true[0, target_index]) / px0
        )
        naive_rd = (
            float(joint[1, target_index]) / float(arm_n[1])
            - float(joint[0, target_index]) / float(arm_n[0])
        )
        by_z[zk] = (corrected_rd, naive_rd)

    corrected = 0.0
    naive = 0.0
    for zk, p_z_count in marg.items():
        p_z = p_z_count / marginal_total
        rd = by_z.get(zk)
        if rd is None:
            _fail(f"covariate stratum {list(zk)} missing from the joint tables")
        corrected += rd[0] * p_z
        naive += rd[1] * p_z

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        _fail(f"missing / non-numeric point {point!r}")
    if abs(corrected - float(point)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(corrected)):
        _fail(f"point mismatch — re-derived corrected {corrected}, recorded {point}")

    claimed_naive = mc.get("naive_point")
    if claimed_naive is None:
        _fail("measurement_correction.naive_point missing")
    if abs(naive - float(claimed_naive)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(naive)):
        _fail(f"naive_point mismatch — re-derived {naive}, recorded {claimed_naive}")


def verify_combined_measurement_correction_numeric(estimate: dict) -> None:
    """Re-derive a COMBINED (exposure AND outcome) confusion-matrix-corrected
    effect — the corrected point, the naive point, each channel's det and the
    composed map's det — from the recorded matrices + per-stratum 2×k observed
    joint tables, and reject on mismatch.

    The correction rides on a ``numerically_solved`` back-door result whose
    derivation ends in ``numeric_measurement_correction_estimate`` (metadata +
    structural licensing only). This is the strong numeric counterpart: a
    SECOND, independent transcription of the two-sided matrix method

        P_true(z)         = M_x⁻¹ · P_obs(z) · (M_y⁻¹)ᵀ
        P(Y*=y* | X*=x,z) = P_true(z)[x, y*] / Σ_b P_true(z)[x, b]
        effect            = Σ_z [ P(Y*=y*|X*=1,z) − P(Y*=y*|X*=0,z) ] · P(z)

    from the recorded ``measurement_correction.sufficient_statistics``. It never
    imports the producer's estimator and never touches the raw data. A result
    that isn't a ``combined_measurement_error_correction`` estimate is a no-op.

    The check that only exists here: the recorded ``det_joint`` must equal
    ``det(M_x)^k · det(M_y)^2``, the determinant of the composed 2k×2k map. A
    point re-derived from two matrices while the joint determinant was carried
    over from a different pair would otherwise pass unnoticed.

    Tamper checks: forged corrected / naive point, either matrix's det
    disagreeing with the matrix, a non-column-stochastic or singular matrix on
    either channel, a joint table of the wrong shape or with a negative count, a
    marginal that doesn't sum to the total (a dropped stratum), a covariate
    stratum missing from the tables, an empty observed arm (positivity), a
    degenerate recovered exposure marginal, a ``side`` that is not 'combined',
    or a claim of differential misclassification (which the two-sided
    factorisation does not license) — each is rejected.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    import numpy as np

    if (
        not isinstance(estimate, dict)
        or estimate.get("method") != "combined_measurement_error_correction"
    ):
        return

    def _fail(msg):
        raise VerificationError(
            f"combined_measurement_correction_numeric: {msg}",
            step_index=None, rule="combined_measurement_correction_numeric",
        )

    mc = estimate.get("measurement_correction")
    if not isinstance(mc, dict):
        _fail("numeric_estimate carries no measurement_correction block")
    if mc.get("side") != "combined":
        _fail("measurement_correction.side is not 'combined'")
    if mc.get("differential") or (isinstance(mc, dict) and mc.get("differential_by")):
        _fail(
            "a combined correction cannot be differential — the two-sided "
            "factorisation M_x · P_true · M_yᵀ holds only for constant matrices"
        )
    suff = mc.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("measurement_correction carries no sufficient_statistics")
    if suff.get("differential"):
        _fail("sufficient_statistics claims differential misclassification")

    try:
        states = list(suff["states"])
        outcome_states = list(suff["outcome_states"])
        target_value = suff["target_value"]
        strata = list(suff["strata"])
        marginal_counts = list(suff["marginal_counts"])
        marginal_total = int(suff["marginal_total"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    if len(states) != 2 or len(set(map(_state_key, states))) != 2:
        _fail(f"exposure states must be a distinct binary pair; got {states!r}")
    k = len(outcome_states)
    if k < 2:
        _fail(f"need at least 2 outcome states; got {outcome_states!r}")
    if len(set(map(_state_key, outcome_states))) != k:
        _fail("outcome states are not distinct")

    # Both channels re-validated and re-inverted independently of the producer.
    Mx_inv, det_x = _reinvert_stochastic(
        suff.get("exposure_confusion_matrix"), 2,
        suff.get("det_exposure"), _fail, label="exposure",
    )
    My_inv, det_y = _reinvert_stochastic(
        suff.get("outcome_confusion_matrix"), k,
        suff.get("det_outcome"), _fail, label="outcome",
    )
    for source, name in ((mc, "measurement_correction"), (suff, "sufficient_statistics")):
        for claimed, derived, chan in (
            (source.get("det_exposure"), det_x, "exposure"),
            (source.get("det_outcome"), det_y, "outcome"),
        ):
            if claimed is not None and abs(float(claimed) - derived) > 1e-9:
                _fail(
                    f"{name}.det_{chan} {claimed} disagrees with the recorded "
                    f"{chan} confusion matrix (det {derived})"
                )
    # The composed map is the Kronecker product of the two channels, so its
    # determinant factorises; a det_joint carried over from a different pair of
    # matrices is caught here and nowhere else.
    det_joint = det_x ** k * det_y ** 2
    for source, name in ((mc, "measurement_correction"), (suff, "sufficient_statistics")):
        claimed_joint = source.get("det_joint")
        if claimed_joint is not None and abs(
            float(claimed_joint) - det_joint
        ) > 1e-9 * (1 + abs(det_joint)):
            _fail(
                f"{name}.det_joint {claimed_joint} disagrees with "
                f"det(M_x)^{k} · det(M_y)^2 = {det_joint}"
            )

    # Independent target index — do not trust the recorded one.
    try:
        target_index = [_state_key(s) for s in outcome_states].index(
            _state_key(target_value)
        )
    except ValueError:
        _fail(f"target value {target_value!r} not among states {outcome_states!r}")

    # Marginal P(z); a marginal that doesn't sum to the total means a stratum
    # was dropped from the standardisation.
    marg: dict = {}
    total = 0
    for rec in marginal_counts:
        marg[_z_key(rec["z"])] = int(rec["count"])
        total += int(rec["count"])
    if total != marginal_total:
        _fail(
            f"marginal counts sum to {total}, not the recorded total "
            f"{marginal_total} (a covariate stratum was dropped)"
        )

    by_z: dict = {}
    for rec in strata:
        joint = np.asarray(rec["joint_counts"], dtype=float)
        if joint.shape != (2, k):
            _fail(f"joint table shape {joint.shape} != (2, {k}) for z={rec['z']}")
        if (joint < -1e-9).any():
            _fail(f"joint table for z={rec['z']} has a negative count")
        arm_n = joint.sum(axis=1)              # observed size of each exposure arm
        if arm_n[0] <= 0 or arm_n[1] <= 0:
            _fail(
                f"covariate stratum {rec['z']} has an empty observed exposure arm "
                f"(arm sizes {[int(a) for a in arm_n]}); positivity is violated"
            )
        p_obs = joint / joint.sum()
        p_true = Mx_inv @ p_obs @ My_inv.T
        px1 = float(p_true[1, :].sum())
        px0 = float(p_true[0, :].sum())
        if px1 <= 1e-12 or px0 <= 1e-12:
            _fail(
                f"stratum {rec['z']} recovers a non-positive true exposure "
                f"marginal (P(X*=1|z)={px1:.3g}, P(X*=0|z)={px0:.3g})"
            )
        by_z[_z_key(rec["z"])] = (
            float(p_true[1, target_index]) / px1
            - float(p_true[0, target_index]) / px0,
            float(joint[1, target_index]) / float(arm_n[1])
            - float(joint[0, target_index]) / float(arm_n[0]),
        )

    corrected = 0.0
    naive = 0.0
    for zk, p_z_count in marg.items():
        rd = by_z.get(zk)
        if rd is None:
            _fail(f"covariate stratum {list(zk)} missing from the joint tables")
        p_z = p_z_count / marginal_total
        corrected += rd[0] * p_z
        naive += rd[1] * p_z

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        _fail(f"missing / non-numeric point {point!r}")
    if abs(corrected - float(point)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(corrected)):
        _fail(f"point mismatch — re-derived corrected {corrected}, recorded {point}")

    claimed_naive = mc.get("naive_point")
    if claimed_naive is None:
        _fail("measurement_correction.naive_point missing")
    if abs(naive - float(claimed_naive)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(naive)):
        _fail(f"naive_point mismatch — re-derived {naive}, recorded {claimed_naive}")


def verify_regression_calibration_numeric(estimate: dict) -> None:
    """Re-derive a regression-calibration-corrected slope — the corrected point,
    the naive (biased) slope, and the reliabilities λ_v — from the recorded
    design covariance matrix Σ_obs + Cov(D,Y) + the per-variable error variances,
    and reject on mismatch.

    The correction rides on a ``numerically_solved`` back-door result whose
    derivation ends in ``numeric_measurement_correction_estimate`` (a shared
    terminal — metadata + structural licensing only; the covariance matrix
    doesn't fit derivation-input serialization). This is the strong numeric
    counterpart: a SECOND, independent transcription of the moment correction

        b_naive = Σ_obs⁻¹ Cov(D, Y)                             (biased)
        β_true  = (Σ_obs − E)⁻¹ Cov(D, Y),  E = diag(σ²_u at the mismeasured columns)
        λ_v     = 1 − σ²_uv / Var(V|rest)                       (continuous det(M))

    from the recorded ``regression_calibration.sufficient_statistics`` (the
    design covariance, the Cov(D,Y) vector, and the per-variable error variances
    ``error_variances``). It never imports the producer's estimator and never
    touches the raw data. The mismeasured column may be the exposure and/or a
    back-door covariate, so E is rebuilt at each mismeasured column's index. A
    result that isn't a ``regression_calibration`` estimate is a no-op.

    Tamper checks: a forged corrected / naive point, a forged reliability, a
    non-symmetric or wrong-shape covariance, an error variance keyed by a
    non-design variable, a scalar ``error_variance`` inconsistent with the
    exposure's diagonal, a σ²_u that makes Σ_obs − E non-positive-definite (a
    degenerate reliability the estimator would have refused) yet a point still
    shipped, or a recorded naive / corrected slope vector that disagrees with the
    covariance re-derivation (which catches a tampered covariance entry that
    wasn't propagated to the slopes) — each is rejected.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    import numpy as np

    if (
        not isinstance(estimate, dict)
        or estimate.get("method") != "regression_calibration"
    ):
        return

    def _fail(msg):
        raise VerificationError(
            f"regression_calibration_numeric: {msg}",
            step_index=None, rule="regression_calibration_numeric",
        )

    rc = estimate.get("regression_calibration")
    if not isinstance(rc, dict):
        _fail("numeric_estimate carries no regression_calibration block")
    suff = rc.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("regression_calibration carries no sufficient_statistics")

    try:
        design_vars = list(suff["design_vars"])
        Sigma = np.asarray(suff["cov_matrix"], dtype=float)
        cov_Dy = np.asarray(suff["cov_design_y"], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    p = len(design_vars)
    if p < 1:
        _fail("design must carry at least the exposure column")
    if Sigma.shape != (p, p):
        _fail(f"cov_matrix {Sigma.shape} does not match {p} design vars")
    if cov_Dy.shape != (p,):
        _fail(f"cov_design_y {cov_Dy.shape} does not match {p} design vars")
    if not np.allclose(Sigma, Sigma.T, atol=1e-8):
        _fail("cov_matrix is not symmetric")

    # Reconstruct the error diagonal E from the recorded per-variable error
    # variances (name → σ²_uv) at each mismeasured column's design index — the
    # general form E = diag(σ²_u at mismeasured columns, 0 elsewhere). A
    # scalar-only record (legacy exposure-side) falls back to E[0,0]=σ²_u.
    e_vec = np.zeros(p)
    ev_map = suff.get("error_variances")
    if isinstance(ev_map, dict) and ev_map:
        for name, val in ev_map.items():
            if name not in design_vars:
                _fail(f"error variance for {name!r} not among design vars {design_vars}")
            v = float(val)
            if not (np.isfinite(v) and v > 0):
                _fail(f"error variance for {name!r} must be positive finite; got {val!r}")
            e_vec[design_vars.index(name)] = v
    else:
        try:
            e_vec[0] = float(suff["error_variance"])
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"no usable error variance in sufficient statistics: {exc}")
    if e_vec.sum() <= 0:
        _fail("no positive measurement-error variance recorded")

    # The scalar error_variance must equal the exposure's diagonal entry.
    exposure_su2 = float(e_vec[0])
    rec_scalar = suff.get("error_variance")
    if rec_scalar is not None and abs(
        float(rec_scalar) - exposure_su2
    ) > 1e-9 * (1 + abs(exposure_su2)):
        _fail(
            f"error_variance {rec_scalar} disagrees with the exposure diagonal "
            f"{exposure_su2}"
        )

    # Naive OLS slope from the recorded covariance — an independent second solve.
    try:
        b = np.linalg.solve(Sigma, cov_Dy)
    except np.linalg.LinAlgError:
        _fail("recorded cov_matrix is singular — cannot re-derive the naive slope")

    # Per-mismeasured-column reliability λ_v = 1 − σ²_uv / Var(V|rest); ≤ 0 is a
    # degenerate reliability the estimator would have refused. Var(V|rest) is the
    # Schur complement of the other design columns.
    def _cond_var(idx):
        if p == 1:
            return float(Sigma[0, 0])
        others = [j for j in range(p) if j != idx]
        s_io = Sigma[idx, others]
        s_oo = Sigma[np.ix_(others, others)]
        try:
            return float(Sigma[idx, idx] - s_io @ np.linalg.solve(s_oo, s_io))
        except np.linalg.LinAlgError:
            _fail(f"design block for column {idx} is singular — cannot re-derive Var(V|rest)")

    reliabilities: dict = {}
    for i in range(p):
        if e_vec[i] > 0:
            var_i = _cond_var(i)
            lam_i = 1.0 - e_vec[i] / var_i
            reliabilities[design_vars[i]] = lam_i
            if lam_i <= 1e-12:
                _fail(
                    f"reliability λ = {lam_i} ≤ 0 for {design_vars[i]!r} (σ²_u "
                    f"{e_vec[i]} ≥ Var(V|rest) {var_i}): the corrected design "
                    f"Σ_obs − E is not positive definite, so no corrected slope "
                    f"should have been produced"
                )

    E = np.diag(e_vec)
    Sigma_star = Sigma - E
    # Positive-definiteness is the general degeneracy condition (per-column λ > 0
    # is necessary but not sufficient once several columns are mismeasured).
    try:
        np.linalg.cholesky(Sigma_star)
    except np.linalg.LinAlgError:
        _fail(
            "corrected design Σ_obs − E is not positive definite — no corrected "
            "slope should have been produced"
        )
    try:
        beta = np.linalg.solve(Sigma_star, cov_Dy)
    except np.linalg.LinAlgError:
        _fail("corrected design Σ_obs − E is singular — cannot re-derive the point")

    # Exposure reliability λ_x (1.0 when the exposure is measured accurately).
    lam = reliabilities.get(design_vars[0], 1.0)

    # Recorded reliability / slope vectors must agree with the covariance
    # re-derivation — a tampered covariance not propagated here is caught.
    rec_lam = rc.get("reliability")
    if rec_lam is not None and abs(lam - float(rec_lam)) > 1e-9 * (1 + abs(lam)):
        _fail(f"reliability mismatch — re-derived {lam}, recorded {rec_lam}")
    rec_rels = suff.get("reliabilities")
    if isinstance(rec_rels, dict):
        for name, lam_v in reliabilities.items():
            if name in rec_rels and abs(
                lam_v - float(rec_rels[name])
            ) > 1e-9 * (1 + abs(lam_v)):
                _fail(
                    f"reliability mismatch for {name!r} — re-derived {lam_v}, "
                    f"recorded {rec_rels[name]}"
                )
    rec_naive_slope = suff.get("naive_slope")
    if rec_naive_slope is not None and not np.allclose(
        b, np.asarray(rec_naive_slope, dtype=float), atol=1e-6,
    ):
        _fail(
            f"naive slope mismatch — re-derived {b.tolist()}, recorded "
            f"{rec_naive_slope}"
        )
    rec_corr_slope = suff.get("corrected_slope")
    if rec_corr_slope is not None and not np.allclose(
        beta, np.asarray(rec_corr_slope, dtype=float), atol=1e-6,
    ):
        _fail(
            f"corrected slope mismatch — re-derived {beta.tolist()}, recorded "
            f"{rec_corr_slope}"
        )

    # Headline point = corrected exposure slope; naive_point = naive exposure slope.
    corrected = float(beta[0])
    naive = float(b[0])

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        _fail(f"missing / non-numeric point {point!r}")
    if abs(corrected - float(point)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(corrected)):
        _fail(f"point mismatch — re-derived corrected {corrected}, recorded {point}")

    claimed_naive = rc.get("naive_point")
    if claimed_naive is None:
        _fail("regression_calibration.naive_point missing")
    if abs(naive - float(claimed_naive)) > _MEASUREMENT_CORRECTION_TOL * (1 + abs(naive)):
        _fail(f"naive_point mismatch — re-derived {naive}, recorded {claimed_naive}")


def _state_key(v):
    """Hashable, bool/int-collision-free key for an outcome state value."""
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", str(v))


def _z_key(z):
    """Order-preserving hashable key for a covariate-stratum value list."""
    return tuple(_state_key(v) for v in z)


def _level_key_v(v):
    """Value-based key mirroring the estimator's ``_level_key`` — a conditioning
    level's bool is collapsed onto its numeric image so a matrix keyed ``0``
    matches an outcome the contract coerced to ``False``. Independent of the
    producer (a second transcription of the same convention)."""
    if isinstance(v, bool):
        return ("n", float(v))
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", str(v))


def _reinvert_stochastic(mat, k, recorded_det, fail, *, label):
    """Independently re-validate + invert one column-stochastic k×k confusion
    matrix from the recorded sufficient statistics. Rejects a wrong shape, a
    non-column-stochastic matrix, a recorded det that disagrees with the matrix,
    and a singular matrix. Returns ``(Minv, det)``."""
    import numpy as np
    M = np.asarray(mat, dtype=float)
    if M.shape != (k, k):
        fail(f"{label} confusion matrix {M.shape} does not match {k} states")
    col_sums = M.sum(axis=0)
    if not np.allclose(col_sums, 1.0, atol=1e-6):
        fail(
            f"{label} confusion matrix is not column-stochastic "
            f"(column sums {[round(float(c), 6) for c in col_sums]})"
        )
    det = float(np.linalg.det(M))
    if recorded_det is not None and abs(det - float(recorded_det)) > 1e-9:
        fail(f"{label} det mismatch — re-derived {det}, recorded {recorded_det}")
    if abs(det) < 1e-12:
        fail(f"{label} confusion matrix is singular — cannot re-invert")
    return np.linalg.inv(M), det


_LONGITUDINAL_TOL = 1e-6


def verify_longitudinal_numeric(estimate: dict) -> None:
    """Audit the numeric answer riding on a longitudinal g-formula /
    IPW-MSM structural identification and reject on violation.

    The structural side (``identify_via_gformula``) is re-checked by the
    derivation verifier; this audits the NUMBER that rides on top — the
    time-varying strategy contrast ``E[Y_{ā=treated}] − E[Y_{ā=control}]``.
    Two estimators, two audit tiers:

    - ``longitudinal_ipw_msm`` (contrast re-derived from the recorded
      marginal-structural-model coefficients): the reported point and both
      strategy means are exact closed forms of the per-time MSM
      coefficients β — ``point = (treated − control)·Σβ_k``,
      ``E[Y_{ā=v}] = β0 + v·Σβ_k``. Recompute them from the recorded β
      vector and reject a mismatch, so a tampered point / mean / single
      coefficient is caught. A fully self-consistent forgery of the whole
      β vector plus its derived quantities is the honest ceiling — the
      verifier does not re-fit the weighted least squares from data.
    - ``longitudinal_gformula`` (construction invariants only): the two
      strategy means come from a black-box Monte-Carlo forward simulation
      over fitted transition + outcome models — not re-derivable without a
      re-fit (the ceiling every data-refit estimator sits at). What IS
      checkable is the construction identity ``point = E_treated −
      E_control`` and the simulation/bootstrap counts; a self-consistent
      forgery of the two means is not caught.

    Both: the nested block's point must equal the headline point, and its
    treatments / outcome must match the headline metadata. ``estimate`` is
    the full ``numeric_estimate`` dict; audited only when a longitudinal
    block is present.
    """
    import math

    def _fail(msg):
        raise VerificationError(msg, step_index=None, rule="longitudinal_numeric")

    def _close(a, b, name):
        if a is None or b is None:
            if a is None and b is None:
                return
            _fail(f"longitudinal.{name}: recomputed {a!r}, recorded {b!r}")
        if not math.isfinite(a):
            _fail(f"longitudinal.{name}: recomputed non-finite {a}")
        if abs(a - b) > _LONGITUDINAL_TOL + 1e-6 * abs(b):
            _fail(f"longitudinal.{name}: recomputed {a}, recorded {b}")

    method = estimate.get("method")
    block = estimate.get("longitudinal_ipw_msm") or estimate.get(
        "longitudinal_gformula"
    )
    if block is None:
        return

    point = block.get("point")
    e1 = block.get("e_y_treated")
    e0 = block.get("e_y_control")

    # Headline / block agreement — the nested answer is the shipped answer.
    _close(point, estimate.get("point"), "block_point==headline_point")
    if block.get("outcome") is not None and estimate.get("outcome") is not None:
        if block["outcome"] != estimate["outcome"]:
            _fail(
                f"block outcome {block['outcome']!r} != headline outcome "
                f"{estimate['outcome']!r}"
            )
    treatments = block.get("treatments")
    if treatments is not None and estimate.get("treatment") is not None:
        if ",".join(treatments) != estimate["treatment"]:
            _fail(
                f"block treatments {treatments!r} do not match headline "
                f"treatment {estimate['treatment']!r}"
            )

    # Construction identity shared by both estimators.
    if e1 is not None and e0 is not None:
        _close(e1 - e0, point, "point==e_y_treated-e_y_control")

    if "longitudinal_ipw_msm" in estimate:
        betas = block.get("msm_coefficients")
        if betas is None:
            _fail("longitudinal_ipw_msm.msm_coefficients missing — cannot "
                  "re-derive the contrast")
        treated = block.get("strategy_treated")
        control = block.get("strategy_control")
        if treated is None or control is None:
            _fail("longitudinal_ipw_msm: strategy_treated / strategy_control "
                  "missing")
        if treatments is not None and len(betas) != len(treatments) + 1:
            _fail(
                f"longitudinal_ipw_msm.msm_coefficients has {len(betas)} "
                f"entries; expected len(treatments)+1 = {len(treatments) + 1} "
                f"(β0 + one per treatment)"
            )
        beta0 = betas[0]
        sum_beta = sum(betas[1:])
        _close((treated - control) * sum_beta, point,
               "ipw_msm.point==(treated-control)*sum_beta")
        _close(beta0 + treated * sum_beta, e1,
               "ipw_msm.e_y_treated==b0+treated*sum_beta")
        _close(beta0 + control * sum_beta, e0,
               "ipw_msm.e_y_control==b0+control*sum_beta")
        # Weights are inverse probabilities: strictly positive, and the max
        # can't sit below the mean.
        w_mean = block.get("weight_mean")
        w_max = block.get("weight_max")
        if w_mean is not None and w_mean <= 0:
            _fail(f"ipw_msm.weight_mean must be positive, got {w_mean}")
        if w_mean is not None and w_max is not None and w_max + _LONGITUDINAL_TOL < w_mean:
            _fail(f"ipw_msm.weight_max {w_max} < weight_mean {w_mean}")

    if "longitudinal_gformula" in estimate:
        # MC black box — only the construction identity (checked above) and
        # the simulation/bootstrap counts are auditable.
        n_sim = block.get("n_sim")
        if n_sim is not None and n_sim <= 0:
            _fail(f"gformula.n_sim must be positive, got {n_sim}")
        nb = block.get("n_bootstrap")
        if nb is not None and nb < 0:
            _fail(f"gformula.n_bootstrap must be non-negative, got {nb}")


def verify_selection_recovery(block: dict, graph) -> None:
    """Independently re-derive a Bareinboim-Pearl selection-recovery block.

    The verdict is a set of d-separation facts about the graph plus a
    closed-form recovery formula and external-data ledger. This verifier
    re-derives all of them from scratch — a SECOND transcription of the
    selection-backdoor conditions and the Theorem-3.5 formula, running on
    the reconstructed graph via low-level structural primitives; it does
    NOT import the producer's ``selection_recovery`` module. It validates
    the returned witness (the adjustment set genuinely satisfies the
    criterion, the Z⁺/Z⁻ partition is correct, the ledger and formula
    match) and, for a negative verdict, re-runs a bounded independent
    search to confirm no admissible set was missed (a producer that
    falsely claimed non-recoverability would be hiding a valid recovery).
    """
    import networkx as nx

    from ..runtime.structural_solver import (
        is_d_connected,
        backdoor_paths,
        _path_is_open,
    )

    def _err(msg: str) -> None:
        raise VerificationError(
            f"selection_recovery: {msg}",
            step_index=None, rule="selection_recovery",
        )

    pred2node = {n.predicate: n for n in graph.nodes}

    def _node(pred: str):
        n = pred2node.get(pred)
        if n is None:
            _err(f"predicate {pred!r} is not a node in the graph")
        return n

    def _dsep(a, b, cond) -> bool:
        return not is_d_connected(graph, a, b, tuple(cond))

    def _s_all_dsep_y(s_nodes, yy, cond) -> bool:
        return all(_dsep(s, yy, cond) for s in s_nodes)

    def _zplus_blocks(xx, yy, zp) -> bool:
        c = frozenset(zp)
        return all(
            not _path_is_open(graph, path, c)
            for path in backdoor_paths(graph, xx, yy)
        )

    def _names(preds) -> str:
        return ", ".join(preds)

    def _cond(*parts) -> str:
        return ", ".join(p for p in parts if p)

    def _rederive_ledger(x_pred, s_nodes, zp_preds, zm_preds):
        z_all_preds = list(zp_preds) + list(zm_preds)
        if not z_all_preds:
            return []
        z_all = [_node(p) for p in z_all_preds]
        if all(_dsep(s, zi, ()) for zi in z_all for s in s_nodes):
            return []
        if not zm_preds:
            return [f"unbiased P({_names(zp_preds)})"]
        return [f"unbiased P({_cond(x_pred, _names(zp_preds), _names(zm_preds))})"]

    def _rederive_effect_formula(x_pred, y_pred, zp, zm):
        zpn, zmn = _names(zp), _names(zm)
        if not zp and not zm:
            return f"P({y_pred} | do({x_pred})) = P({y_pred} | {x_pred}, S)"
        if not zm:
            return (
                f"P({y_pred} | do({x_pred})) = "
                f"Σ_{{{zpn}}} P({y_pred} | {_cond(x_pred, zpn)}, S) · P({zpn})"
            )
        if not zp:
            return (
                f"P({y_pred} | do({x_pred})) = "
                f"Σ_{{{zmn}}} P({y_pred} | {_cond(x_pred, zmn)}, S) · "
                f"P({zmn} | {x_pred})"
            )
        return (
            f"P({y_pred} | do({x_pred})) = "
            f"Σ_{{{zpn}}} [ Σ_{{{zmn}}} P({y_pred} | {_cond(x_pred, zpn, zmn)}, S) "
            f"· P({zmn} | {_cond(x_pred, zpn)}) ] · P({zpn})"
        )

    def _sbd_admissible_exists(x_node, y_node, s_nodes, max_size=4):
        from itertools import combinations
        desc_x = nx.descendants(graph, x_node)
        forbidden = {x_node, y_node} | set(s_nodes)
        cands = [n for n in graph.nodes if n not in forbidden]
        for size in range(0, min(len(cands), max_size) + 1):
            for combo in combinations(cands, size):
                if not _s_all_dsep_y(s_nodes, y_node, (x_node,) + combo):
                    continue
                zp = [n for n in combo if n not in desc_x]
                if _zplus_blocks(x_node, y_node, zp):
                    return True
        return False

    def _conditional_z_exists(x_node, y_node, s_nodes, max_size=4):
        from itertools import combinations
        forbidden = {x_node, y_node} | set(s_nodes)
        cands = [n for n in graph.nodes if n not in forbidden]
        for size in range(1, min(len(cands), max_size) + 1):
            for combo in combinations(cands, size):
                if _s_all_dsep_y(s_nodes, y_node, (x_node,) + combo):
                    return True
        return False

    kind = block.get("query_kind")
    x = _node(block["treatment"])
    y = _node(block["outcome"])
    s_nodes = [_node(p) for p in block["selection_nodes"]]
    if not s_nodes:
        _err("block carries no selection_nodes")
    recoverable = block["recoverable"]
    criterion = block["criterion"]
    zp_preds = list(block["z_plus"])
    zm_preds = list(block["z_minus"])

    if kind == "effect":
        if recoverable:
            if criterion != "selection_backdoor":
                _err(f"effect recoverable but criterion is {criterion!r}")
            desc_x = nx.descendants(graph, x)
            z_plus = [_node(p) for p in zp_preds]
            z_minus = [_node(p) for p in zm_preds]
            for zp in z_plus:
                if zp in desc_x:
                    _err(f"z_plus member {zp.predicate!r} is a descendant of X")
            for zm in z_minus:
                if zm not in desc_x:
                    _err(f"z_minus member {zm.predicate!r} is not a descendant of X")
            z_all = z_plus + z_minus
            if not _s_all_dsep_y(s_nodes, y, (x,) + tuple(z_all)):
                _err("SBD condition (1) fails: S is not d-separated from Y | X,Z")
            if not _zplus_blocks(x, y, z_plus):
                _err("SBD condition (2) fails: Z⁺ leaves a back-door path open")
            ledger = _rederive_ledger(x.predicate, s_nodes, zp_preds, zm_preds)
            if ledger != list(block["external_data_needed"]):
                _err(
                    f"external_data_needed mismatch: recomputed {ledger}, "
                    f"recorded {block['external_data_needed']}"
                )
            formula = _rederive_effect_formula(
                x.predicate, y.predicate, zp_preds, zm_preds
            )
            if formula != block["recovery_formula"]:
                _err(
                    f"recovery_formula mismatch: recomputed {formula!r}, "
                    f"recorded {block['recovery_formula']!r}"
                )
        else:
            if _sbd_admissible_exists(x, y, s_nodes):
                _err(
                    "block claims P(y|do(x)) is not SBD-recoverable, but an "
                    "admissible selection-backdoor set exists within budget"
                )
    elif kind == "conditional":
        if recoverable:
            if criterion == "conditional_independence":
                if not _s_all_dsep_y(s_nodes, y, (x,)):
                    _err("claims Y ⊥ S | X but they are d-connected")
            elif criterion == "external_data":
                z = [_node(p) for p in block["adjustment_set"]]
                if not _s_all_dsep_y(s_nodes, y, (x,) + tuple(z)):
                    _err("claims Y ⊥ S | X,Z but they are d-connected given X,Z")
            else:
                _err(f"conditional recoverable but criterion is {criterion!r}")
        else:
            if _s_all_dsep_y(s_nodes, y, (x,)) or _conditional_z_exists(
                x, y, s_nodes
            ):
                _err(
                    "block claims P(y|x) is not s-recoverable, but Y is "
                    "d-separable from S given X (or X and some observed Z)"
                )
    else:
        _err(f"unknown query_kind {kind!r}")


def verify_missing_data_recovery(block: dict, base_graph, indicators, query) -> None:
    """Independently re-derive a Mohan-Pearl-Tian missing-data block.

    A SECOND transcription of the whole §S9.2 analysis — rebuild the
    m-graph from the declared indicators, reclassify the mechanism
    (MCAR/MAR/MNAR) by d-separation, reconstruct the g-formula
    conditioning set, and re-search the ordered factorization — all via
    low-level structural primitives, NOT by importing the producer's
    missing_data module. It then checks the block's mechanism,
    recoverability verdict, and recovery formula match the re-derivation.

    When the block carries the multi-factor sub-blocks (``covariate_recovery``
    / ``estimand``), it also independently re-derives the covariate marginal
    P(Z | given) recovery and the combined interventional estimand verdict
    (recoverable iff BOTH the conditional and the covariate factor are), and
    checks those too. A bare conditional-only block skips that section.
    """
    import networkx as nx
    from itertools import combinations, permutations

    from ..runtime.structural_solver import is_d_connected, minimal_adjustment_sets
    from ..types import Atom, ConstTerm

    def _err(msg: str) -> None:
        raise VerificationError(
            f"missing_data_recovery: {msg}",
            step_index=None, rule="missing_data_recovery",
        )

    R_PREFIX = "__R__"
    pred2node = {n.predicate: n for n in base_graph.nodes}

    def _dsep(g, a, b, cond):
        return not is_d_connected(g, a, b, tuple(cond))

    # --- rebuild the m-graph (independent transcription) ---
    m = base_graph.copy()
    r_of_var: dict = {}
    for mi in indicators:
        var_node = pred2node.get(mi.missing_var.predicate)
        if var_node is None:
            continue
        r_atom = Atom(
            predicate=f"{R_PREFIX}{var_node.predicate}",
            args=(ConstTerm(name=var_node.predicate),),
        )
        m.add_node(r_atom)
        r_of_var[var_node] = r_atom
        for parent in mi.caused_by:
            p = pred2node.get(parent.predicate)
            if p is not None:
                m.add_edge(p, r_atom)
    if not r_of_var:
        _err("block present but the program declares no missingness indicators")

    vm = set(r_of_var)
    substantive = list(base_graph.nodes)
    vo = [n for n in substantive if n not in vm]

    # --- reclassify mechanism ---
    r_atoms = list(r_of_var.values())
    if all(_dsep(m, r, v, ()) for r in r_atoms for v in substantive):
        mech = "MCAR"
    elif all(_dsep(m, r, vmi, vo) for r in r_atoms for vmi in vm):
        mech = "MAR"
    else:
        mech = "MNAR"
    if mech != block["mechanism"]:
        _err(f"mechanism: recomputed {mech}, recorded {block['mechanism']!r}")

    # --- reconstruct the g-formula conditioning set (as the producer did) ---
    x = pred2node.get(query.intervention.atom.predicate)
    y = pred2node.get(query.target.atom.predicate)
    if x is None or y is None:
        _err("treatment or outcome not in graph")
    given = tuple(
        pred2node[g.atom.predicate] for g in query.given
        if g.atom.predicate in pred2node
    )
    z: tuple = ()
    try:
        adj = minimal_adjustment_sets(base_graph, x, y, given=given)
        if adj:
            z = tuple(sorted(min(adj, key=len), key=lambda a: a.predicate))
    except Exception:
        z = ()
    x_list = [x, *given, *z]
    y_list = [y]

    # --- re-search the ordered factorization (reusable for any factor) ---
    def _pick_xi(yi, later):
        later_list = list(later)
        later_set = set(later_list)
        for size in range(0, min(len(later_list), 4) + 1):
            for xi in combinations(later_list, size):
                rest = later_set - set(xi)
                if any(not _dsep(m, yi, v, xi) for v in rest):
                    continue
                w_i = [yi, *xi]
                r_wi = [r_of_var[v] for v in w_i if v in vm]
                if all(_dsep(m, yi, r, xi) for r in r_wi):
                    return tuple(sorted(xi, key=lambda a: a.predicate))
        return None

    def _search(yl, xl):
        for order in permutations(yl):
            acc = []
            ok = True
            for i, yi in enumerate(order):
                later = list(order[i + 1:]) + list(xl)
                xi = _pick_xi(yi, later)
                if xi is None:
                    ok = False
                    break
                acc.append((yi, xi))
            if ok:
                return acc
        return None

    def _factor_repr(yi, xi):
        w_i = [yi, *xi]
        r_names = ", ".join(f"R_{v.predicate}=0" for v in w_i if v in vm)
        cond = ", ".join(a.predicate for a in xi)
        inside = yi.predicate
        if cond and r_names:
            return f"P({inside} | {cond}, {r_names})"
        if cond:
            return f"P({inside} | {cond})"
        if r_names:
            return f"P({inside} | {r_names})"
        return f"P({inside})"

    def _formula_of(yl, xl, factors):
        ynames = ", ".join(a.predicate for a in yl)
        xnames = ", ".join(a.predicate for a in xl)
        target = f"P({ynames} | {xnames})" if xl else f"P({ynames})"
        factor_strs = [_factor_repr(yi, xi) for yi, xi in factors]
        if len(factor_strs) == 1 and not xl and len(yl) == 1:
            return f"{target} = {factor_strs[0]}"
        return f"{target} = " + " · ".join(factor_strs)

    def _rhs(f):
        return f.split(" = ", 1)[1] if " = " in f else f

    # --- conditional P(Y | X, given, Z) ---
    cond_factors = _search(y_list, x_list)
    cond_recoverable = cond_factors is not None
    if cond_recoverable != block["recoverable"]:
        _err(
            f"recoverable: recomputed {cond_recoverable}, recorded "
            f"{block['recoverable']}"
        )
    if cond_recoverable:
        cond_formula = _formula_of(y_list, x_list, cond_factors)
        if cond_formula != block["recovery_formula"]:
            _err(
                f"recovery_formula: recomputed {cond_formula!r}, recorded "
                f"{block['recovery_formula']!r}"
            )

    # --- covariate marginal P(Z | given) + full-estimand combination ---
    # Only when the block carries the multi-factor sub-blocks (the real
    # scheduler path always does; a bare conditional-only block skips this).
    if "estimand" in block or block.get("covariate_recovery") is not None:
        z_list = list(z)
        cov_factors = None
        cov_recoverable = True            # empty Z ⇒ nothing to recover
        if z_list:
            cov_factors = _search(z_list, list(given))
            cov_recoverable = cov_factors is not None

        cov_block = block.get("covariate_recovery")
        if z_list:
            if cov_block is None:
                _err("covariate_recovery: Z non-empty but block is null")
            if cov_recoverable != cov_block["recoverable"]:
                _err(
                    f"covariate recoverable: recomputed {cov_recoverable}, "
                    f"recorded {cov_block['recoverable']}"
                )
            if cov_recoverable:
                cov_formula = _formula_of(z_list, list(given), cov_factors)
                if cov_formula != cov_block["recovery_formula"]:
                    _err(
                        f"covariate recovery_formula: recomputed "
                        f"{cov_formula!r}, recorded "
                        f"{cov_block['recovery_formula']!r}"
                    )
        elif cov_block is not None:
            _err("covariate_recovery: empty Z but a block was recorded")

        # estimand = conditional × covariate: recoverable iff both are.
        est_recoverable = cond_recoverable and cov_recoverable
        est_block = block.get("estimand")
        if est_block is not None:
            if est_recoverable != est_block["recoverable"]:
                _err(
                    f"estimand recoverable: recomputed {est_recoverable}, "
                    f"recorded {est_block['recoverable']}"
                )
            if est_recoverable:
                gnames = ", ".join(a.predicate for a in given)
                estimand = (
                    f"P({y.predicate} | do({x.predicate}), {gnames})"
                    if given else f"P({y.predicate} | do({x.predicate}))"
                )
                cond_rhs = _rhs(_formula_of(y_list, x_list, cond_factors))
                if z_list:
                    cov_rhs = _rhs(_formula_of(z_list, list(given), cov_factors))
                    zsub = ", ".join(a.predicate for a in z_list)
                    est_formula = f"{estimand} = Σ_{{{zsub}}} {cond_rhs} · {cov_rhs}"
                else:
                    est_formula = f"{estimand} = {cond_rhs}"
                if est_formula != est_block["recovery_formula"]:
                    _err(
                        f"estimand recovery_formula: recomputed "
                        f"{est_formula!r}, recorded "
                        f"{est_block['recovery_formula']!r}"
                    )


def verify_effect_structural(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a STRUCTURALLY_SOLVED effect-query derivation.

    Used by Phase 6.mediation where an EffectQuery with a mediator
    lands in structural-identification territory (no numeric formula).
    The derivation must end with ``identify_via_mediation`` whose
    output matches the claimed StructuralResult.
    """
    if not isinstance(context.query, EffectQuery):
        raise VerificationError(
            "verify_effect_structural requires an EffectQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    last_rule = derivation[-1].rule
    if last_rule not in (
        "identify_via_mediation",
        # Joint multi-mediator block decomposition (VanderWeele-Vansteelandt
        # 2014). Structurally identified before the estimation dispatch
        # attaches the joint estimate_mediation_joint number; verified
        # structurally when no data attaches.
        "identify_via_mediation_joint",
        "identify_via_transport",
        "identify_via_joint_backdoor",
        # Phase 7.L — longitudinal g-formula (sequential back-door) of a
        # time-varying strategy contrast. Structurally identified before the
        # estimation dispatch attaches (and flips to numerically_solved) the
        # g-formula / IPW-MSM number; verified structurally when no number
        # attaches (data absent).
        "identify_via_gformula",
        # Joint general-ID: a latent-confounded joint effect do(A, B, …)
        # with no adjustment set, point-identified by the set-valued
        # Shpitser-Pearl ID. Structurally identified before the estimation
        # dispatch attaches the joint general-ID plug-in number; verified
        # structurally when no data attaches.
        "identify_via_general_id",
    ):
        raise VerificationError(
            "structural effect derivation must end in identify_via_mediation, "
            "identify_via_mediation_joint, identify_via_transport, "
            "identify_via_joint_backdoor, identify_via_gformula, or "
            "identify_via_general_id; got "
            + repr(last_rule),
            step_index=len(derivation) - 1, rule=last_rule,
        )


def verify_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: NumericResult,
) -> None:
    """Verify a numerically-solved effect / probability derivation.

    The context must carry ``theta`` (R6 / R7 need it). The last step
    must be a ``numeric_result`` whose output equals ``claimed_result``.
    """
    if not isinstance(context.query, (EffectQuery, ProbabilityQuery)):
        raise VerificationError(
            "verify_numeric requires an EffectQuery or ProbabilityQuery",
            step_index=None, rule=None,
        )
    if context.theta is None:
        raise VerificationError(
            "verify_numeric requires a non-None theta in the context",
            step_index=None, rule=None,
        )

    step_by_id, _ = _walk(derivation, context, _assert_numeric_query_binding)

    if derivation[-1].rule != "numeric_result":
        raise VerificationError(
            "verify_numeric: last step must be a numeric_result rule",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if isinstance(context.query, EffectQuery):
        evaluation_ref = derivation[-1].inputs.get("evaluation")
        if not isinstance(evaluation_ref, StepRef):
            raise VerificationError(
                "effect derivation final numeric_result must reference an evaluation step",
                step_index=len(derivation) - 1, rule=derivation[-1].rule,
            )
        evaluation_step = step_by_id.get(evaluation_ref.step_id)
        if evaluation_step is None or evaluation_step.rule not in (
            "formula_evaluation",
            "mediation_numeric_evaluate",
            "iv_wald_numeric_evaluate",  # Fix 6 audit follow-up
        ):
            raise VerificationError(
                "effect derivation must end in formula_evaluation -> "
                "numeric_result, mediation_numeric_evaluate -> "
                "numeric_result, or iv_wald_numeric_evaluate -> "
                "numeric_result",
                step_index=len(derivation) - 1, rule=derivation[-1].rule,
            )
        if not any(
            step.rule in (
                "identify_via_backdoor",
                "identify_via_front_door",
                "identify_via_mediation",
                # Joint multi-mediator block: the same mediation_numeric_evaluate
                # closure as the single-mediator path, reached through the block
                # four-condition check instead of the single-mediator one.
                "identify_via_mediation_joint",
                "identify_via_transport",  # Fix 3+4 §T9.2 numeric
                "identify_via_tian",       # Fix 5 audit follow-up
                "identify_via_iv",         # Fix 6 audit follow-up
                "identify_via_idc",        # Phase 2 conditional general-ID
            )
            for step in derivation
        ):
            raise VerificationError(
                "effect derivation is missing an identify_via_backdoor, "
                "identify_via_front_door, identify_via_mediation, "
                "identify_via_mediation_joint, "
                "identify_via_transport, identify_via_tian, identify_via_iv, "
                "or identify_via_idc witness",
                step_index=len(derivation) - 1, rule=derivation[-1].rule,
            )


def verify_cause(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a cause-query derivation.

    - V3: negative case, witnessed by a single ``no_directed_path`` step.
    - V4: positive case, witnessed by a single ``cause_via_directed_path``
      step whose ``paths`` input carries the concrete directed paths.
    """
    if not isinstance(context.query, CauseQuery):
        raise VerificationError(
            "verify_cause requires a CauseQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_cause_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    expected_rule = (
        "cause_via_directed_path"
        if claimed_result.value is True
        else "no_directed_path"
    )
    if derivation[-1].rule != expected_rule:
        raise VerificationError(
            f"cause derivation with value={claimed_result.value!r} must end in "
            f"{expected_rule!r}, got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def verify_assoc(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify an assoc-query derivation.

    - V3: negative case, witnessed by a single ``d_separated`` step.
    - V4: positive case, witnessed by a single ``d_connected_via_open_path``
      step whose ``paths`` input carries the open paths.
    """
    if not isinstance(context.query, AssocQuery):
        raise VerificationError(
            "verify_assoc requires an AssocQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_assoc_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if context.bidirected:
        expected_rule = (
            "m_connection_witness"
            if claimed_result.value is True
            else "m_separation_witness"
        )
    else:
        expected_rule = (
            "d_connected_via_open_path"
            if claimed_result.value is True
            else "d_separated"
        )
    if derivation[-1].rule != expected_rule:
        raise VerificationError(
            f"assoc derivation with value={claimed_result.value!r} must end in "
            f"{expected_rule!r}, got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def verify_counterfactual(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: NumericResult,
) -> None:
    """Verify a binary counterfactual-cell derivation.

    Single witness family: ``counterfactual_cell_bounds``. The rule
    independently recovers the observational joint from ``ctx.theta``,
    re-solves the cell from the consistency identity, and audits the
    declared interventional risk and its provenance.
    """
    if not isinstance(context.query, CounterfactualQuery):
        raise VerificationError(
            "verify_counterfactual requires a CounterfactualQuery in the context",
            step_index=None, rule=None,
        )
    if context.theta is None:
        raise VerificationError(
            "verify_counterfactual requires a non-None theta in the context",
            step_index=None, rule=None,
        )

    _walk(derivation, context, _assert_counterfactual_query_binding)

    if derivation[-1].rule != "counterfactual_cell_bounds":
        raise VerificationError(
            "counterfactual derivation must end in "
            "'counterfactual_cell_bounds'",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def verify_counterfactual_cell_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a data-based counterfactual-cell derivation — the numeric
    counterpart of ``verify_counterfactual``.

    The derivation must end in ``numeric_counterfactual_cell_estimate``. That
    single rule re-solves the consistency identity (the verifier's OWN
    transcription) on the reported empirical joint + interventional risk,
    re-derives from the query whether the cell needs a risk at all, re-derives
    the back-door adjustment set on ``ctx.graph``, and audits the estimate
    metadata — no re-fit on the raw data, the same trade-off the other numeric
    verifiers make. Unlike the theta path it needs no theta: the joint arrives
    as reported empirical frequencies rather than being recovered symbolically.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, CounterfactualQuery):
        raise VerificationError(
            "verify_counterfactual_cell_numeric requires a CounterfactualQuery "
            "in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_counterfactual_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "numeric_counterfactual_cell_estimate":
        raise VerificationError(
            "counterfactual numeric derivation must end in "
            f"'numeric_counterfactual_cell_estimate'; got "
            f"{derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def _assert_causation_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Causation derivations have a single rule whose cause/effect binding
    is rechecked inside the rule against ``ctx.query`` (parallel to the
    counterfactual asserter)."""
    return None


def verify_causation(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: NumericResult,
) -> None:
    """Verify a probabilities-of-causation (PN/PS/PNS) derivation.

    The single ``probabilities_of_causation_tian_pearl`` rule
    independently re-checks the observational joint (from theta) and
    re-derives the Tian-Pearl bounds/points, auditing the whole envelope.
    Here we additionally cross-check that the claimed headline
    ``numeric_result`` (the PN quantity) is consistent with the verified
    envelope — point under monotonicity, interval otherwise.
    """
    if not isinstance(context.query, CausationQuery):
        raise VerificationError(
            "verify_causation requires a CausationQuery in the context",
            step_index=None, rule=None,
        )
    if context.theta is None:
        raise VerificationError(
            "verify_causation requires a non-None theta in the context",
            step_index=None, rule=None,
        )

    _walk(derivation, context, _assert_causation_query_binding)

    if derivation[-1].rule != "probabilities_of_causation_tian_pearl":
        raise VerificationError(
            "causation derivation must end in "
            "'probabilities_of_causation_tian_pearl'",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    envelope = derivation[-1].output
    pn = envelope.get("pn") if isinstance(envelope, dict) else None
    if not isinstance(pn, dict):
        raise VerificationError(
            "causation envelope is missing the pn block",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if pn.get("point") is not None:
        expected = NumericResult(value=float(pn["point"]))
    else:
        expected = NumericResult(
            value=None,
            interval=NumericInterval(
                low=float(pn["lower"]), high=float(pn["upper"]),
            ),
        )
    if not _numeric_result_matches(claimed_result, expected):
        raise VerificationError(
            "causation headline (PN) does not match the verified envelope",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def verify_causation_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a data-based PN/PS/PNS estimate derivation — the numeric
    counterpart of ``verify_causation``.

    The derivation must end in ``numeric_causation_estimate``. That single rule
    re-applies the Tian-Pearl theorem (the verifier's OWN transcription) to the
    reported empirical joint + do-risks and confirms the reported PN/PS/PNS
    bounds and points, re-derives the back-door adjustment set on ``ctx.graph``,
    and audits the estimate metadata — no re-fit on the raw data, the same
    trade-off the other numeric verifiers make.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, CausationQuery):
        raise VerificationError(
            "verify_causation_numeric requires a CausationQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_causation_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "numeric_causation_estimate":
        raise VerificationError(
            "causation numeric derivation must end in "
            f"'numeric_causation_estimate'; got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def _assert_scm_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """SCM-counterfactual derivations have a single rule whose binding to
    the query/graph/observations is rechecked inside the rule."""
    return None


def verify_scm_counterfactual(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: NumericResult,
) -> None:
    """Verify a deterministic linear-SCM counterfactual derivation.

    The single ``scm_abduction_action_prediction`` rule independently
    re-runs Pearl's three-step computation from the structural
    coefficients on the graph + the unit's observations and checks the
    claimed point. Here we also pin the terminal rule and confirm the
    last step's output equals the claimed numeric result.
    """
    if not isinstance(context.query, SCMCounterfactualQuery):
        raise VerificationError(
            "verify_scm_counterfactual requires a SCMCounterfactualQuery "
            "in the context",
            step_index=None, rule=None,
        )
    if context.observations is None:
        raise VerificationError(
            "verify_scm_counterfactual requires the unit's observations in "
            "the context",
            step_index=None, rule=None,
        )

    _walk(derivation, context, _assert_scm_query_binding)

    if derivation[-1].rule != "scm_abduction_action_prediction":
        raise VerificationError(
            "scm_counterfactual derivation must end in "
            "'scm_abduction_action_prediction'",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


_SCM_FIT_TOL = 1e-6


def verify_scm_counterfactual_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result,
    num_est: dict,
) -> None:
    """Verify a DATA-fitted linear-SCM counterfactual (``themis.estimate``).

    Two independent layers:

    1. Walk the single ``numeric_scm_counterfactual_estimate`` terminal
       (metadata audit + query binding), pin the terminal, and check its
       output equals the claimed ``StructuralResult``.
    2. STRONG re-derivation from the recorded sufficient statistics: for every
       relevant node re-solve its OLS ``β=(XᵀX)⁻¹Xᵀy`` from the recorded moment
       matrices, confirm the parent set matches ``ctx.graph`` and the re-solved
       slopes match the recorded coefficients, then re-run Pearl's
       abduction–action–prediction from the re-solved slopes + the recorded
       unit and confirm the counterfactual point. Deliberately does NOT import
       the estimator or ``runtime.scm_counterfactual`` — the verifier carries
       the arithmetic; only the moment matrices (anchored by ``data_hash``) and
       the unit are taken on trust (the data-refit ceiling).
    """
    if not isinstance(context.query, SCMCounterfactualQuery):
        raise VerificationError(
            "verify_scm_counterfactual_numeric requires a SCMCounterfactualQuery",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_scm_query_binding)
    if derivation[-1].rule != "numeric_scm_counterfactual_estimate":
        raise VerificationError(
            "scm_counterfactual numeric derivation must end in "
            "'numeric_scm_counterfactual_estimate'",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].output != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    _recheck_scm_counterfactual_fit(context, num_est)


def _recheck_scm_counterfactual_fit(
    context: VerificationContext, num_est: dict,
) -> None:
    """Independent re-solve of the OLS moments + re-run of abduction-action-
    prediction. Raises VerificationError on any mismatch."""
    import numpy as np
    import networkx as nx

    graph = context.graph
    q = context.query
    x_atom = q.intervention.atom
    y_atom = q.target
    if x_atom not in graph or y_atom not in graph:
        raise VerificationError(
            "scm_counterfactual numeric: query atoms not in graph",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )

    # Relevant set + topo, independently from the graph (mirrors the estimator).
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(graph.in_edges(x_atom)))
    relevant = set(nx.ancestors(mutilated, y_atom)) | {y_atom}
    fit_nodes = [v for v in relevant if v != x_atom]

    name_to_atom: dict[str, object] = {}
    for a in relevant:
        if a.predicate in name_to_atom:
            raise VerificationError(
                "scm_counterfactual numeric: ambiguous predicate in relevant set",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        name_to_atom[a.predicate] = a

    node_fits = num_est.get("node_fits")
    if not isinstance(node_fits, list):
        raise VerificationError(
            "scm_counterfactual numeric: node_fits must be a list",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )
    fits_by_node = {f.get("node"): f for f in node_fits}
    if set(fits_by_node) != {v.predicate for v in fit_nodes}:
        raise VerificationError(
            "scm_counterfactual numeric: recorded fits do not match the "
            "graph-derived relevant node set",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )

    equations: dict = {}
    for v in fit_nodes:
        f = fits_by_node[v.predicate]
        parents = f.get("parents")
        recorded_coef = f.get("coefficients")
        if not isinstance(parents, list) or not isinstance(recorded_coef, list):
            raise VerificationError(
                "scm_counterfactual numeric: parents / coefficients malformed",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        # Parent SET must match the graph independently.
        if set(parents) != {p.predicate for p in graph.predecessors(v)}:
            raise VerificationError(
                f"scm_counterfactual numeric: recorded parents for {v.predicate!r} "
                f"do not match the graph",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        k = len(parents)
        xtx = np.array(f.get("xtx"), dtype=float)
        xty = np.array(f.get("xty"), dtype=float)
        if xtx.shape != (k + 1, k + 1) or xty.shape != (k + 1,) \
                or len(recorded_coef) != k:
            raise VerificationError(
                "scm_counterfactual numeric: moment-matrix shapes inconsistent "
                f"with parent count for {v.predicate!r}",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        try:
            beta = np.linalg.solve(xtx, xty)
        except np.linalg.LinAlgError:
            raise VerificationError(
                f"scm_counterfactual numeric: recorded XtX for {v.predicate!r} is "
                f"singular — slopes are not re-solvable",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        slopes = [float(b) for b in beta[1:]]
        for got, claimed in zip(slopes, recorded_coef):
            if abs(got - float(claimed)) > _SCM_FIT_TOL:
                raise VerificationError(
                    f"scm_counterfactual numeric: re-solved OLS slope for "
                    f"{v.predicate!r} ({got}) != recorded coefficient ({claimed})",
                    step_index=None, rule="numeric_scm_counterfactual_estimate",
                )
        # Build the equation from the verifier's OWN re-solved slopes.
        equations[v] = tuple(
            (name_to_atom[p], s) for p, s in zip(parents, slopes)
        )

    # The unit's observed values (relevant set must be fully covered).
    observed_raw = num_est.get("observed_unit")
    if not isinstance(observed_raw, list):
        raise VerificationError(
            "scm_counterfactual numeric: observed_unit must be a list",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )
    observed: dict = {}
    for pair in observed_raw:
        name, val = pair[0], pair[1]
        if name not in name_to_atom:
            raise VerificationError(
                f"scm_counterfactual numeric: observed_unit names a non-relevant "
                f"variable {name!r}",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )
        observed[name_to_atom[name]] = float(val)
    for v in relevant:
        if v not in observed:
            raise VerificationError(
                f"scm_counterfactual numeric: unit missing relevant variable "
                f"{v.predicate!r}",
                step_index=None, rule="numeric_scm_counterfactual_estimate",
            )

    iv_val = float(num_est.get("intervention_value"))
    if abs(iv_val - float(q.intervention.value)) > _SCM_FIT_TOL:
        raise VerificationError(
            "scm_counterfactual numeric: intervention_value does not match the query",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )

    # (i) Abduction — intercept absorbed into each recovered exogenous term.
    noise = {
        v: observed[v] - sum(coef * observed[p] for p, coef in terms)
        for v, terms in equations.items()
    }
    # (ii) Action + (iii) Prediction.
    topo = [n for n in nx.topological_sort(graph) if n in relevant]
    cf: dict = {}
    for v in topo:
        if v == x_atom:
            cf[v] = iv_val
        else:
            cf[v] = noise[v] + sum(coef * cf[p] for p, coef in equations[v])
    expected = cf[y_atom]

    point = num_est.get("point")
    if point is None or abs(float(point) - expected) > _SCM_FIT_TOL:
        raise VerificationError(
            f"scm_counterfactual numeric: recorded point {point} != independently "
            f"recomputed {expected}",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )


def _assert_ctf_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Counterfactual-conjunction derivations have a single rule whose
    binding to the query/graph is rechecked inside the rule."""
    return None


def verify_counterfactual_conjunction(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a general counterfactual identification (ID*) derivation.

    The terminal ``id_star_identification`` rule re-runs the ID* engine and
    confirms the outcome CLASS (identifiable / inconsistent-zero) matches
    the claim (a structural licence). On top of that — mirroring
    ``verify_identify`` — this pins the terminal rule, checks the last
    step's output equals the claim, and, unless ``P(γ)=0``, runs a
    Monte-Carlo semantic probe: it samples random SCMs consistent with the
    ADMG, computes the true ``P(γ)`` by counterfactual Monte-Carlo over a
    shared exogenous background, and requires the claimed formula to match.
    A formula that passes every structural check but computes the wrong
    number is rejected here.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, CounterfactualConjunctionQuery):
        raise VerificationError(
            "verify_counterfactual_conjunction requires a "
            "CounterfactualConjunctionQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_ctf_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "id_star_identification":
        raise VerificationError(
            "counterfactual-conjunction derivation must end in "
            f"'id_star_identification'; got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    # Semantic backbone: the structural rule proves the query is identified;
    # it does NOT prove the FORMULA computes the true P(γ). Probe it against
    # random SCMs. P(γ)=0 (an inconsistent conjunction, rendered as the
    # constant 0) has no formula to probe — the rule already confirmed the
    # ID* engine agrees it is inconsistent.
    formula = derivation[-1].inputs.get("formula")
    is_zero = isinstance(formula, ConstantExpr) and formula.value == 0.0
    if formula is not None and not is_zero:
        from ..runtime.ctf_identify import CtfEvent
        q = context.query

        def _to_gamma(events):
            return tuple(
                CtfEvent(
                    variable=e.variable,
                    subscript=frozenset((s.atom, s.value) for s in e.subscript),
                    value=e.value,
                )
                for e in events
            )

        gamma = _to_gamma(q.events)
        delta = _to_gamma(q.condition)
        domains = context.theta.domains if context.theta is not None else {}
        # Conditional (IDC*) formulas are a P(γ',δ')/P(δ') ratio — probe them
        # with the conditional Monte-Carlo backbone (numerator and denominator
        # share one exogenous draw); unconditional (ID*) formulas use the plain
        # P(γ) probe.
        if delta:
            probe = probe_conditional_counterfactual_formula(
                context.graph, context.bidirected,
                gamma=gamma, delta=delta, formula=formula, domains=domains,
            )
            quantity = "P(γ|δ)"
        else:
            probe = probe_counterfactual_formula(
                context.graph, context.bidirected,
                gamma=gamma, formula=formula, domains=domains,
            )
            quantity = "P(γ)"
        if probe.status == "mismatch":
            raise VerificationError(
                "counterfactual formula fails semantic verification: it does "
                f"not compute the true {quantity} in a model consistent with "
                f"the graph. {probe.detail}",
                step_index=len(derivation) - 1, rule=derivation[-1].rule,
            )


def verify_ctf_conjunction_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a data-based counterfactual-conjunction (ID*/IDC* plug-in)
    estimate derivation — the numeric counterpart of
    ``verify_counterfactual_conjunction``.

    The derivation must end in ``numeric_ctf_conjunction_estimate`` atop a
    ``ctf_conjunction_criterion`` structural witness. The rule handlers
    re-run ID*/IDC* to confirm the conjunction is identifiable
    (safety-critical: a number is licensed ONLY for an identified
    counterfactual) and audit the estimate's metadata self-consistency
    (method enum / CI bounds / data_hash / sample_size) — no re-fit, the
    same cost trade-off ``verify_numeric_estimate`` makes for the effect
    data estimators.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, CounterfactualConjunctionQuery):
        raise VerificationError(
            "verify_ctf_conjunction_numeric requires a "
            "CounterfactualConjunctionQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_ctf_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "numeric_ctf_conjunction_estimate":
        raise VerificationError(
            "counterfactual-conjunction numeric derivation must end in "
            f"'numeric_ctf_conjunction_estimate'; got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def _assert_proximal_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
    step_by_id: dict[str, DerivationStep],
    step_output_by_id: dict[str, object],
) -> None:
    """Proximal derivations have rules whose binding to the query/graph is
    rechecked inside the rule (``proximal_criterion`` re-runs identify_proximal
    from ``ctx.query``)."""
    return None


def verify_proximal_effect(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a structural proximal-identification derivation.

    The terminal ``proximal_criterion`` rule re-runs ``identify_proximal`` on
    the context's (graph, bidirected) and the query's roles, confirming the
    effect is proximal-identifiable (Miao model (f)) — the independent safety
    check. Here we pin the terminal rule and confirm the last step's output
    equals the claim. Proximal identification produces a matrix estimand
    descriptor, not a formula, so there is no formula to semantically probe —
    the independent re-run of identify_proximal IS the semantic check.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, ProximalEffectQuery):
        raise VerificationError(
            "verify_proximal_effect requires a ProximalEffectQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_proximal_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "proximal_criterion":
        raise VerificationError(
            "proximal derivation must end in 'proximal_criterion'; got "
            f"{derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )


def verify_proximal_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify a data-based proximal (matrix plug-in) estimate derivation — the
    numeric counterpart of ``verify_proximal_effect``.

    The derivation must end in ``numeric_proximal_estimate`` atop a
    ``proximal_criterion`` structural witness. The rule handlers re-run
    ``identify_proximal`` to confirm proximal-identifiability (safety-critical:
    a number is licensed ONLY for an identified effect) and audit the
    estimate's metadata self-consistency (method enum / CI bounds / data_hash /
    sample_size) — no re-fit, the same trade-off the other numeric verifiers
    make.

    Raises ``VerificationError`` on reject; returns ``None`` on accept.
    """
    if not isinstance(context.query, ProximalEffectQuery):
        raise VerificationError(
            "verify_proximal_numeric requires a ProximalEffectQuery in the context",
            step_index=None, rule=None,
        )
    _walk(derivation, context, _assert_proximal_query_binding)

    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    if derivation[-1].rule != "numeric_proximal_estimate":
        raise VerificationError(
            "proximal numeric derivation must end in 'numeric_proximal_estimate';"
            f" got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
