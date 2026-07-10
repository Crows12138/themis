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
        # General-ID (c-factor) non-parametric plug-in — the effect is
        # point-identified only through the general ID algorithm (e.g. the
        # napkin); the derivation ends in the plug-in terminal atop a
        # general_id_criterion structural witness.
        "numeric_general_id_estimate",
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
        "identify_via_transport",
        "identify_via_joint_backdoor",
    ):
        raise VerificationError(
            "structural effect derivation must end in identify_via_mediation, "
            "identify_via_transport, or identify_via_joint_backdoor; got "
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
                "identify_via_transport",  # Fix 3+4 §T9.2 numeric
                "identify_via_tian",       # Fix 5 audit follow-up
                "identify_via_iv",         # Fix 6 audit follow-up
            )
            for step in derivation
        ):
            raise VerificationError(
                "effect derivation is missing an identify_via_backdoor, "
                "identify_via_front_door, identify_via_mediation, "
                "identify_via_transport, identify_via_tian, or "
                "identify_via_iv witness",
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
    """Verify a narrow counterfactual derivation.

    Current Phase 5 §C scope has a single witness family:
    ``counterfactual_bounds_binary_monotone``. The rule independently
    recomputes the currently landed binary monotone bounds / point value
    from ``ctx.query`` + ``ctx.theta``.
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

    if derivation[-1].rule != "counterfactual_bounds_binary_monotone":
        raise VerificationError(
            "counterfactual derivation must end in "
            "'counterfactual_bounds_binary_monotone'",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            "last derivation step output does not equal claimed result",
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
