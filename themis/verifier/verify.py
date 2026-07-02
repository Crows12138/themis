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
from .semantic_probe import probe_identify_formula


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
