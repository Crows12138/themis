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

from typing import Callable, NoReturn, TypeVar

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
from .declaration_rules import (
    CONFUSION_MATRIX, VARIANCE, check_declaration_premises,
)
from .errors import (
    RuleNotFoundError,
    StepRefError,
    VerificationError,
)
from .rules import (
    Counterfactual, _numeric_result_matches, abduct_act_predict,
    dispatch_rule, known_rule,
)
from .semantic_probe import (
    formula_fits,
    probe_conditional_counterfactual_formula,
    probe_counterfactual_formula,
    probe_identify_formula,
)
from .serialization import _DECODE_BY_KIND, DerivationSerializationError


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


_QueryT = TypeVar("_QueryT")


def _query_as(context: VerificationContext, shape: type[_QueryT]) -> _QueryT:
    """Read the context query at the shape the caller was written for.

    Every ``verify_*`` entry point checks the query shape before it starts
    the walk, and each binding asserter / re-check helper is installed by
    exactly one of them. That guarantee lived only in the call graph; this
    states it where the reader (and the checker) is.
    """
    q = context.query
    if not isinstance(q, shape):
        raise VerificationError(
            f"verification context carries a {type(q).__name__}, "
            f"not a {shape.__name__}",
            step_index=None, rule=None,
        )
    return q


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


# Rules that may produce a formula referenced by
# subsequent formula_evaluation steps. When the verifier checks an
# effect query's formula_evaluation, the formula must equal the
# output of one of these prior witness steps. A path missing from this
# set is silently rejected by the verifier even though the scheduler
# emitted a well-formed formula, so new identification paths that
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
    """Reject derivations that prove *some other* query on the same graph.

    Installed by every entry point whose query is identify-SHAPED — one
    intervention, one target, one conditioning set: ``verify_identify``
    (IdentifyQuery) plus ``verify_numeric_estimate`` and
    ``verify_effect_structural`` (EffectQuery). Each rule below has to
    name the active query's X, Y and given, so a perfectly valid proof
    for a different (X, Y, given, do-value) cannot be replayed here.

    The two query types state those three things at different shapes, and
    the rules need both shapes. An IdentifyQuery leaves the literal open:
    its target is a bare ``Atom`` and the estimand is the whole
    distribution. An EffectQuery asks about one literal: its target is a
    ``ValuedAtom`` and that value is part of the question. Criterion rules
    reason structurally and so name bare atoms; formula rules build an
    estimand and so name valued ones. The query is therefore unpacked once
    into ``*_atom`` / ``*_va`` names and every branch compares against
    those. Picking ``q.target`` or ``q.given`` apart inside a branch
    instead is what makes a branch bind correctly for one query type while
    comparing incommensurable shapes — and so rejecting unconditionally —
    for the other.
    """
    q = context.query
    if isinstance(q, EffectQuery):
        # The valued shape is the query's own; the bare shape drops the value.
        q_target_atom = q.target.atom
        q_target_va = q.target
        q_given_atoms = frozenset(g.atom for g in q.given)
        q_given_vas = frozenset(q.given)
    elif isinstance(q, IdentifyQuery):
        # The bare shape is the query's own; the valued shape spells the
        # open literal as value=None, which is what the formula builders
        # emit for an identify estimand.
        q_target_atom = q.target
        q_target_va = ValuedAtom(atom=q.target, value=None)
        q_given_atoms = frozenset(q.given)
        q_given_vas = frozenset(
            ValuedAtom(atom=a, value=None) for a in q.given
        )
    else:
        raise VerificationError(
            "identify-shaped query binding requires an IdentifyQuery or an "
            f"EffectQuery; got a {type(q).__name__}",
            step_index=step_index, rule=step.rule,
        )
    # Both types state the intervention as an Intervention(atom, value),
    # so X is the one axis that needs no per-type branch.
    q_x_atom = q.intervention.atom
    q_x_va = ValuedAtom(atom=q_x_atom, value=q.intervention.value)

    if step.rule == "backdoor_criterion":
        if step.inputs.get("x") != q_x_atom:
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
        if step.inputs.get("target") != q_target_va:
            raise VerificationError(
                "backdoor_adjustment_formula.target does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        if step.inputs.get("intervention") != q_x_va:
            raise VerificationError(
                "backdoor_adjustment_formula.intervention does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        step_given = step.inputs.get("given", ())
        if frozenset(step_given) != q_given_vas:
            raise VerificationError(
                "backdoor_adjustment_formula.given does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )

    if step.rule == "unidentifiable_via_backdoor":
        if step.inputs.get("x") != q_x_atom:
            raise VerificationError(
                "unidentifiable_via_backdoor.x does not match verification context query",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                "unidentifiable_via_backdoor.y does not match verification context query",
                step_index=step_index, rule=step.rule,
            )
        step_given = step.inputs.get("given", frozenset())
        if frozenset(step_given) != q_given_atoms:
            raise VerificationError(
                "unidentifiable_via_backdoor.given does not match verification context query",
                step_index=step_index, rule=step.rule,
            )

    # A6 front-door: same binding shape as backdoor's, but since the
    # front-door formula builder currently does not accept an
    # ``observed`` conditioning set, we require the active query to
    # have ``given == ()``. That keeps the verifier from accepting a
    # front-door proof for a conditioned query it cannot construct.
    if step.rule == "front_door_criterion":
        if step.inputs.get("x") != q_x_atom:
            raise VerificationError(
                "front_door_criterion.x does not match verification context query",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("y") != q_target_atom:
            raise VerificationError(
                "front_door_criterion.y does not match verification context query",
                step_index=step_index, rule=step.rule,
            )
        if q_given_atoms:
            raise VerificationError(
                "front_door_criterion requires the verification context "
                "query's given to be empty",
                step_index=step_index, rule=step.rule,
            )

    if step.rule == "front_door_adjustment_formula":
        if step.inputs.get("target") != q_target_va:
            raise VerificationError(
                "front_door_adjustment_formula.target does not match "
                "verification context query",
                step_index=step_index, rule=step.rule,
            )
        if step.inputs.get("intervention") != q_x_va:
            raise VerificationError(
                "front_door_adjustment_formula.intervention does not match "
                "verification context query",
                step_index=step_index, rule=step.rule,
            )
        if q_given_atoms:
            raise VerificationError(
                "front_door_adjustment_formula requires the verification "
                "context query's given to be empty",
                step_index=step_index, rule=step.rule,
            )

    # Joint (treatment-set) back-door: the criterion step declares the
    # whole treatment vector + target + given it reasons about. Bind them
    # to the active EffectQuery so a joint proof for one (treatments, Y,
    # given) cannot be replayed against another query on the same graph.
    if step.rule == "joint_backdoor_criterion" and isinstance(q, EffectQuery):
        # The one branch that reads ``q`` directly: a joint treatment vector
        # exists only on an EffectQuery, so there is no shape to unify.
        expected_treatments = frozenset(
            (q_x_atom, *(iv.atom for iv in q.extra_interventions))
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
        if step.inputs.get("x") != q_x_atom:
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
    q = _query_as(context, CauseQuery)
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
    q = _query_as(context, AssocQuery)
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
            expected_given_atoms = frozenset(g.atom for g in q.given)
            if frozenset(step_given) != expected_given_atoms:
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


#: What the probe says when it has an opinion. ``inconclusive`` is not
#: here and that is the whole point of there being a list: a probe that
#: could not run is silent, and a formula that is not about this graph is
#: not silent — they were one word until the cheapest forgery in the
#: census turned out to be the one that produced it.
#:
#: ``unevaluable`` is the same distinction one layer in. The text check
#: that produces ``unfit`` runs before any sampling; inside the sampling
#: loop every failure was still answered with the word that means
#: silence, and a formula asking this model for a factor the model's own
#: factorisation does not hold got past on it.
_PROBE_REFUSES = ("mismatch", "unfit", "unevaluable")


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
        expected_finals: tuple[str, ...] = (
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
                y=q.target, given=_conditioned(q), formula=formula,
                domains=domains,
            )
            if probe.status in _PROBE_REFUSES:
                raise VerificationError(
                    # The prefix says THAT the probe refused; the detail
                    # says why. It used to say why as well, and it said
                    # one verdict's reason for all of them — a formula
                    # this model cannot even be asked was reported as one
                    # computing the wrong number.
                    "identify formula fails semantic verification against "
                    f"models consistent with the graph. {probe.detail}",
                    step_index=len(derivation) - 1, rule=derivation[-1].rule,
                )


def _conditioned(query) -> tuple[ValuedAtom, ...]:
    """The variables a question conditions on, each with the value it names.

    An identify query names variables; an effect query names variables AND
    the value its estimand is about, the same way it names one value of Y.
    The probe hears both in one shape — a name, and a value where the
    question gives one — so neither caller has to say it twice, and neither
    can say it in a shape the other's parameter drops on the floor.
    """
    return tuple(
        g if isinstance(g, ValuedAtom) else ValuedAtom(atom=g, value=None)
        for g in (getattr(query, "given", ()) or ()))


def _probability_refs(expr):
    """Every probability factor in a formula, in document order."""
    if isinstance(expr, ProbabilityRefExpr):
        yield expr
    elif isinstance(expr, ProductExpr):
        for term in expr.terms:
            yield from _probability_refs(term)
    elif isinstance(expr, SumExpr):
        yield from _probability_refs(expr.body)
    elif isinstance(expr, FractionExpr):
        yield from _probability_refs(expr.numerator)
        yield from _probability_refs(expr.denominator)


def _as_conditional(target, given) -> str:
    """A conditional the way the report prints it, for saying which one
    this is. The value is part of the quantity — ``P(y=true | x=true)``
    and ``P(y=false | x=true)`` are two of them — so a message that left
    it out could name the forgery and the honest formula with one line."""
    def one(va):
        return (f"{va.atom.predicate}={va.value}" if va.value is not None
                else va.atom.predicate)
    body = ", ".join(one(g) for g in given)
    return f"P({one(target)}{' | ' + body if body else ''})"


def _hold_the_question_itself(formula, query) -> None:
    """A question with no intervention identifies nothing, so its estimand
    IS the question and can be held to it.

    The third question, and the third prerequisite. Whether a formula is
    ABOUT this problem needs the names it uses; whether it COMPUTES what
    was asked needs an (X, Y) pair and a model to sample. A probability
    question has no X, so no model can be asked — and none is needed,
    because nothing was identified. The quantity a reader is shown is the
    quantity that was asked for, or it is a different quantity printed
    under the same heading.

    The comparison is not new, and what was new is which record it holds.
    ``_assert_query_binding`` puts a ``formula_evaluation`` step against
    the query's own reference, so the chain's account of what it evaluated
    is held while ``result["formula"]`` — the copy the report prints and
    the browser shows — is not; forging that copy on an answer whose chain
    carries the step passes the same door that refuses a forged step. An
    answer that took no route has no chain there at all.

    Order is not part of a quantity. ``P(y | a, b)`` and ``P(y | b, a)``
    are one conditional and a reader reads them as one, so the conditions
    are compared as a multiset. The chain half compares them verbatim and
    is right to: what it holds is provenance — that the step evaluated the
    object the query built — which is a stricter question than this one.
    """
    if not isinstance(formula, ProbabilityRefExpr):
        raise VerificationError(
            "the estimand shown to a reader is not written as the "
            "conditional this question names. A probability question "
            "identifies nothing, so the only estimand its route produces "
            "is that conditional; a formula of another shape is not one "
            "this comparison can be made against, and letting it through "
            "would be silence wearing assent's clothes",
            step_index=None, rule="identification_formula",
        )
    same_conditions = (sorted(formula.given, key=repr)
                       == sorted(query.given, key=repr))
    if formula.target != query.target or not same_conditions:
        raise VerificationError(
            f"the estimand shown to a reader is "
            f"{_as_conditional(formula.target, formula.given)}; the question "
            f"asks for {_as_conditional(query.target, query.given)}",
            step_index=None, rule="identification_formula",
        )


def _hold_populations(formula, context) -> None:
    """Which population each factor of the estimand is read from.

    A formula is read in the population the question is about, and one
    kind of estimand is not: a transported one takes the effect's own
    conditional from a source domain, where the treatment was randomised,
    and every other factor from the target. Two places, printed as one
    line — a reader who is not told cannot tell them apart, and was not
    told, because the encoder that writes the envelope's copy of a formula
    never learned the field the producer sets on it.

    The probe cannot settle this: its model is one population and this
    formula is about two. But WHICH two is not a question for a model at
    all, so the tag is re-derived rather than trusted — the source from
    the selection nodes the program declares, the target from the
    question's own ``target_population``, and which factor is which from
    the formula's own shape. Where the problem has one population there is
    nothing to choose between and silence names it; a factor that names a
    population anyway is naming something this problem does not have.

    An estimand reads from two places when the question names a
    population AND the program declares selection nodes — both halves of
    the program's own text, neither of them the route the answer took.
    Either half alone is a one-population formula and demanding a source
    tag from one would be a false refusal: selection nodes with an
    ordinary question do not transport, and a question naming a
    population with no selection node is the trivial case, where no shift
    was declared, the two diagrams are the same one, and there is no
    source domain to name.
    """
    asked = getattr(context.query, "target_population", None)
    sources = ({sn.source_population for sn in context.selection_nodes}
               if asked is not None else set())
    intervention = getattr(context.query, "intervention", None)
    treatment = getattr(intervention, "atom", None)
    target = getattr(context.query, "target", None)
    outcome = getattr(target, "atom", target)

    for ref in _probability_refs(formula):
        carries_the_effect = bool(sources) and (
            ref.target.atom == outcome
            and any(g.atom == treatment for g in ref.given))
        wanted = sources if carries_the_effect else {asked}
        role = ("the source domain's conditional" if carries_the_effect
                else "a target-population marginal" if sources
                else "read in the population the question is about")
        if not sources:
            wanted = wanted | {None}
        if ref.population in wanted:
            continue
        raise VerificationError(
            f"the estimand shown to a reader says a factor is read from "
            f"{ref.population!r}; it is {role}, which this problem declares "
            f"as {sorted(str(w) for w in wanted)}",
            step_index=None, rule="identification_formula",
        )


def _probe_the_conjunction(formula, query, context):
    """Put one counterfactual-conjunction estimand to its own probe.

    Written once because two rules ask this of two different formulas: the
    one the chain's terminal step was built with, and the one the envelope
    shows a reader. Returns the probe's verdict and the quantity it was
    about, so a caller's refusal can name it.
    """
    from ..runtime.ctf_identify import CtfEvent

    def _events(events):
        return tuple(
            CtfEvent(
                variable=e.variable,
                subscript=frozenset((s.atom, s.value) for s in e.subscript),
                value=e.value,
            )
            for e in events
        )

    gamma, delta = _events(query.events), _events(query.condition)
    domains = context.theta.domains if context.theta is not None else {}
    # A conditional (IDC*) formula is a P(γ',δ')/P(δ') ratio — probe it with
    # the conditional Monte-Carlo backbone, whose numerator and denominator
    # share one exogenous draw; an unconditional (ID*) one uses the plain
    # P(γ) probe.
    if delta:
        return probe_conditional_counterfactual_formula(
            context.graph, context.bidirected,
            gamma=gamma, delta=delta, formula=formula, domains=domains,
        ), "P(γ|δ)"
    return probe_counterfactual_formula(
        context.graph, context.bidirected,
        gamma=gamma, formula=formula, domains=domains,
    ), "P(γ)"


def verify_identification_formula(result: dict,
                                  context: VerificationContext) -> None:
    """The estimand on the envelope, against the graph it claims to be for.

    ``result["formula"]`` is what a reader is shown as the estimand, what
    the explainer reads to say which variables were adjusted for, and what
    every surface names when it says what was identified. Nothing read it:
    on the twenty-three answers that carry one it could be deleted outright
    and the door said yes.

    The probe that could answer this already existed and was reachable from
    one branch of the query-kind dispatch — a check about the ANSWER,
    standing where a route was chosen. It is put here, outside that
    dispatch, for the same reason the route audits are.

    An effect answer's formula already names the value of Y, where an
    identify query's leaves it open; asked about the other value it returns
    the same number and the probe reads that as a mismatch by 1−p. So the
    binding loop is told the one value this formula is about — and it is
    told through a parameter of its own. The first version said it by
    cutting Y's domain to that value, which is the same dictionary the
    probe samples its models from: Y became a constant, every probability
    and every truth came back 1.0, and the probe returned ``match`` for
    every formula on every answer in the corpus, forged or not.

    Three questions are asked and they do not share a prerequisite.
    Whether this formula is ABOUT this graph needs only the graph, and is
    asked of every answer that carries one. Whether it COMPUTES what was
    asked needs something to compute against, and each kind of question
    supplies its own: an effect question an (X, Y) pair, a counterfactual
    conjunction its γ (and, for a conditional one, its δ). Binding the
    first question to the second's prerequisite is how it came to be
    skipped on a shape whose graph could have answered it.

    The conjunction's arithmetic already existed — and was asked of the
    formula the CHAIN carries, ``derivation[-1].inputs["formula"]``, which
    is not the estimand a reader is shown. So the envelope's could be
    replaced by the constant 0.0 and every door said yes, while the probe
    ran and answered ``match`` about the other copy. It is asked here of
    what the envelope shows. The chain rule still asks it of the chain's:
    they are two claims — that the engine's output computes the truth, and
    that the reader is shown something that does.

    A conjunction whose ``P(γ)`` is zero is rendered as the constant 0,
    and the chain rule skips probing it because the rule above it has just
    confirmed the ID* engine calls the query inconsistent. Nothing warrants
    that about the envelope's copy, so it is not skipped here: the probe
    evaluates a constant like any other formula, and an honest zero matches
    a true zero.

    The third is for the questions that have no X at all. A probability
    question identifies nothing: its estimand is the conditional it names,
    so the two can be compared directly and no model is needed. Read as a
    missing arithmetic check this looks like a gap in the probe; it is
    not, and treating it as one would put a sampled model where a
    comparison belongs.

    THE SECOND QUESTION IS A ONE-POPULATION QUESTION, and that is a third
    prerequisite. A transported answer's estimand takes its conditional
    from a source domain, where the treatment was randomised, and its
    covariate marginal from the target. Read as a formula in one
    population it is a back-door adjustment over a set that does not block
    the back door, and a sampled model rightly disagrees with it — so the
    arithmetic is not asked where the problem declares selection nodes.
    What is asked instead is ``_hold_populations``, which is the question
    the disagreement was really about: not whether the factors compute the
    right number, but whether a reader is told that they come from two
    places. That is asked of every formula, one population or two.

    The condition is read off the PROBLEM, not the route: a program that
    declares selection nodes is a program about more than one population.
    Not off the supplied parameters — a two-source problem with no data at
    all still transports — and not off the answer's route block, which
    would put a question about the envelope back inside a dispatch.

    Returns ``None`` on accept, including when there is no formula to
    check — this rule holds what is written, and whether it must be
    written is the schema's to say.
    """
    written = result.get("formula")
    if not isinstance(written, dict):
        return
    try:
        formula = _DECODE_BY_KIND[written["kind"]](written)
    except (KeyError, TypeError, DerivationSerializationError) as exc:
        raise VerificationError(
            f"the estimand on the envelope is not a formula this system "
            f"can read: {exc}", step_index=None, rule="identification_formula",
        ) from exc

    declared = context.theta.domains if context.theta is not None else ()
    unfit = formula_fits(context.graph, formula, declared)
    if unfit is not None:
        raise VerificationError(
            f"the estimand shown to a reader is not the one this graph and "
            f"this question identify. {unfit.detail}",
            step_index=None, rule="identification_formula",
        )

    _hold_populations(formula, context)

    query = context.query
    if isinstance(query, ProbabilityQuery):
        _hold_the_question_itself(formula, query)
        return

    if isinstance(query, CounterfactualConjunctionQuery):
        probe, quantity = _probe_the_conjunction(formula, query, context)
        if probe.status in _PROBE_REFUSES:
            raise VerificationError(
                f"the estimand shown to a reader does not compute "
                f"{quantity} in models consistent with the graph. "
                f"{probe.detail}",
                step_index=None, rule="identification_formula",
            )
        return

    target = getattr(query, "target", None)
    intervention = getattr(query, "intervention", None)
    if target is None or intervention is None:
        return
    if context.selection_nodes:
        return

    y_atom = getattr(target, "atom", target)
    domains = dict(context.theta.domains if context.theta is not None else {})
    probe = probe_identify_formula(
        context.graph, context.bidirected,
        x=intervention.atom, x_value=intervention.value, y=y_atom,
        given=_conditioned(query),
        formula=formula, domains=domains,
        y_values=(target.value,) if hasattr(target, "value") else None,
    )
    if probe.status in _PROBE_REFUSES:
        raise VerificationError(
            f"the estimand shown to a reader is not the one this graph and "
            f"this question identify. {probe.detail}",
            step_index=None, rule="identification_formula",
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
        # The same answer shape where adjustment fails and the set-valued
        # ID still identifies: the contrast and the interaction are finite
        # differences over the per-corner c-factor plug-in. Their own
        # re-derivation from the recorded corner risks is
        # verify_treatment_box (kernel-called).
        "numeric_joint_general_id_estimate",
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
        # Anderson-Rubin region over a treatment VECTOR — the answer is k
        # conservative intervals rather than a point, so there is no
        # ``numeric_estimate`` to audit and the terminal does metadata +
        # structural licensing only. The region's own re-derivation from the
        # recorded second moments is verify_vector_iv_region (kernel-called),
        # for the reason the two above it are: those are matrices.
        "numeric_anderson_rubin_region",
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

    def _closer_to_null(lo, hi):
        # The interval's nearest approach to the null. An interval spanning
        # the null approaches it exactly, so 0.0 — not "no bound".
        if lo is None or hi is None:
            return None
        if lo > 0:
            return lo
        if hi < 0:
            return hi
        return 0.0

    def _band(point, bound):
        # Themis's cut-points; the paper's rule about which number they read.
        # The bound nearer the null governs whenever there is one, because
        # "is this robust" asks what would take the FINDING away and the
        # point's E-value answers what would move the ESTIMATE to the null.
        #
        # Read off the RECORDED E-values, both already held to the
        # independently recomputed ones above. A band is a step function, so
        # re-deriving it from this transcription's own arithmetic would let
        # a last-bit difference at a cut-point reject a sound block — and
        # what is being audited here is the rule, which is what was wrong.
        if point is None:
            return None, None
        basis = "point" if bound is None else "ci_bound"
        value = point if bound is None else bound
        for cut, name in ((1.5, "fragile"), (2.5, "moderate"),
                          (5.0, "substantial")):
            if value < cut:
                return name, basis
        return "very_robust", basis

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
    ci_bound = _closer_to_null(lo, hi)

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

    # The reading a person acts on, audited like the numbers under it. It was
    # prose until it became a field, and prose is the one part of this block
    # nothing could re-derive — which is how the reading came to be taken off
    # the point estimate for years without a check noticing.
    for name, recomputed in zip(
            ("interpretation_band", "band_basis"),
            _band(block.get("e_value"), block.get("e_value_ci_bound"))):
        if recomputed != block.get(name):
            raise VerificationError(
                f"e_value.{name}: recomputed {recomputed!r}, "
                f"recorded {block.get(name)!r}",
                step_index=None, rule="e_value",
            )


#: Methods whose ``dose_response_curve`` is recomputed from the envelope's own
#: sufficient statistics by that method's numeric verifier, row by row. Membership
#: is a claim that such a verifier exists and covers every row; a method added
#: here without one would lose its curve's only check.
_CURVES_RE_DERIVED_ELSEWHERE = frozenset({
    "exposure_measurement_error_correction",
    "combined_measurement_error_correction",
})


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
    - the reference point's effect is 0 (Y(x_ref) − Y(x_ref) = 0) and its
      interval is [0, 0] — a level contrasted with itself is not an
      estimate, so there is no width for one to have;
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

    So is a curve from a method in :data:`_CURVES_RE_DERIVED_ELSEWHERE`. This
    audit exists BECAUSE a black-box fit cannot be recomputed, and it encodes
    the sampled-continuous-treatment convention — every row matching a sampling
    point, the reference carried as a row whose effect is zero. A curve over a
    polytomous exposure's declared states has neither: there are no sampling
    points, and the reference is omitted rather than carried, because a level
    contrasted with itself is not an estimate. Running this audit on one would
    reject an honest curve for failing a convention it does not share — and it
    would buy nothing, since those curves are re-derived row by row from the
    recorded sufficient statistics, which is strictly stronger than any
    construction invariant.
    """
    import math

    curve = estimate.get("dose_response_curve")
    if curve is None:
        return
    if estimate.get("method") in _CURVES_RE_DERIVED_ELSEWHERE:
        return

    def _fail(msg: str) -> NoReturn:
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
    # And its interval is not a narrow one — it is no interval at all. A
    # dose contrasted with itself has no sampling variability to report, so
    # [0, 0] is the whole of what this row can say, and it is what the
    # producer writes. Asking only that the interval BRACKET zero is what
    # one asks of an ESTIMATE that came out null, and it left both endpoints
    # of this row free to be anything straddling zero — free with nothing
    # else watching, because the budget that prices every other row is
    # computed from a half-width and this row's is zero.
    rlo, rhi = ref_pt.get("ci_lower"), ref_pt.get("ci_upper")
    if (rlo is not None or rhi is not None) \
            and not (_eq(rlo, 0.0) and _eq(rhi, 0.0)):
        _fail(
            f"reference point interval is [{rlo}, {rhi}]; a level contrasted "
            "with itself has none — the effect is 0 by construction and so "
            "is the width"
        )


_MEDIATION_TOL = 1e-6


#: The verifier's own transcription of the enumeration cap and the two
#: withholding species (``themis.estimation.treatment_box``). Copied rather
#: than imported for the standing reason: importing the producer's
#: vocabulary makes the audit a check of the producer against itself.
_JOINT_CORNER_CAP = 5
_JOINT_UNAVAILABLE_KINDS = frozenset({"corner_unsupported", "order_above_cap"})
#: The two answers are sums of at most 2^K corners, so an absolute tolerance
#: is the right shape and this is a generous one for float64 summation at
#: K ≤ 5. It covers a continuous outcome's scale as well, because what is
#: allowed for is summation order rather than magnitude: the corners are the
#: same standardized values the estimator itself differenced.
_JOINT_CORNER_TOL = 1e-9


def verify_treatment_box(estimate: dict) -> None:
    """Re-derive a joint answer from the treatment box it records.

    Both numbers a joint answer reports are finite differences over the box
    — the contrast is all-hi minus all-lo, the K-way interaction is the
    alternating sum over all 2^K corners — and both derivation terminals
    that produce one do metadata + structural licensing only. So the box is
    recorded, and the audit here is a re-derivation rather than a
    re-reading, written from the definition in this module's own
    transcription.

    What that catches which the terminals cannot: a contrast or an
    interaction that is internally consistent (a number inside its own CI)
    but does not follow from the corners the same result reports.

    Asked of any answer that CARRIES a box, rather than of the one method
    that happened to record one. Two estimators reach the same quantity by
    different roads and emit the same block, and they had opposite fates:
    the general-ID plug-in kept its corners and had both numbers
    re-derived, while the joint back-door g-formula computed every corner,
    took its two differences and dropped the box — leaving a joint contrast
    that could be replaced with any number at all. Nothing in this function
    was ever about general-ID; only its selector was.

    Three further things the recorded box has to say about itself:

    - the corners are distinct, and each names every treatment — a repeated
      or short cell would let one corner stand in for two in the sum;
    - a corner is held to the unit interval exactly where the envelope
      names the outcome level the risks are OF, since that is the one
      statement on it that makes them probabilities. A fitted link is not
      that statement — a caller may name a logistic form over a column that
      is not binary — and on a mean-valued outcome the bound would refuse an
      honest answer;
    - the box is complete exactly when an interaction is reported, and when
      it is not, the species says which way it went missing and the cells
      or the cap behind it agree with what is actually there.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    ne = estimate
    treatments = ne.get("treatments")
    if not isinstance(treatments, list) or len(treatments) < 2:
        raise VerificationError(
            "a joint answer must name at least two treatments; "
            f"got {treatments!r}",
        )
    k = len(treatments)
    joint = ne.get("joint_effect")
    if not isinstance(joint, dict):
        raise VerificationError(
            "a joint answer must carry a joint_effect block",
        )
    recorded = ne.get("corner_risks")
    if not isinstance(recorded, list) or not recorded:
        raise VerificationError(
            "a joint answer must carry corner_risks — without them neither "
            "reported number can be re-derived",
        )
    # Naming the outcome level is what makes these probabilities rather
    # than means, so it is what the range is asked about. Absent it a corner
    # is a standardized value on the outcome's own scale, with no range to
    # be held to.
    binary = ne.get("outcome_high") is not None

    risks: dict[tuple, float] = {}
    for entry in recorded:
        cell = entry.get("cell") if isinstance(entry, dict) else None
        risk = entry.get("risk") if isinstance(entry, dict) else None
        if not isinstance(cell, dict) or sorted(cell) != sorted(treatments):
            raise VerificationError(
                f"corner_risks cell {cell!r} must give a value for every "
                f"treatment in {treatments!r}",
            )
        if not isinstance(risk, (int, float)) or isinstance(risk, bool):
            raise VerificationError(
                f"corner_risks risk at {cell!r} must be a number; "
                f"got {risk!r}",
            )
        if binary and not (0.0 <= float(risk) <= 1.0):
            raise VerificationError(
                f"corner_risks risk at {cell!r} must be a probability, since "
                f"this answer reports the risk of "
                f"{ne.get('outcome_high')!r}; got {risk!r}",
            )
        key = tuple(cell[t] for t in treatments)
        if key in risks:
            raise VerificationError(
                f"corner_risks names the corner {cell!r} more than once",
            )
        risks[key] = float(risk)

    levels: list[set] = [set() for _ in treatments]
    for key in risks:
        for i, value in enumerate(key):
            levels[i].add(value)
    if any(len(s) != 2 for s in levels):
        raise VerificationError(
            "corner_risks must range over both levels of every treatment; "
            f"got {[sorted(map(str, s)) for s in levels]}",
        )
    # The contrast's own two corners, read off the block that claims them
    # rather than off an assumption about which level is "high".
    treated, control = joint.get("treated"), joint.get("control")
    if not isinstance(treated, dict) or not isinstance(control, dict):
        raise VerificationError(
            "joint_effect must name the treated and control cells it was "
            "taken between",
        )
    try:
        hi_key = tuple(treated[t] for t in treatments)
        lo_key = tuple(control[t] for t in treatments)
    except KeyError as exc:
        raise VerificationError(
            f"joint_effect cells must give a value for every treatment; "
            f"{exc} is missing",
        ) from None
    for key, which in ((hi_key, "treated"), (lo_key, "control")):
        if key not in risks:
            raise VerificationError(
                f"joint_effect's {which} cell is not among the recorded "
                "corner_risks, so the contrast rests on nothing",
            )
    # The control cell is what tells a corner's sign in the alternating sum
    # below, so a treatment held at the same level in both cells would make
    # the two corners the contrast is between the same corner.
    if any(h == lo for h, lo in zip(hi_key, lo_key)):
        raise VerificationError(
            "joint_effect's treated and control cells must differ in every "
            f"treatment; got {treated!r} against {control!r}",
        )
    redone = risks[hi_key] - risks[lo_key]
    claimed = joint.get("point")
    if not isinstance(claimed, (int, float)) or isinstance(claimed, bool) \
            or abs(float(claimed) - redone) > _JOINT_CORNER_TOL:
        raise VerificationError(
            f"joint_effect.point {claimed!r} does not equal the recorded "
            f"corners' difference {redone!r}",
        )

    interaction = ne.get("interaction")
    unavailable = ne.get("interaction_unavailable")
    if (interaction is None) == (unavailable is None):
        raise VerificationError(
            "a joint answer carries exactly one of interaction / "
            "interaction_unavailable — one says the number, the other says "
            "why there is none",
        )
    if interaction is not None:
        _joint_interaction_holds(interaction, risks, lo_key, k)
    elif unavailable is not None:
        _joint_interaction_withheld(unavailable, risks, treatments, k)


def _joint_interaction_holds(
    interaction: dict, risks: dict[tuple, float], lo_key: tuple, k: int,
) -> None:
    """The K-way interaction, re-derived from the box rather than read.

    Its own sign rule, written from the definition — a corner's sign is the
    parity of how many treatments sit at their CONTROL level — so a producer
    that got the parity backwards is caught rather than mirrored.
    """
    if len(risks) != 2 ** k:
        raise VerificationError(
            f"an order-{k} interaction needs all {2 ** k} corners; "
            f"{len(risks)} are recorded",
        )
    total = 0.0
    for key, risk in risks.items():
        n_lo = sum(1 for i, value in enumerate(key) if value == lo_key[i])
        total += (-1.0 if n_lo % 2 else 1.0) * risk
    got = interaction.get("point")
    if not isinstance(got, (int, float)) or isinstance(got, bool) \
            or abs(float(got) - total) > _JOINT_CORNER_TOL:
        raise VerificationError(
            f"interaction.point {got!r} does not equal the alternating "
            f"sum {total!r} over the recorded corners",
        )
    if interaction.get("order") != k:
        raise VerificationError(
            f"interaction.order must be the number of treatments ({k}); "
            f"got {interaction.get('order')!r}",
        )


def _joint_interaction_withheld(
    unavailable: dict, risks: dict[tuple, float],
    treatments: list | tuple, k: int,
) -> None:
    """Why there is no interaction, held to the box the same result reports.

    Both species make a checkable claim, and which one is claimed decides
    what checks it: an order above the cap is a claim about K, which is on
    this block, and an unsupported corner is a claim about the box, which is
    beside it.
    """
    kind = unavailable.get("kind")
    if kind not in _JOINT_UNAVAILABLE_KINDS:
        raise VerificationError(
            f"interaction_unavailable.kind must be one of "
            f"{sorted(_JOINT_UNAVAILABLE_KINDS)}; got {kind!r}",
        )
    if unavailable.get("order") != k:
        raise VerificationError(
            f"interaction_unavailable.order must be the number of "
            f"treatments ({k}); got {unavailable.get('order')!r}",
        )
    if kind == "order_above_cap":
        if k <= _JOINT_CORNER_CAP:
            raise VerificationError(
                f"interaction_unavailable claims order {k} is above the "
                f"cap, but {_JOINT_CORNER_CAP} corners' worth of treatments "
                "is within it",
            )
        return
    # corner_unsupported: the box WAS walked, so the missing corners are
    # exactly the ones the block names, and there is at least one.
    missing = 2 ** k - len(risks)
    named = unavailable.get("unsupported_cells")
    if not isinstance(named, list) or not named:
        raise VerificationError(
            "interaction_unavailable of kind corner_unsupported must name "
            "the corners it could not stand on",
        )
    if len(named) != missing:
        raise VerificationError(
            f"interaction_unavailable names {len(named)} unsupported "
            f"corner(s) but {missing} of the {2 ** k} are missing from "
            "corner_risks",
        )
    for cell in named:
        if not isinstance(cell, dict) or sorted(cell) != sorted(treatments):
            raise VerificationError(
                f"unsupported cell {cell!r} must give a value for every "
                f"treatment in {treatments!r}",
            )
        if tuple(cell[t] for t in treatments) in risks:
            raise VerificationError(
                f"unsupported cell {cell!r} is recorded in corner_risks, so "
                "it was evaluable after all",
            )


#: Both re-derivations below are closed-form sums of a handful of recorded
#: numbers, so what separates a real disagreement from float noise is small.
_FRONTDOOR_EMPIRICAL_TOL = 1e-6


def verify_frontdoor_empirical_numeric(estimate: dict) -> None:
    """Re-derive a front-door point taken with the sample's own conditional.

    The derivation terminal audits metadata and structural licensing: that
    a front-door criterion was witnessed, that the mediators match it. It
    cannot say whether the number followed from anything, because the
    enumerating route's arms are sums over strata no envelope carries.
    This route's arms are two means, and they ARE carried — so the point
    stops being a number the reader has to take on trust.

    Two checks, and the second exists only on the linear form:

    The contrast is a difference of the two standardized arms. That is the
    estimand's definition and holds whatever the outcome model was, so it
    is checked for both.

    On a linear outcome model the arms are more than that. Writing the fit
    as ``a + b_x·x + b_m'm``, the inner average over x' adds ``b_x·P(X=1)``
    to every row alike and the intercept to every row alike, so both cancel
    from the difference and

        point = b_m' · (M̄ | X=1  −  M̄ | X=0)

    — the front-door product rule with the two halves it is a product of
    both recorded. That is an independent recomputation and not a
    re-reading: a point can sit inside its own interval, agree with its own
    two arms, and still not follow from the coefficients and the mediator
    shift the same result reports.

    On a logit outcome model there is no such identity to check. The
    standardized mean of a non-linear link does not collapse to a function
    of its coefficients, so re-deriving the arms would mean holding the
    rows, which the verifier does not. The difference identity and the fact
    that each arm is a probability are what can be said, and pretending to
    more would be the audit agreeing with itself.

    ``estimate`` is the full ``numeric_estimate`` dict.
    """
    method = estimate.get("method")
    block = estimate.get("front_door_empirical")
    if not isinstance(block, dict):
        raise VerificationError(
            f"a {method!r} estimate must carry a front_door_empirical block "
            "— without it the point rests on nothing the envelope holds",
        )
    arms = {}
    for key in ("arm_treated", "arm_control", "treatment_prevalence"):
        value = block.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise VerificationError(
                f"front_door_empirical.{key} must be a number; got {value!r}",
            )
        arms[key] = float(value)
    prevalence = arms["treatment_prevalence"]
    if not 0.0 < prevalence < 1.0:
        # Both arms weight the inner sum, and both are read off rows. A
        # prevalence at either end says one of them had none.
        raise VerificationError(
            "front_door_empirical.treatment_prevalence must be strictly "
            f"between 0 and 1; got {prevalence!r}",
        )

    point = estimate.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise VerificationError(
            f"a {method!r} estimate must carry a numeric point; "
            f"got {point!r}",
        )
    contrast = arms["arm_treated"] - arms["arm_control"]
    if abs(contrast - float(point)) > _FRONTDOOR_EMPIRICAL_TOL * (
            1 + abs(contrast)):
        raise VerificationError(
            f"front-door point {float(point)!r} is not the difference of the "
            f"two standardized arms it records ({arms['arm_treated']!r} − "
            f"{arms['arm_control']!r} = {contrast!r})",
        )

    shift = block.get("mediator_shift")
    coefficients = block.get("outcome_coefficients")
    if not isinstance(shift, list) or not shift:
        raise VerificationError(
            "front_door_empirical.mediator_shift must be a non-empty list — "
            "a front door with no mediator term is not one",
        )
    if not isinstance(coefficients, list) or len(coefficients) != len(shift) + 1:
        raise VerificationError(
            "front_door_empirical.outcome_coefficients must give the "
            f"treatment's coefficient and one per mediator term ({len(shift)}"
            f" + 1); got {coefficients!r}",
        )
    for name, values in (("mediator_shift", shift),
                         ("outcome_coefficients", coefficients)):
        for value in values:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise VerificationError(
                    f"front_door_empirical.{name} must hold numbers; "
                    f"got {value!r}",
                )

    if method == "frontdoor_empirical_logistic":
        for key in ("arm_treated", "arm_control"):
            if not 0.0 <= arms[key] <= 1.0:
                raise VerificationError(
                    f"front_door_empirical.{key} is a standardized "
                    f"probability under a logit outcome model, so it must lie "
                    f"in [0, 1]; got {arms[key]!r}",
                )
        return

    redone = sum(float(b) * float(s)
                 for b, s in zip(coefficients[1:], shift))
    if abs(redone - float(point)) > _FRONTDOOR_EMPIRICAL_TOL * (
            1 + abs(redone)):
        raise VerificationError(
            f"front-door point {float(point)!r} does not follow from the "
            f"outcome coefficients and the mediator shift this result "
            f"records; those give {redone!r}",
        )


def verify_mediation_numeric(estimate: dict) -> None:
    """Audit the numeric answer blocks riding on a mediation structural
    result and reject on violation.

    Mediation stays ``structurally_solved`` (routed to
    verify_effect_structural, which checks only the identify_via_mediation
    terminal), so the numbers attached to it — the Imai NDE/NIE
    decomposition and the two four-way splits — otherwise ship with no
    numeric audit at all: today a tampered ``err_cde`` or ``prop_mediated``
    passes ``themis.verify`` untouched.

    Four blocks, two levels of check:

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
    - ``controlled_direct_effect`` (STRONG on the linear path, INVARIANTS on
      the logit one): the curve the ``cde_*`` route reports where the
      natural effects did not survive the graph. On a linear outcome the
      covariate terms cancel from the treated-minus-control difference, so
      CDE(m*) = θ_x + θ_xm·m* re-derives every level from two recorded
      coefficients; on the logit path standardization is not collapsible and
      the check is that each contrast equals the two standardized risks it
      was made from. Both paths also hold ``varies_with_level`` to what the
      levels actually say, since that flag is what a reader is shown in
      place of comparing the rows themselves.

    ``estimate`` is the full ``numeric_estimate`` dict; each block is
    audited only when present.
    """
    import math

    def _fail(msg: str, rule: str) -> NoReturn:
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
            # gamma_j * m* exactly (the covariates cancel in the difference) —
            # re-derived here from the SAME recorded coefficients, independent
            # of the estimator (a self-consistent forgery of a cde point is
            # caught). On the joint LOGIT path CDE is a plug-in over the
            # covariates and is not re-derivable here (construction ceiling).
            #
            # m* IS READ OFF THE ROW. It used to be written in as 0 and 1,
            # which made this an audit of a block other than the one in front
            # of it: the levels are the block's own claim about where it held
            # the mediators, and a row relabelled to m*=7 went on satisfying a
            # check about m*=0. The standalone curve thirty lines below has
            # always read its own level; the general form is the same one, and
            # it is the same form for every m*.
            cde_blk = dec.get("cde")
            if cde_blk is not None:
                sum_g = sum(float(gammas[name]) for name in betas)
                for side in ("reference_control", "reference_treated"):
                    row = cde_blk.get(side)
                    if row is None:
                        continue
                    at = row.get("mediator_level")
                    if not isinstance(at, (int, float)) or isinstance(at, bool):
                        _fail(
                            f"decomposition.cde.{side} reports a controlled "
                            f"direct effect and names no mediator level to "
                            f"have held them at; got {at!r}",
                            "decomposition",
                        )
                    _close(float(beta_x) + sum_g * float(at), row["point"],
                           f"decomposition.cde.{side}"
                           f"[m*={at}]==beta_x+m*sum_gamma", "decomposition")
        _close(nde + nie, te, "decomposition.nde+nie==te", "decomposition")
        pm = dec.get("proportion_mediated")
        if pm is not None and abs(te) > _MEDIATION_TOL:
            _close(nie / te, pm["point"], "decomposition.proportion_mediated",
                   "decomposition")

    # ---- controlled_direct_effect: the curve, re-derived --------------
    # STRONG on the linear path and construction-level on the logit one,
    # for the reason the NDE/NIE block above gives for the same split: a
    # standardization over covariates is collapsible in one case and not in
    # the other, and claiming otherwise would be the audit asserting an
    # identity that does not hold.
    cde = estimate.get("controlled_direct_effect")
    if cde is not None:
        rows = cde.get("levels") or []
        if not rows:
            _fail("controlled_direct_effect carries no levels",
                  "controlled_direct_effect")
        suff = cde.get("sufficient_statistics") or {}
        coefs = suff.get("outcome_coefficients") or []
        names = suff.get("design_columns") or []
        # The block names its own leading columns; reading the product's
        # position off that rather than off a constant is what keeps this
        # audit honest if the design ever gains a term before it.
        product_at = (names.index("treatment_x_mediator")
                      if "treatment_x_mediator" in names else None)
        treatment_at = (names.index("treatment")
                        if "treatment" in names else None)
        # The two numbers the linear curve is a closed form of, or nothing.
        # Bound here rather than re-tested per level, so what the loop below
        # branches on is whether the strong re-derivation is AVAILABLE — one
        # question — instead of restating which method produced the block.
        theta: tuple[float, float] | None = None
        if estimate.get("method") == "cde_linear":
            if (product_at is None or treatment_at is None
                    or len(coefs) <= max(product_at, treatment_at)):
                _fail(
                    "controlled_direct_effect: the linear curve is a closed "
                    "form of the treatment and exposure-mediator "
                    "coefficients, and the recorded design does not name "
                    "where they are",
                    "controlled_direct_effect",
                )
            theta = (float(coefs[treatment_at]), float(coefs[product_at]))
        points = []
        for i, row in enumerate(rows):
            level = row.get("mediator_level")
            point = row.get("point")
            # Every contrast against the two quantities it is a difference
            # of. A tamper of one number stops agreeing with its own parts.
            _close(float(row["risk_treated"]) - float(row["risk_control"]),
                   point,
                   f"controlled_direct_effect.levels[{i}]"
                   ".point==risk_treated-risk_control",
                   "controlled_direct_effect")
            if theta is not None:
                # The covariate terms cancel from the treated-minus-control
                # difference, so the whole curve is two numbers.
                _close(theta[0] + theta[1] * float(level), point,
                       f"controlled_direct_effect.levels[{i}]"
                       ".point==theta_x+theta_xm*level",
                       "controlled_direct_effect")
            lo, hi = row.get("ci_lower"), row.get("ci_upper")
            if lo is not None and hi is not None and not lo <= point <= hi:
                _fail(
                    f"controlled_direct_effect.levels[{i}]: point {point} "
                    f"outside its own interval [{lo}, {hi}]",
                    "controlled_direct_effect",
                )
            points.append(float(point))
        # The flag a reader is shown instead of comparing the rows
        # themselves, so it is held to what the rows say.
        varies = len(points) > 1 and max(points) != min(points)
        if bool(cde.get("varies_with_level")) != varies:
            _fail(
                f"controlled_direct_effect.varies_with_level says "
                f"{cde.get('varies_with_level')} and the levels say {varies}",
                "controlled_direct_effect",
            )


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
    residualised second moments Z'Z / Z'x / Z'y / xx / xy / yy). The joint
    first-stage F comes out of the same moments — the share of the treatment
    the q instruments explain against what is left, over the degrees of
    freedom the intercept, the exogenous block and the instruments leave —
    and is held to the reported one, because that number is what a
    weak-instrument verdict is read off and nothing re-derived it. When the block
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

    def _fail(msg: str) -> NoReturn:
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

    # The joint first stage, from the same moments. On this path the F is a
    # q-restriction test — how much of the treatment the instruments
    # together explain, against what is left, over the degrees of freedom
    # remaining after the intercept, the exogenous block and the
    # instruments. It is the number a weak-instrument verdict is read off,
    # it was recorded on the envelope and re-derived by nothing, and the
    # moments to do it with were already here.
    claimed_f = estimate.get("first_stage_f_stat")
    if claimed_f is not None:
        n_exog = int(suff.get("n_exog", 0))
        f_dof = n - n_exog - q - 1
        residual = xx - x_pz_x
        if f_dof < 1 or residual <= 0:
            _fail(
                f"first_stage_f_stat is reported and the recorded moments "
                f"support no F (residual dof {f_dof}, residual variance "
                f"{residual})"
            )
        joint_f = (x_pz_x / q) / (residual / f_dof)
        if abs(joint_f - float(claimed_f)) > _IV_OVERID_TOL * (1 + abs(joint_f)):
            _fail(
                f"first_stage_f_stat mismatch — re-derived {joint_f}, "
                f"recorded {claimed_f}; the weak-instrument verdict a reader "
                f"is shown is not the one these moments support"
            )

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
            if recomputed is None or claimed is None:
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
        # An open end of the set is a None endpoint, so both ends of a
        # rebuilt segment are optional — the first append happens to be
        # (None, float) and the last (float, None).
        rebuilt: list[tuple[float | None, float | None]] = []
        member = tails_in
        prev: float | None = None
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


_AR_REGION_TOL = 1e-6


def verify_vector_iv_region(block: dict) -> None:
    """Re-derive an Anderson-Rubin confidence REGION over a treatment vector —
    the inverted quadratic, the region's shape, every coordinate projection,
    the centre and the 2SLS point — from the recorded residualised second
    moments, and reject on mismatch.

    A SECOND, independent transcription of the inversion. With ``W`` partialled
    out and ``P_.. = S_z.'(Z'Z)⁻¹S_z.``, accepting ``AR(b) <= F(q, m)`` at level
    ``1-α`` is ``b'A b − 2b'B + C <= 0`` with ``κ = q·F(q, m)``, ``G = m + κ``::

        A = G·P_xx − κ·XX      B = G·P_xy − κ·xy      C = G·P_yy − κ·yy

    and ``m = n − |W| − q − 1``. The classification is re-derived here in the
    EIGENBASIS of A rather than by the producer's case split: rotating B into
    it makes the quadratic separable, so the minimum is ``C − Σ_{λi>0} B̃i²/λi``
    and each branch is a statement about one axis — negative λ means the
    quadratic falls without bound along that eigenvector, a zero λ with B̃i ≠ 0
    means it is linear and non-constant there, a zero λ with B̃i = 0 means it is
    flat and the region is a cylinder. A bug in either arrangement is visible
    from the other.

    The projections are checked twice over, by two formulas that share no
    algebra. The general one minimises over the other coordinates (a Schur
    complement, solved with the verifier's own quadratic classifier), and the
    endpoints it produces are then confirmed against the QUADRATIC ITSELF: at
    the minimising completion of a finite endpoint the form must evaluate to
    zero, which is what "this is where the region ends" means and which no
    classification can fake. Where the region is an ellipsoid the endpoint is
    checked a third time against the support function
    ``μ_j ± sqrt(r·(A⁻¹)_jj)``, and the theorem tying the two vocabularies —
    the region is bounded iff every projection is — is asserted in both
    directions, so a tampered ``shape`` and a tampered ``projections`` each
    fail on the other.

    Never imports the producer's module and never touches the raw data. A block
    that is not an ``anderson_rubin_region`` is a no-op.
    """
    import math

    import numpy as np
    from scipy.stats import f as _f_dist

    from .rules import _ar_solve_set_verifier

    if not isinstance(block, dict) or block.get("kind") != "anderson_rubin_region":
        return

    def _fail(msg: str) -> NoReturn:
        raise VerificationError(
            f"vector_iv_region: {msg}", step_index=None,
            rule="vector_iv_region",
        )

    if block.get("method") != "iv_anderson_rubin_region":
        _fail(f"unexpected method {block.get('method')!r}")
    region = block.get("region")
    if not isinstance(region, dict):
        _fail("block carries no region")
    suff = block.get("sufficient_statistics")
    if not isinstance(suff, dict):
        _fail("block carries no sufficient_statistics — a shape with nothing "
              "behind it is a claim no reader can check")

    try:
        q = int(suff["q"]); n = int(suff["n"]); n_exog = int(suff["n_exog"])
        names = [str(t) for t in suff["treatments"]]
        k = len(names)
        zz = np.asarray(suff["zz"], dtype=float).reshape(q, q)
        zx = np.asarray(suff["zx"], dtype=float).reshape(q, k)
        zy = np.asarray(suff["zy"], dtype=float).reshape(q)
        xx = np.asarray(suff["xx"], dtype=float).reshape(k, k)
        xy = np.asarray(suff["xy"], dtype=float).reshape(k)
        yy = float(suff["yy"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    if k < 2:
        _fail(f"a region is for a treatment VECTOR; the moments name {k}")
    for where, said in (("region", region.get("treatments")),
                        ("block", block.get("treatments"))):
        if [str(t) for t in (said or ())] != names:
            _fail(f"{where}.treatments {said!r} is not the order the moments "
                  f"are in ({names}); every coordinate below would then be "
                  f"about a different coefficient")

    m_denom = n - n_exog - q - 1
    if m_denom < 1:
        _fail("residual df m = n - |W| - q - 1 < 1; the AR test is undefined")
    if int(region.get("dof_num", -1)) != q:
        _fail(f"dof_num mismatch — q = {q}, recorded {region.get('dof_num')}")
    if int(region.get("dof_denom", -1)) != m_denom:
        _fail(f"dof_denom mismatch — m = {m_denom}, recorded "
              f"{region.get('dof_denom')}")

    try:
        ci_level = float(region["ci_level"])
    except (KeyError, TypeError, ValueError):
        _fail("region missing / non-numeric ci_level")
    if not (0.0 < ci_level < 1.0):
        _fail(f"ci_level must be in (0, 1); got {ci_level}")

    kappa = float(q) * float(_f_dist.ppf(ci_level, q, m_denom))
    claimed_kappa = region.get("kappa")
    if claimed_kappa is None or abs(float(claimed_kappa) - kappa) > \
            _AR_REGION_TOL * (1 + abs(kappa)):
        _fail(f"kappa mismatch — re-derived q·F(q,m) = {kappa}, recorded "
              f"{claimed_kappa}")

    try:
        zz_inv = np.linalg.inv(zz)
    except np.linalg.LinAlgError:
        _fail("recorded Z'Z is singular — cannot re-derive")
    p_xx = zx.T @ zz_inv @ zx
    p_xy = zx.T @ zz_inv @ zy
    p_yy = float(zy @ zz_inv @ zy)

    g = m_denom + kappa
    a_re = 0.5 * ((g * p_xx - kappa * xx) + (g * p_xx - kappa * xx).T)
    b_re = g * p_xy - kappa * xy
    c_re = g * p_yy - kappa * yy

    try:
        a_rec = np.asarray(region["a_matrix"], dtype=float).reshape(k, k)
        b_rec = np.asarray(region["b_vector"], dtype=float).reshape(k)
        c_rec = float(region["c_scalar"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed recorded quadratic: {exc}")

    a_scale = float(np.abs(a_re).max()) + 1.0
    if float(np.abs(a_rec - a_rec.T).max()) > _AR_REGION_TOL * a_scale:
        _fail("recorded a_matrix is not symmetric; the region it defines is "
              "not the one its eigenvalues describe")
    if float(np.abs(a_rec - a_re).max()) > _AR_REGION_TOL * a_scale:
        _fail(f"a_matrix mismatch — re-derived {a_re.tolist()}, recorded "
              f"{a_rec.tolist()}")
    b_scale = float(np.abs(b_re).max()) + 1.0
    if float(np.abs(b_rec - b_re).max()) > _AR_REGION_TOL * b_scale:
        _fail(f"b_vector mismatch — re-derived {b_re.tolist()}, recorded "
              f"{b_rec.tolist()}")
    if abs(c_rec - c_re) > _AR_REGION_TOL * (abs(c_re) + 1.0):
        _fail(f"c_scalar mismatch — re-derived {c_re}, recorded {c_rec}")

    def _quadratic(beta) -> float:
        v = np.asarray(beta, dtype=float).reshape(k)
        return float(v @ a_re @ v) - 2.0 * float(b_re @ v) + c_re

    # --- the shape, re-derived in the eigenbasis ------------------------------
    rtol = 1e-9
    w_eig, v_eig = np.linalg.eigh(a_re)
    e_tol = rtol * max(float(np.max(np.abs(w_eig))), 1.0)
    b_rot = v_eig.T @ b_re
    b_tol = e_tol * max(1.0, float(np.abs(b_re).max()) + 1.0)
    val_tol = rtol * (abs(c_re) + float(np.abs(b_re).sum()) + 1.0)

    positive = w_eig > e_tol
    flat = np.abs(w_eig) <= e_tol
    centre_re = None
    if (w_eig < -e_tol).any():
        shape_re = "unbounded"
    elif (np.abs(b_rot[flat]) > b_tol).any():
        shape_re = "unbounded"
    elif flat.all():
        shape_re = "whole_space" if c_re <= val_tol else "empty"
    else:
        minimum = c_re - float(
            np.sum(b_rot[positive] ** 2 / w_eig[positive]))
        if minimum > val_tol:
            shape_re = "empty"
        elif flat.any():
            shape_re = "unbounded"
        else:
            shape_re = "bounded"
            centre_re = v_eig @ (b_rot / w_eig)

    if region.get("shape") != shape_re:
        _fail(f"shape mismatch — re-classified {shape_re!r}, recorded "
              f"{region.get('shape')!r}")
    if bool(region.get("bounded")) != (shape_re == "bounded"):
        _fail(f"bounded={region.get('bounded')!r} contradicts shape "
              f"{shape_re!r}")

    claimed_centre = region.get("center")
    if (claimed_centre is None) != (centre_re is None):
        _fail(f"centre presence mismatch — a centre exists iff the quadratic "
              f"is positive definite; re-derived "
              f"{'one' if centre_re is not None else 'none'}, recorded "
              f"{claimed_centre!r}")
    if centre_re is not None:
        got = np.asarray(claimed_centre, dtype=float).reshape(k)
        if float(np.abs(a_re @ got - b_re).max()) > _AR_REGION_TOL * b_scale:
            _fail(f"centre {got.tolist()} does not solve A·centre = B")

    claimed_point = region.get("point")
    if claimed_point is not None:
        pt = np.asarray(claimed_point, dtype=float).reshape(k)
        residual = p_xx @ pt - p_xy
        if float(np.abs(residual).max()) > _AR_REGION_TOL * (
                float(np.abs(p_xy).max()) + 1.0):
            _fail(f"2SLS point {pt.tolist()} does not solve P_xx·β = P_xy")

    # --- the projections, and the theorem that ties them to the shape --------
    projections = region.get("projections")
    if not isinstance(projections, list) or len(projections) != k:
        _fail(f"expected one projection per treatment ({k}); recorded "
              f"{projections!r}")

    for j, proj in enumerate(projections):
        if not isinstance(proj, dict):
            _fail(f"projection {j} is not an object")
        if proj.get("treatment") != names[j]:
            _fail(f"projection {j} is labelled {proj.get('treatment')!r} and "
                  f"coordinate {j} of the moments is {names[j]!r}")

        rest = [i for i in range(k) if i != j]
        a_ss = a_re[np.ix_(rest, rest)]
        a_sj = a_re[np.ix_(rest, [j])].reshape(-1)
        b_s = b_re[rest]
        w_ss, v_ss = np.linalg.eigh(a_ss)
        s_tol = rtol * max(float(np.max(np.abs(w_ss))), 1.0)
        inner_free = False
        inv_ss = None
        if (w_ss < -s_tol).any():
            inner_free = True
        else:
            null = np.abs(w_ss) <= s_tol
            if null.any():
                span_tol = s_tol * max(
                    1.0, float(np.abs(a_sj).max()),
                    float(np.abs(b_s).max()) + 1.0)
                nulls = v_ss[:, null]
                if (float(np.abs(nulls.T @ a_sj).max()) > span_tol
                        or float(np.abs(nulls.T @ b_s).max()) > span_tol):
                    inner_free = True
                else:
                    inv_ss = np.linalg.pinv(a_ss)
            else:
                inv_ss = np.linalg.inv(a_ss)

        if inner_free:
            # The inner minimum is -inf for all but at most one value of this
            # coordinate, so every value survives.
            kind_re, lower_re, upper_re = "whole_line", None, None
        else:
            alpha = float(a_re[j, j]) - float(a_sj @ inv_ss @ a_sj)
            gamma = float(b_re[j]) - float(a_sj @ inv_ss @ b_s)
            delta = c_re - float(b_s @ inv_ss @ b_s)
            scale = abs(alpha) + abs(gamma) + abs(delta) + 1.0
            kind_re, lower_re, upper_re = _ar_solve_set_verifier(
                alpha, -2.0 * gamma, delta, atol=rtol * scale)

        if proj.get("kind") != kind_re:
            _fail(f"projection onto {names[j]!r}: re-projected {kind_re!r}, "
                  f"recorded {proj.get('kind')!r}")
        for side, recomputed in (("lower", lower_re), ("upper", upper_re)):
            claimed = proj.get(side)
            if recomputed is None and claimed is None:
                continue
            if recomputed is None or claimed is None:
                _fail(f"projection onto {names[j]!r}: {side} presence "
                      f"mismatch — re-projected {recomputed}, recorded "
                      f"{claimed}")
            if abs(recomputed - float(claimed)) > _AR_REGION_TOL * (
                    1 + abs(recomputed)):
                _fail(f"projection onto {names[j]!r}: {side} mismatch — "
                      f"re-projected {recomputed}, recorded {claimed}")

            # And the endpoint against the quadratic itself. At a finite end
            # of a projection the region is touched, so the form evaluates to
            # zero at the completion that minimises it — a check that shares
            # no algebra with the classification above.
            if inv_ss is not None:
                witness = np.zeros(k)
                witness[j] = float(claimed)
                witness[rest] = inv_ss @ (b_s - float(claimed) * a_sj)
                touched = _quadratic(witness)
                if abs(touched) > 1e-6 * (abs(c_re) + abs(float(claimed)) + 1.0):
                    _fail(f"projection onto {names[j]!r}: the recorded {side} "
                          f"endpoint {claimed} does not touch the region — "
                          f"the quadratic is {touched} there, not 0")

    kinds = [p.get("kind") for p in projections]
    if (shape_re == "bounded") != all(kind == "bounded" for kind in kinds):
        _fail(f"shape {shape_re!r} contradicts the projections {kinds!r}: a "
              f"region is bounded exactly when every coordinate of it is")

    # The ellipsoid's own support function, which the Schur route never uses.
    if shape_re == "bounded":
        a_inv = np.linalg.inv(a_re)
        radius = float(b_re @ a_inv @ b_re) - c_re
        if radius < -val_tol:
            _fail(f"bounded region with a negative squared radius {radius}")
        mu = a_inv @ b_re
        for j, proj in enumerate(projections):
            half = math.sqrt(max(radius, 0.0) * float(a_inv[j, j]))
            for side, expected in (("lower", mu[j] - half),
                                   ("upper", mu[j] + half)):
                claimed = proj.get(side)
                if claimed is None or abs(float(claimed) - expected) > \
                        1e-6 * (1 + abs(expected)):
                    _fail(f"projection onto {names[j]!r}: {side} {claimed} is "
                          f"not the ellipsoid's support point {expected} in "
                          f"that direction")


_MEASUREMENT_CORRECTION_TOL = 1e-6


def _record_cell(level, width: int, fail) -> tuple:
    """A recorded ``level`` as the tuple of axis values it stands for.

    A one-column axis records the bare value it has always recorded; a
    joint one records the list, in the axis's own order. A record whose
    shape disagrees with the axis is refused here rather than keyed
    anyway — a two-column axis carrying a scalar would key on something no
    cell can equal, and every stratum would then fail for "no matrix",
    which is a true sentence about the wrong fault.
    """
    if width == 1:
        if isinstance(level, list):
            fail(f"a one-column differential axis recorded a cell {level!r}")
        return (level,)
    if not isinstance(level, list) or len(level) != width:
        fail(
            f"a {width}-column differential axis recorded {level!r}, which "
            f"does not give one value per column"
        )
    return tuple(level)


def _axis_columns(differential_by) -> tuple:
    """The differential axis as a tuple of column names.

    One column or several, and the one-column case is spelled as a bare
    name because that is what it has always been spelled as. Reading it
    into a tuple here is what keeps a joint axis from being a third branch
    everywhere below: the matrix is selected by a CELL either way, and how
    many coordinates that cell has is the only difference.
    """
    if isinstance(differential_by, str):
        return (differential_by,)
    return tuple(differential_by)


def _cell_key_v(values) -> tuple:
    """The key of a whole cell — one :func:`_level_key_v` per coordinate."""
    return tuple(_level_key_v(v) for v in values)


def _axis_slots(axis: tuple, adjustment_vars: list, home: str, fail) -> tuple:
    """Where each axis column's value is read from: an index into the
    stratum key, or ``None`` for the channel's own column (the arm, or the
    outcome column being inverted).

    A column that is neither is the fault this refuses. It used to be
    checked as "differential_by must be among adjustment_vars", which a
    joint axis fails for naming the arm — a column that is not a covariate
    and is not a typo either.
    """
    slots: list[int | None] = []
    for col in axis:
        if col in adjustment_vars:
            slots.append(adjustment_vars.index(col))
        elif col == home:
            slots.append(None)
        else:
            fail(
                f"differential axis names {col!r}, which is neither {home!r} "
                f"nor one of the recorded adjustment_vars {adjustment_vars}"
            )
    return tuple(slots)


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

    def _fail(msg: str) -> NoReturn:
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

    # Two claims about the declaration, before anything is inverted with it.
    # Every recorded tally must normalise to the matrix beside it, which is
    # the one part of the widening a sufficient statistic can reproduce; and
    # the premise the estimate declares must say which of the two ways this
    # channel was settled, because the interval is the same pair of numbers
    # on the page either way.
    _check_validation_tallies(suff, _fail)
    _check_matrix_premises(
        estimate, suff, rule="measurement_correction_numeric",
        channels={estimate.get("outcome"): "validation_counts"},
    )

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
    axis_columns: tuple = (
        _axis_columns(differential_by) if covariate_differential else ()
    )
    # Exactly one of the two is populated below, and each is read only
    # under the same condition that populates it; empty means "this
    # selector is not the one in play".
    Minv_by_arm: dict = {}
    Minv_by_level: dict = {}
    cov_idx = None
    if covariate_differential:
        if mc.get("differential_by") not in (None, differential_by):
            _fail(
                f"measurement_correction.differential_by {mc.get('differential_by')!r} "
                f"disagrees with sufficient_statistics.differential_by {differential_by!r}"
            )
        adjustment_vars = list(suff.get("adjustment_vars") or [])
        axis_slots = _axis_slots(
            axis_columns, adjustment_vars, str(estimate.get("treatment")), _fail)
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
            cell = _record_cell(lvl, len(axis_columns), _fail)
            Minv_lvl, _d = _reinvert_stochastic(
                mat, k, rec_det, _fail,
                label=f"{'/'.join(axis_columns)}={lvl!r}",
            )
            key = _cell_key_v(cell)
            if key in Minv_by_level:
                _fail(
                    f"duplicate differential level {lvl!r} for "
                    f"{'/'.join(axis_columns)}"
                )
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
            cell = tuple(
                bool(arm) if slot is None else rec["z"][slot]
                for slot in axis_slots
            )
            Minv_sel = Minv_by_level.get(_cell_key_v(cell))
            if Minv_sel is None:
                _fail(
                    f"stratum z={rec['z']} arm={arm} has no confusion matrix "
                    f"for {'/'.join(axis_columns)}={list(cell)!r} in the "
                    f"recorded set"
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


#: Where the same matrix is written twice: the ``measurement_correction`` block
#: (what an auditor reads) and its ``sufficient_statistics`` (what the verifier
#: re-inverts). Paired by (block key, sufficient-statistics key).
_MATRIX_WRITTEN_TWICE = (
    ("confusion_matrix", "confusion_matrix"),
    ("confusion_matrix_exposure", "exposure_confusion_matrix"),
    ("confusion_matrix_outcome", "outcome_confusion_matrix"),
)


def _check_block_matrices_match(mc: dict, suff: dict, fail) -> None:
    """The matrices the block shows must be the matrices the number came from.

    Only the sufficient-statistics copy is re-inverted, so without this the
    block's copy is decorative: an envelope could display one channel to a
    reader while the point was computed from another, and every numeric check
    would still pass because every numeric check reads the other copy. Found by
    a tamper probe that changed the displayed matrix and was not rejected.
    """
    for block_key, suff_key in _MATRIX_WRITTEN_TWICE:
        shown = mc.get(block_key)
        used = suff.get(suff_key)
        if shown is None or used is None:
            continue
        if [[float(v) for v in row] for row in shown] != [
            [float(v) for v in row] for row in used
        ]:
            fail(
                f"measurement_correction.{block_key} is not the matrix the "
                f"point was computed from (sufficient_statistics.{suff_key})"
            )
    shown_sets = mc.get("confusion_matrices")
    if shown_sets is None:
        return
    used_sets = (
        suff.get("confusion_matrices_by_outcome")
        or suff.get("confusion_matrices_by_level")
        or suff.get("confusion_matrices_by_arm")
    )
    if used_sets is None:
        fail(
            "measurement_correction.confusion_matrices has no counterpart in "
            "sufficient_statistics, so nothing re-inverted what it shows"
        )
        return   # unreachable: ``fail`` raises, but it is a plain parameter
    if len(shown_sets) != len(used_sets):
        fail(
            f"measurement_correction.confusion_matrices has {len(shown_sets)} "
            f"entries; the set that was inverted has {len(used_sets)}"
        )
    for shown, used in zip(shown_sets, used_sets):
        if [[float(v) for v in row] for row in shown.get("matrix", ())] != [
            [float(v) for v in row] for row in used.get("matrix", ())
        ]:
            fail(
                "a matrix in measurement_correction.confusion_matrices is not "
                "the one the inversion used"
            )


def _check_recorded_risks(mc: dict, corrected, naive, close, fail) -> None:
    """The per-level risks the block records must be the ones just re-derived.

    Without this the risks would be the only numbers in the envelope nothing
    re-computes — and they are the numbers the curve is built from, so a
    tampered risk vector beside an untampered point would read as a corrected
    answer whose per-level detail says something else.
    """
    for key, derived in (("risks", corrected), ("naive_risks", naive)):
        claimed = mc.get(key)
        if claimed is None:
            continue
        if len(claimed) != len(derived):
            fail(
                f"measurement_correction.{key} has {len(claimed)} entries, "
                f"re-derived {len(derived)}"
            )
        for a, (c, d) in enumerate(zip(claimed, derived)):
            if not close(d, float(c)):
                fail(
                    f"measurement_correction.{key}[{a}] mismatch — "
                    f"re-derived {d}, recorded {c}"
                )


def _check_exposure_curve(estimate: dict, states, corrected, close, fail) -> None:
    """Every curve row re-derived: one row per non-reference level, each level
    named once, each effect the level's risk minus the reference's."""
    curve = estimate.get("dose_response_curve")
    if curve is None:
        return
    if estimate.get("reference_point") is not None and (
        _state_key(estimate["reference_point"]) != _state_key(states[0])
    ):
        fail(
            f"numeric_estimate.reference_point {estimate['reference_point']!r} is "
            f"not the first declared exposure state {states[0]!r}"
        )
    expected = [_state_key(s) for s in states[1:]]
    seen: list = []
    for row in curve:
        try:
            xk = _state_key(row["x"])
            effect = float(row["effect"])
        except (KeyError, TypeError, ValueError) as exc:
            fail(f"ill-formed dose_response_curve row: {exc}")
        if xk in seen:
            fail(f"dose_response_curve names level {row['x']!r} twice")
        seen.append(xk)
        try:
            a = [_state_key(s) for s in states].index(xk)
        except ValueError:
            fail(
                f"dose_response_curve row {row['x']!r} is not an exposure state "
                f"{list(states)!r}"
            )
        if a == 0:
            fail(
                "dose_response_curve carries the reference level, whose effect "
                "against itself is zero by construction and not an estimate"
            )
        derived = corrected[a] - corrected[0]
        if not close(derived, effect):
            fail(
                f"dose_response_curve[{row['x']!r}] mismatch — re-derived "
                f"{derived}, recorded {effect}"
            )
    if sorted(map(str, seen)) != sorted(map(str, expected)):
        fail(
            f"dose_response_curve must carry every non-reference level "
            f"{list(states[1:])!r}; got {[row['x'] for row in curve]!r}"
        )


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

    def _fail(msg: str) -> NoReturn:
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

    # Two claims about the declaration, before anything is inverted with it.
    # Every recorded tally must normalise to the matrix beside it, which is
    # the one part of the widening a sufficient statistic can reproduce; and
    # the premise the estimate declares must say which of the two ways this
    # channel was settled, because the interval is the same pair of numbers
    # on the page either way.
    _check_validation_tallies(suff, _fail)
    _check_matrix_premises(
        estimate, suff, rule="exposure_measurement_correction_numeric",
        channels={estimate.get("treatment"): "validation_counts"},
    )

    try:
        states = list(suff["states"])
        outcome_states = list(suff["outcome_states"])
        target_value = suff["target_value"]
        strata = list(suff["strata"])
        marginal_counts = list(suff["marginal_counts"])
        marginal_total = int(suff["marginal_total"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"ill-formed sufficient statistics: {exc}")

    kx = len(states)
    if kx < 2 or len(set(map(_state_key, states))) != kx:
        _fail(f"exposure states must be two or more distinct values; got {states!r}")
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
    axis_columns: tuple = (
        _axis_columns(differential_by) if covariate_differential else ()
    )
    # Exactly one of the two is populated below, and each is read only
    # under the same condition that populates it; empty means "this
    # selector is not the one in play".
    Minv_by_outcome: dict = {}
    Minv_by_level: dict = {}
    cov_idx = None
    if covariate_differential:
        if mc.get("differential_by") not in (None, differential_by):
            _fail(
                f"measurement_correction.differential_by {mc.get('differential_by')!r} "
                f"disagrees with sufficient_statistics.differential_by {differential_by!r}"
            )
        adjustment_vars = list(suff.get("adjustment_vars") or [])
        axis_slots = _axis_slots(
            axis_columns, adjustment_vars, str(estimate.get("outcome")), _fail)
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
            cell = _record_cell(lvl, len(axis_columns), _fail)
            Minv_lvl, _d = _reinvert_stochastic(
                mat, kx, rec_det, _fail,
                label=f"{'/'.join(axis_columns)}={lvl!r}",
            )
            key = _cell_key_v(cell)
            if key in Minv_by_level:
                _fail(
                    f"duplicate differential level {lvl!r} for "
                    f"{'/'.join(axis_columns)}"
                )
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
                mat, kx, rec_det, _fail, label=f"outcome {lvl!r}",
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
        if M.shape != (kx, kx):
            _fail(f"exposure confusion matrix {M.shape} is not {kx}×{kx}")
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

    # Per-z recovered target risk AT EVERY exposure level (corrected + naive),
    # from the kx×k joint tables.
    by_z: dict = {}
    for rec in strata:
        zk = _z_key(rec["z"])
        joint = np.asarray(rec["joint_counts"], dtype=float)
        if joint.shape != (kx, k):
            _fail(f"joint table shape {joint.shape} != ({kx}, {k}) for z={rec['z']}")
        if (joint < -1e-9).any():
            _fail(f"joint table for z={rec['z']} has a negative count")
        arm_n = joint.sum(axis=1)                 # observed size of each exposure arm
        empty = [i for i in range(kx) if arm_n[i] <= 0]
        if empty:
            _fail(
                f"covariate stratum {rec['z']} has an empty observed exposure arm "
                f"at {[states[i] for i in empty]} "
                f"(arm sizes {[int(a) for a in arm_n]}); positivity is violated"
            )
        Nz = joint.sum()
        p_obs = joint / Nz
        p_true = np.empty_like(p_obs)
        if covariate_differential:
            # Per outcome COLUMN, because the axis may name the outcome as
            # well as a covariate. Where it does not, every column selects
            # the same M_z and this is the one-matrix multiplication it was
            # written as — the same arithmetic, said once for both.
            for j in range(k):
                cell = tuple(
                    outcome_states[j] if slot is None else rec["z"][slot]
                    for slot in axis_slots
                )
                Minv_sel = Minv_by_level.get(_cell_key_v(cell))
                if Minv_sel is None:
                    _fail(
                        f"stratum z={rec['z']} has no confusion matrix for "
                        f"{'/'.join(axis_columns)}={list(cell)!r} in the "
                        f"recorded set"
                    )
                p_true[:, j] = Minv_sel @ p_obs[:, j]
        else:
            for j in range(k):
                p_true[:, j] = Minv_by_outcome[_level_key_v(outcome_states[j])] @ p_obs[:, j]
        px = p_true.sum(axis=1)
        degenerate = [i for i in range(kx) if float(px[i]) <= 1e-12]
        if degenerate:
            _fail(
                f"stratum {rec['z']} recovers a non-positive true exposure "
                f"marginal at {[states[i] for i in degenerate]} "
                f"({[round(float(px[i]), 6) for i in degenerate]})"
            )
        by_z[zk] = (
            [float(p_true[a, target_index]) / float(px[a]) for a in range(kx)],
            [float(joint[a, target_index]) / float(arm_n[a]) for a in range(kx)],
        )

    corrected = [0.0] * kx
    naive = [0.0] * kx
    for zk, p_z_count in marg.items():
        p_z = p_z_count / marginal_total
        rd = by_z.get(zk)
        if rd is None:
            _fail(f"covariate stratum {list(zk)} missing from the joint tables")
        for a in range(kx):
            corrected[a] += rd[0][a] * p_z
            naive[a] += rd[1][a] * p_z

    def _close(derived: float, claimed: float) -> bool:
        return abs(derived - claimed) <= _MEASUREMENT_CORRECTION_TOL * (
            1 + abs(derived)
        )

    # The reference is the first declared state — that is the whole of the
    # convention, so it is re-derived here and the recorded value is checked
    # against it rather than believed.
    recorded_reference = suff.get("reference_value")
    if recorded_reference is not None and (
        _state_key(recorded_reference) != _state_key(states[0])
    ):
        _fail(
            f"sufficient_statistics.reference_value {recorded_reference!r} is not "
            f"the first declared exposure state {states[0]!r}"
        )

    # Two levels have one contrast and it is the point; more than two have
    # k−1 and none of them is "the" point, so a point there would be a number
    # with no statement of which levels it runs between.
    point = estimate.get("point")
    if kx > 2:
        if point is not None:
            _fail(
                f"a point {point!r} is recorded for an exposure with {kx} "
                f"levels, where no single contrast is the effect"
            )
    else:
        if not isinstance(point, (int, float)) or isinstance(point, bool):
            _fail(f"missing / non-numeric point {point!r}")
        derived = corrected[1] - corrected[0]
        if not _close(derived, float(point)):
            _fail(
                f"point mismatch — re-derived corrected {derived}, recorded {point}"
            )
        claimed_naive = mc.get("naive_point")
        if claimed_naive is None:
            _fail("measurement_correction.naive_point missing")
        derived_naive = naive[1] - naive[0]
        if not _close(derived_naive, float(claimed_naive)):
            _fail(
                f"naive_point mismatch — re-derived {derived_naive}, "
                f"recorded {claimed_naive}"
            )

    _check_block_matrices_match(mc, suff, _fail)
    _check_recorded_risks(mc, corrected, naive, _close, _fail)
    _check_exposure_curve(estimate, states, corrected, _close, _fail)


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

    def _fail(msg: str) -> NoReturn:
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

    # Two claims about the declaration, before anything is inverted with it.
    # Every recorded tally must normalise to the matrix beside it, which is
    # the one part of the widening a sufficient statistic can reproduce; and
    # the premise the estimate declares must say which of the two ways this
    # channel was settled, because the interval is the same pair of numbers
    # on the page either way.
    _check_validation_tallies(suff, _fail)
    _check_matrix_premises(
        estimate, suff, rule="combined_measurement_correction_numeric",
        channels={estimate.get("treatment"): "exposure_validation_counts",
                  estimate.get("outcome"): "outcome_validation_counts"},
    )
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

    kx = len(states)
    if kx < 2 or len(set(map(_state_key, states))) != kx:
        _fail(f"exposure states must be two or more distinct values; got {states!r}")
    k = len(outcome_states)
    if k < 2:
        _fail(f"need at least 2 outcome states; got {outcome_states!r}")
    if len(set(map(_state_key, outcome_states))) != k:
        _fail("outcome states are not distinct")

    # Both channels re-validated and re-inverted independently of the producer.
    Mx_inv, det_x = _reinvert_stochastic(
        suff.get("exposure_confusion_matrix"), kx,
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
    det_joint = det_x ** k * det_y ** kx
    for source, name in ((mc, "measurement_correction"), (suff, "sufficient_statistics")):
        claimed_joint = source.get("det_joint")
        if claimed_joint is not None and abs(
            float(claimed_joint) - det_joint
        ) > 1e-9 * (1 + abs(det_joint)):
            _fail(
                f"{name}.det_joint {claimed_joint} disagrees with "
                f"det(M_x)^{k} · det(M_y)^{kx} = {det_joint}"
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
        if joint.shape != (kx, k):
            _fail(f"joint table shape {joint.shape} != ({kx}, {k}) for z={rec['z']}")
        if (joint < -1e-9).any():
            _fail(f"joint table for z={rec['z']} has a negative count")
        arm_n = joint.sum(axis=1)              # observed size of each exposure arm
        empty = [i for i in range(kx) if arm_n[i] <= 0]
        if empty:
            _fail(
                f"covariate stratum {rec['z']} has an empty observed exposure arm "
                f"at {[states[i] for i in empty]} "
                f"(arm sizes {[int(a) for a in arm_n]}); positivity is violated"
            )
        p_obs = joint / joint.sum()
        p_true = Mx_inv @ p_obs @ My_inv.T
        px = p_true.sum(axis=1)
        degenerate = [i for i in range(kx) if float(px[i]) <= 1e-12]
        if degenerate:
            _fail(
                f"stratum {rec['z']} recovers a non-positive true exposure "
                f"marginal at {[states[i] for i in degenerate]} "
                f"({[round(float(px[i]), 6) for i in degenerate]})"
            )
        by_z[_z_key(rec["z"])] = (
            [float(p_true[a, target_index]) / float(px[a]) for a in range(kx)],
            [float(joint[a, target_index]) / float(arm_n[a]) for a in range(kx)],
        )

    corrected = [0.0] * kx
    naive = [0.0] * kx
    for zk, p_z_count in marg.items():
        rd = by_z.get(zk)
        if rd is None:
            _fail(f"covariate stratum {list(zk)} missing from the joint tables")
        p_z = p_z_count / marginal_total
        for a in range(kx):
            corrected[a] += rd[0][a] * p_z
            naive[a] += rd[1][a] * p_z

    def _close(derived: float, claimed: float) -> bool:
        return abs(derived - claimed) <= _MEASUREMENT_CORRECTION_TOL * (
            1 + abs(derived)
        )

    recorded_reference = suff.get("reference_value")
    if recorded_reference is not None and (
        _state_key(recorded_reference) != _state_key(states[0])
    ):
        _fail(
            f"sufficient_statistics.reference_value {recorded_reference!r} is not "
            f"the first declared exposure state {states[0]!r}"
        )

    # Two levels have one contrast and it is the point; more than two have
    # k−1 and none of them is "the" point, so a point there would be a number
    # with no statement of which levels it runs between.
    point = estimate.get("point")
    if kx > 2:
        if point is not None:
            _fail(
                f"a point {point!r} is recorded for an exposure with {kx} "
                f"levels, where no single contrast is the effect"
            )
    else:
        if not isinstance(point, (int, float)) or isinstance(point, bool):
            _fail(f"missing / non-numeric point {point!r}")
        derived = corrected[1] - corrected[0]
        if not _close(derived, float(point)):
            _fail(
                f"point mismatch — re-derived corrected {derived}, recorded {point}"
            )
        claimed_naive = mc.get("naive_point")
        if claimed_naive is None:
            _fail("measurement_correction.naive_point missing")
        derived_naive = naive[1] - naive[0]
        if not _close(derived_naive, float(claimed_naive)):
            _fail(
                f"naive_point mismatch — re-derived {derived_naive}, "
                f"recorded {claimed_naive}"
            )

    _check_block_matrices_match(mc, suff, _fail)
    _check_recorded_risks(mc, corrected, naive, _close, _fail)
    _check_exposure_curve(estimate, states, corrected, _close, _fail)


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

    def _fail(msg: str) -> NoReturn:
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

    # Everything above re-derives the POINT, and the point is the same number
    # whether σ²_u was taken as exact or redrawn from the study that estimated
    # it. What separates those two runs is the interval, which no sufficient
    # statistic can reproduce — so the one thing checkable about it is that the
    # block and the premise tell the reader the same story.
    # Which columns count as mismeasured is taken from the error diagonal this
    # audit rebuilt, not from the block's own list of them: a premise held
    # against the producer's account of what it corrected would agree with the
    # producer wherever that account is the thing that is wrong.
    check_declaration_premises(
        VARIANCE,
        rule="regression_calibration_numeric",
        declared=estimate.get("assumptions") or (),
        measured=[v for v, e in zip(design_vars, e_vec) if e > 0],
        carried=rc.get("validation_df") or {},
    )


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


#: Where a single-channel estimate's matrices and their tallies sit, and
#: where a combined one's two channels do. Restated rather than imported,
#: for the reason every name in this module is.
_TALLIED = (
    ("confusion_matrix", "validation_counts"),
    ("exposure_confusion_matrix", "exposure_validation_counts"),
    ("outcome_confusion_matrix", "outcome_validation_counts"),
)
_PER_LEVEL = ("confusion_matrices_by_arm", "confusion_matrices_by_level",
              "confusion_matrices_by_outcome")


def _check_validation_tallies(suff: dict,
                              fail: Callable[[str], NoReturn]) -> None:
    """Every recorded validation tally against the matrix it is said to
    normalise to.

    This is the one part of the widening that IS re-derivable. The interval
    itself is a bootstrap and no sufficient statistic reproduces it, but the
    matrix the redraws were centred on is a column-normalisation of the
    tally, exactly and by definition — so a tally that does not normalise
    to the recorded matrix says the two came from different places, and one
    of them is not what the correction used.

    A set settled two ways is rejected here as well as at the producer,
    because "some levels counted" is a claim the premise cannot make: the
    channel's single premise id would then be true of part of a channel.
    """
    import numpy as np

    def one(counts, matrix, where: str) -> None:
        unusable = f"{where} is not a rectangle of non-negative finite counts"
        try:
            C = np.asarray(counts, dtype=float)
        except (TypeError, ValueError):
            fail(unusable)
        if (C.ndim != 2 or C.size == 0 or not np.isfinite(C).all()
                or (C < 0).any()):
            fail(unusable)
        totals = C.sum(axis=0)
        if (totals <= 0).any():
            fail(
                f"{where} has a true state no validation subject stood at "
                f"(column totals {[round(float(t), 6) for t in totals]}), so "
                f"that column of the matrix is a proportion of nothing"
            )
        M = np.asarray(matrix, dtype=float)
        if M.shape != C.shape:
            fail(f"{where} is {C.shape} and the matrix beside it is {M.shape}")
        if not np.allclose(C / totals, M, atol=1e-9):
            fail(
                f"{where} does not normalise to the matrix recorded beside "
                f"it. A tally and its matrix are one declaration — the "
                f"interval was redrawn from this tally and centred on that "
                f"matrix, and they cannot both be what the correction used"
            )

    for mkey, ckey in _TALLIED:
        if ckey in suff:
            one(suff[ckey], suff.get(mkey), f"sufficient_statistics.{ckey}")
    for lkey in _PER_LEVEL:
        records = suff.get(lkey) or []
        counted = [r for r in records if isinstance(r, dict)
                   and "validation_counts" in r]
        if counted and len(counted) != len(records):
            fail(
                f"{lkey} declares {len(counted)} of {len(records)} levels as "
                f"a validation tally and the rest as exact matrices. One "
                f"channel is settled one way or the other, and the premise "
                f"this estimate declares can only be true of all of it"
            )
        for index, record in enumerate(counted):
            one(record["validation_counts"], record.get("matrix"),
                f"sufficient_statistics.{lkey}[{index}].validation_counts")


def _counted_channel(suff: dict, key: str):
    """The tally behind one channel, or ``None`` where none was declared.

    A differential channel records one tally per level rather than one at
    the top, and it is the CHANNEL that carries a premise — so the answer
    for a level set is the set, and it is only an answer when every level
    has one, which :func:`_check_validation_tallies` has already required.
    """
    if key in suff:
        return suff[key]
    for lkey in _PER_LEVEL:
        records = suff.get(lkey) or []
        if records and all(isinstance(r, dict) and "validation_counts" in r
                           for r in records):
            return [r["validation_counts"] for r in records]
    return None


def _check_matrix_premises(estimate: dict, suff: dict, *, rule: str,
                           channels: dict) -> None:
    """Hold a misclassification correction's matrix premises to what its
    block records — see :mod:`themis.verifier.declaration_rules`.

    ``channels`` maps each mismeasured column to the sufficient-statistic
    key its tally would sit under. The columns come from the estimate's own
    metadata because that is what the correction was OF; which of the two
    ways each was declared comes from the record, never from the premise
    being checked.
    """
    check_declaration_premises(
        CONFUSION_MATRIX,
        rule=rule,
        declared=estimate.get("assumptions") or (),
        measured=[c for c in channels if c],
        carried={
            column: tally
            for column, key in channels.items()
            if column and (tally := _counted_channel(suff, key)) is not None
        },
    )


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

    def _fail(msg: str) -> NoReturn:
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


#: The verifier's own copy of the two ways a source domain can be blocked
#: and of the agreement tolerance. Transcribed rather than imported: the
#: point of this audit is to hold the producer to a standard it did not
#: also write, and a shared constant is a shared belief.
_TRANSPORT_BLOCKED_KINDS = frozenset({
    "treatment_or_outcome_off_diagram", "no_s_admissible_set"})
_TRANSPORT_SOURCES_TOL = 1e-9


def verify_transport_sources(block: dict) -> None:
    """Re-derive the multi-source transport verdict from the block itself.

    Each declared source domain is its own selection diagram, so a block
    carries one route per domain and — once a route's formula has been
    evaluated — that route's own number. Several such numbers are several
    estimands of ONE target quantity, which makes their agreement a claim
    the block already holds the evidence for:

    - a reported number requires every evaluated route to have reached it,
      and ``agreeing_sources`` to be how many did;
    - evaluated routes that do NOT agree require no number to be reported,
      because reporting one is choosing which selection diagram to believe.

    So the withholding is audited in the same breath as the number, and a
    producer that reported the first of two conflicting values, or claimed
    an agreement over routes that disagree, is caught here rather than
    believed. The route bookkeeping is checked alongside, since a number
    attributed to a domain that does not transport is the same defect
    wearing a different shape.
    """
    def _err(msg: str) -> NoReturn:
        raise VerificationError(
            f"transport_identification: {msg}",
            step_index=None, rule="transport_identification",
        )

    declared = {
        str(n.get("id")): str(n.get("source_population"))
        for n in (block.get("s_nodes") or ())
    }
    routes = block.get("sources")
    if not isinstance(routes, list) or not routes:
        _err("carries no sources; every declared source domain gets a route, "
             "and a program with none gets the one no-boundary route")

    evaluated: list[tuple[str | None, float]] = []
    for route in routes:
        source = route.get("source_population")
        transportable = bool(route.get("transportable"))
        numeric = route.get("numeric")
        if transportable:
            if route.get("blocked_by") is not None:
                _err(f"source {source!r} transports and still names a reason "
                     f"it does not")
            if route.get("formula_repr") is None:
                _err(f"source {source!r} transports with no estimand")
        else:
            if str(route.get("blocked_by")) not in _TRANSPORT_BLOCKED_KINDS:
                _err(f"source {source!r} does not transport and names "
                     f"{route.get('blocked_by')!r}, which is not one of the "
                     f"ways a source domain can be blocked")
            if numeric is not None:
                _err(f"source {source!r} does not transport and still carries "
                     f"a number")
        for node_id in route.get("s_nodes") or ():
            if str(node_id) not in declared:
                _err(f"source {source!r} claims selection node {node_id!r}, "
                     f"which the block does not declare")
            if declared[str(node_id)] != str(source):
                _err(f"selection node {node_id!r} is declared about "
                     f"{declared[str(node_id)]!r} and rides on the route for "
                     f"{source!r}; a diagram belongs to one source domain")
        if isinstance(numeric, dict):
            evaluated.append((source, float(numeric["value"])))

    reported = block.get("numeric")
    if reported is None:
        if len(evaluated) >= 2:
            spread = max(v for _s, v in evaluated) - min(v for _s, v in evaluated)
            if spread <= _TRANSPORT_SOURCES_TOL:
                _err(f"{len(evaluated)} sources agree to within {spread:.3g} "
                     f"and no number is reported; agreement is the case where "
                     f"the answer stands")
        elif evaluated:
            _err("one source evaluated its estimand and no number is "
                 "reported; there is nothing for it to disagree with")
        return

    if not evaluated:
        _err("a number is reported and no source evaluated its estimand")
    value = float(reported["value"])
    for source, v in evaluated:
        if abs(v - value) > _TRANSPORT_SOURCES_TOL:
            _err(f"source {source!r} carried the effect to {v!r} and the "
                 f"reported number is {value!r}; two numbers for one quantity "
                 f"refute a declared selection diagram and no number is the "
                 f"answer to that")
    if int(reported["agreeing_sources"]) != len(evaluated):
        _err(f"claims {reported['agreeing_sources']} agreeing sources and "
             f"{len(evaluated)} evaluated their estimand")
    if reported.get("source_population") not in {s for s, _v in evaluated}:
        _err(f"attributes the number to {reported.get('source_population')!r}, "
             f"which is not one of the sources that evaluated")


_ACR_TOL = 1e-7


def verify_acr_decomposition(estimate: dict) -> None:
    """Independently re-derive the average-causal-response decomposition.

    Everything the block claims comes back from ``cells`` alone — per
    instrument level, a count and three sums — so the table is recomputed
    rather than re-read. The identity being checked is the one that makes
    the block true at all:

        Cov(S, Z) = Σ_j (s_j − s_{j−1}) · Cov(1{S ≥ s_j}, Z)
        point     = Cov(Y, Z) / Cov(S, Z)
        weight_j  = (s_j − s_{j−1}) · Cov(1{S ≥ s_j}, Z) / Cov(S, Z)

    and hence Σ_j weight_j = 1, which is not a normalisation imposed on
    the way out but a consequence — so a weight vector that sums to one
    while disagreeing with the cells is caught, and so is one that agrees
    with the cells while failing to sum to one.

    The monotonicity verdict is re-derived too. It is the block's only
    claim ABOUT the world rather than about arithmetic, and it is the one
    a producer would most usefully lie about: a negative weight says the
    reported number is not an average of anything, and it hides behind a
    perfectly ordinary aggregate first stage.
    """
    acr = estimate.get("acr_decomposition")
    if acr is None:
        return

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"acr_decomposition: {msg}", step_index=None,
            rule="acr_decomposition",
        )

    def _close(a: float, b: float) -> bool:
        return abs(a - b) <= _ACR_TOL * max(1.0, abs(a), abs(b))

    levels = [float(v) for v in acr.get("levels") or ()]
    margins = list(acr.get("margins") or ())
    cells = list(acr.get("cells") or ())
    if len(levels) < 2:
        _err(f"claims {len(levels)} dose levels; a margin needs two")
    if len(margins) != len(levels) - 1:
        _err(f"{len(margins)} margins over {len(levels)} levels")
    if sorted(levels) != levels or len(set(levels)) != len(levels):
        _err(f"levels {levels} are not strictly ascending")
    if len(cells) < 2:
        _err("fewer than two instrument levels; nothing moves the treatment")

    n_total = sum(int(c["n"]) for c in cells)
    if n_total <= 0:
        _err("the cells hold no observations")
    z_vals = [float(c["instrument_value"]) for c in cells]
    if sorted(z_vals) != z_vals or len(set(z_vals)) != len(z_vals):
        _err(f"instrument levels {z_vals} are not strictly ascending")
    if [float(v) for v in acr.get("instrument_levels") or ()] != z_vals:
        _err("instrument_levels disagrees with the cells")

    for c in cells:
        above = [int(v) for v in c["at_or_above"]]
        if len(above) != len(levels) - 1:
            _err(f"cell at Z={c['instrument_value']!r} counts {len(above)} "
                 f"thresholds over {len(levels)} levels")
        if any(a > int(c["n"]) or a < 0 for a in above):
            _err(f"cell at Z={c['instrument_value']!r} counts more rows above "
                 f"a threshold than it holds")
        if any(above[i] < above[i + 1] for i in range(len(above) - 1)):
            # {S >= s_1} contains {S >= s_2} contains ..., always.
            _err(f"cell at Z={c['instrument_value']!r} has more rows above a "
                 f"higher threshold than above a lower one")

    e_z = sum(float(c["instrument_value"]) * int(c["n"]) for c in cells) / n_total
    e_s = sum(float(c["sum_treatment"]) for c in cells) / n_total
    e_y = sum(float(c["sum_outcome"]) for c in cells) / n_total
    cov_sz = sum(float(c["instrument_value"]) * float(c["sum_treatment"])
                 for c in cells) / n_total - e_s * e_z
    cov_yz = sum(float(c["instrument_value"]) * float(c["sum_outcome"])
                 for c in cells) / n_total - e_y * e_z

    if not _close(cov_sz, float(acr["first_stage_covariance"])):
        _err(f"records a first stage of {acr['first_stage_covariance']!r}; "
             f"the cells give {cov_sz!r}")
    if not _close(cov_yz, float(acr["outcome_covariance"])):
        _err(f"records an outcome covariance of {acr['outcome_covariance']!r}; "
             f"the cells give {cov_yz!r}")
    if cov_sz == 0.0:
        _err("a first stage of exactly zero; nothing is identified")

    point = estimate.get("point")
    if point is None or not _close(float(point), cov_yz / cov_sz):
        _err(f"reports a point of {point!r}; the cells give {cov_yz / cov_sz!r}")

    binary_z = len(cells) == 2
    total_weight = 0.0
    rebuilt_cov: list[float] = []
    for j, margin in enumerate(margins):
        lower = float(margin["from_dose"])
        upper = float(margin["to_dose"])
        if (lower, upper) != (levels[j], levels[j + 1]):
            _err(f"margin {j} spans {lower}→{upper}; the levels give "
                 f"{levels[j]}→{levels[j + 1]}")
        step = upper - lower
        if not _close(step, float(margin["step"])):
            _err(f"margin {j} records a step of {margin['step']!r} over "
                 f"{lower}→{upper}")
        n_above = sum(int(c["at_or_above"][j]) for c in cells)
        cov_ind = sum(float(c["instrument_value"]) * int(c["at_or_above"][j])
                      for c in cells) / n_total - (n_above / n_total) * e_z
        rebuilt_cov.append(cov_ind)
        if not _close(cov_ind, float(margin["covariance"])):
            _err(f"margin {j} records Cov(1{{S>={upper}}}, Z) = "
                 f"{margin['covariance']!r}; the cells give {cov_ind!r}")
        weight = step * cov_ind / cov_sz
        if not _close(weight, float(margin["weight"])):
            _err(f"margin {j} records a weight of {margin['weight']!r}; "
                 f"the cells give {weight!r}")
        total_weight += weight

        share = margin.get("share_moved")
        if binary_z:
            hi, lo = cells[-1], cells[0]
            expected = (int(hi["at_or_above"][j]) / int(hi["n"])
                        - int(lo["at_or_above"][j]) / int(lo["n"]))
            if share is None or not _close(float(share), expected):
                _err(f"margin {j} records a moved share of {share!r}; "
                     f"the cells give {expected!r}")
        elif share is not None:
            _err(f"margin {j} claims a moved share of {share!r} with "
                 f"{len(cells)} instrument levels, where it is a share of "
                 f"nobody")

    if not _close(total_weight, 1.0):
        _err(f"the weights sum to {total_weight!r}; they are shares of one "
             f"number and the identity makes them sum to one")

    # The one claim about the world. Under monotonicity every margin's
    # covariance shares the sign of the aggregate first stage, so a
    # negative weight refutes it. Which rule applies is read off the table
    # rather than declared on it: intervals decide where the bootstrap
    # produced them, the point sign where it did not.
    if all(m.get("ci_upper") is not None for m in margins):
        expected_refuting = [
            j for j, m in enumerate(margins) if float(m["ci_upper"]) < 0
        ]
    else:
        if any(m.get("ci_upper") is not None for m in margins):
            _err("carries an interval on some margins and not others; the "
                 "weights are shares of one number and are resampled together")
        expected_refuting = [
            j for j, cov in enumerate(rebuilt_cov)
            if (levels[j + 1] - levels[j]) * cov / cov_sz < 0
        ]

    if [int(j) for j in acr.get("refuting_margins") or ()] != expected_refuting:
        _err(f"names margins {list(acr.get('refuting_margins') or [])} as "
             f"refuting; the rule it declares gives {expected_refuting}")
    if bool(acr.get("monotonicity_refuted")) != bool(expected_refuting):
        _err(f"says monotonicity_refuted={acr.get('monotonicity_refuted')!r} "
             f"with {len(expected_refuting)} refuting margins")


def verify_identification_pattern(block: dict, graph, bidirected, query) -> None:
    """Independently re-derive the graph-level identification pattern.

    This block is the ONE sentence a reader is given about where the
    number came from — "control for {W}", "through the mediator {M},
    holding {C}" — and it names a criterion, so what is checked is that
    the named sets actually satisfy that criterion. The re-derivation
    runs on edge deletion plus m-separation (a back-door path from A is
    open given S exactly when A stays m-connected after A's outgoing
    edges are cut), which is a different derivation from the producer's
    path enumeration with a first-edge filter, and it uses the verifier's
    own m-separation rather than the runtime's.

    A pattern can also fail by being too modest, and that failure is the
    one this block was fixed for: ``c_factor`` claimed where a back door
    or a front door was there to be named leaves a reader told nothing
    when something could have been said. So the general solution is the
    only label whose ABSENCE of structure is searched for rather than
    taken on the producer's word.

    The two front-door keys answer different questions and both are
    checked against the graph. ``covariate_set`` is what the criterion
    holds; ``conditioned_on`` is what the QUESTION asks about, which the
    criterion has nothing to say about — they read alike and mean opposite
    things on a collider, which is why they are two keys rather than one.

    No branch returns without re-deriving something, and the fourth
    pattern is why that is stated. ``instrumental_variable`` used to leave
    here immediately, saying beside itself that these were "premises the
    iv_criterion derivation rule already re-derives". That sentence is
    true of the derivation and says nothing about this block: the
    derivation carries its OWN copy of the instrument, and no rule related
    the two. Measured against the public door, every field of the IV
    surface was free — an envelope naming the OUTCOME as its instrument
    passed ``themis.verify`` — while the same edit to the derivation was
    refused. A skip whose justification names a different object than the
    thing skipped is not a skip anything can check, which is why the
    branch now re-derives Pearl's criterion from the strings THIS block
    holds, against the graph, like its three siblings.
    """
    import networkx as nx

    from .rules import (
        _verifier_directed_descendants,
        _verifier_is_m_connected,
        _verifier_nodes_by_label,
        iv_criterion_holds,
    )

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"identification: {msg}", step_index=None, rule="identification",
        )

    # The IV claim reaches a reader from two blocks — ``identification``,
    # the human surface, and ``iv_identification``, which the report routes
    # — and they are one statement written twice. Whichever this is, the
    # criterion is re-derived from its own fields, so neither is audited
    # only through the other.
    pattern = block.get("pattern")
    if pattern is None and block.get("strategy") == "iv":
        pattern = "instrumental_variable"

    x = getattr(getattr(query, "intervention", None), "atom", None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    if x is None or y is None or x not in graph or y not in graph:
        return
    given = frozenset(
        getattr(g, "atom", g) for g in (getattr(query, "given", ()) or ())
    )

    bidir = frozenset(bidirected or ())
    label = _verifier_nodes_by_label(graph)

    def _node(name: str):
        n = label.get(name)
        if n is None:
            _err(f"names {name!r}, which is not a node in the graph")
        return n

    cut: dict = {}

    def _cut_out_edges(node):
        # One copy per node, reused: the negative claim below asks this
        # question once per candidate subset.
        g = cut.get(node)
        if g is None:
            g = graph.copy()
            g.remove_edges_from(list(g.out_edges(node)))
            cut[node] = g
        return g

    def _backdoor_open(src, dst, held) -> bool:
        """Is a back-door path src ⇠ … dst open given ``held``?"""
        return _verifier_is_m_connected(
            _cut_out_edges(src), bidir, src, dst, frozenset(held),
        )

    def _adjustment_valid(w) -> bool:
        held = frozenset(w) | given
        if held & (_verifier_directed_descendants(graph, x) | {x, y}):
            return False
        return not _backdoor_open(x, y, held)

    without: dict = {}

    def _front_door_valid(z, c) -> bool:
        z, c = frozenset(z), frozenset(c)
        if not z or z & ({x, y} | c):
            return False
        if c & (_verifier_directed_descendants(graph, x) | {x, y}):
            return False
        stripped = without.get(z)
        if stripped is None:
            stripped = graph.copy()
            stripped.remove_nodes_from(z)
            without[z] = stripped
        if x in stripped and y in stripped and nx.has_path(stripped, x, y):
            return False          # a directed path bypasses the mediators
        for zi in z:
            if _backdoor_open(x, zi, c):
                return False
            if _backdoor_open(zi, y, c | {x}):
                return False
        return True

    if pattern == "instrumental_variable":
        name = block.get("instrument")
        if not isinstance(name, str):
            _err("claims an instrumental variable and names no instrument")
        z = _node(name)
        w = frozenset(_node(s) for s in block.get("conditioning") or ())
        if z in (x, y):
            _err(f"names {name!r} as the instrument, which is the "
                 f"{'treatment' if z == x else 'outcome'}")
        if w & {x, y, z}:
            _err(f"holds {sorted(block.get('conditioning') or [])} while the "
                 f"instrument is valid only given a set disjoint from the "
                 f"treatment, the outcome and the instrument itself")
        iv1, iv23 = iv_criterion_holds(graph, bidir, x, y, z, w)
        if not (iv1 and iv23):
            # Which half failed is the useful half of the message: a
            # relevance failure names an instrument that moves nothing, an
            # exclusion failure names one with its own path to the outcome.
            _err(f"names {name!r} as an instrument valid given "
                 f"{sorted(block.get('conditioning') or [])}, which does not "
                 f"satisfy the IV criterion (IV1 relevance={iv1}, "
                 f"IV2+IV3 exclusion={iv23})")
        return

    if pattern == "backdoor":
        w = frozenset(_node(s) for s in block.get("adjustment_set") or ())
        if not _adjustment_valid(w):
            _err(f"claims back-door adjustment on {sorted(block.get('adjustment_set') or [])}, "
                 f"which does not satisfy the back-door criterion")
        return

    if pattern == "front_door":
        z = frozenset(_node(s) for s in block.get("mediator_set") or ())
        c = frozenset(_node(s) for s in block.get("covariate_set") or ())
        if not _front_door_valid(z, c):
            _err(f"claims a front door through {sorted(block.get('mediator_set') or [])} "
                 f"holding {sorted(block.get('covariate_set') or [])}, which does "
                 f"not satisfy the front-door criterion")
        return

    if pattern != "c_factor":
        _err(f"unknown pattern {pattern!r}")

    # The general solution, claimed. Search for the structure it says is
    # not there. Both searches are over subsets, the same shape of work
    # the producer does, because the claim being checked is a negative.
    from itertools import combinations

    descendants_x = _verifier_directed_descendants(graph, x)
    pool = [n for n in graph.nodes if n not in (descendants_x | {x, y} | given)]
    for size in range(len(pool) + 1):
        for combo in combinations(pool, size):
            if _adjustment_valid(frozenset(combo)):
                _err(f"claims the general solution while "
                     f"{sorted(n.predicate for n in combo)} is a valid "
                     f"back-door adjustment set that went unnamed")

    # The front-door search runs whether or not the question conditions.
    # It used to stop here, carrying the producer's own reason for
    # withholding the label — a conditional estimand is not what the
    # front-door criterion identifies — as a second copy. That reason was
    # about the ESTIMAND and the label is about the GRAPH, and while both
    # copies agreed the disagreement was invisible; with the producer now
    # naming the structure, a verifier that still skipped would be the one
    # place a c_factor claim on a conditional question went unchecked.
    mediators = [
        n for n in graph.nodes
        if n in descendants_x and n != y and nx.has_path(graph, n, y)
    ]
    for zsize in range(1, len(mediators) + 1):
        for zc in combinations(mediators, zsize):
            for csize in range(len(pool) + 1):
                for cc in combinations(pool, csize):
                    if _front_door_valid(frozenset(zc), frozenset(cc)):
                        _err(
                            f"claims the general solution while the effect is "
                            f"identified by the front door through "
                            f"{sorted(n.predicate for n in zc)} holding "
                            f"{sorted(n.predicate for n in cc)}")


def verify_iv_surfaces(
    identification: "dict | None",
    iv_identification: "dict | None",
    graph,
    bidirected,
    query,
) -> None:
    """The IV claim is written twice, and both copies face the reader.

    ``extensions.identification`` is the human surface and
    ``extensions.iv_identification`` is what the report routes for this
    strategy, and the producer writes one instrument, one conditioning set
    and one premise into both. Two facts follow, and they are separate.

    The first is that each block has to satisfy the criterion on its own
    fields, which :func:`verify_identification_pattern` does for whichever
    it is handed. Auditing only one and trusting the other to match would
    put the second block back where it was: reachable by a reader,
    re-derived by nobody.

    The second is that satisfying the criterion is not agreeing. A graph
    can carry two valid instruments, so both blocks can pass their own
    re-derivation while a reader is shown one and the number was computed
    from the other. So the shared fields are held equal where both are
    present — the rule the envelope's other display copies already live
    by, that a tamper of the human surface alone cannot pass.

    Equal where both are present, rather than present together in every
    field: the feedback-loop route deliberately writes no
    ``required_assumption`` on the human surface, saying beside itself
    that the premise under a loop is one sentence the gap report states in
    full and a second wording here would be the same claim with two
    authors. Absence is that route's decision about which sentence a
    reader gets. A DIFFERENT sentence is not.
    """

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"iv_identification: {msg}", step_index=None,
            rule="iv_identification",
        )

    if isinstance(iv_identification, dict):
        verify_identification_pattern(
            iv_identification, graph, bidirected, query)

    surface = identification if isinstance(identification, dict) else {}
    if surface.get("pattern") != "instrumental_variable":
        return
    if not isinstance(iv_identification, dict):
        _err("the human surface names an instrumental variable and the block "
             "it is copied from is absent")

    for field in ("instrument", "conditioning", "required_assumption"):
        shown = surface.get(field)
        if shown is None:
            continue
        held = iv_identification.get(field)
        if shown != held:
            _err(f"shows the reader {field}={shown!r} while the block it "
                 f"copies holds {held!r}")


def verify_proximal_estimand(block: dict, query) -> None:
    """Hold the proximal descriptor to the question it describes.

    ``_rule_proximal_criterion`` re-runs Miao's model (f) on the graph and
    is a real re-derivation — but it takes the roles from ``ctx.query``,
    never from this block. So identifiability is established for the
    question that was asked while the block a reader reads can name a
    different one, and the two swaps that matter most are invisible: the
    treatment-inducing proxy and the outcome-inducing proxy exchanged, or
    the unobserved confounder named as one of the observed variables. Both
    passed the public door, and both describe a study nobody ran.

    What is checkable here is the whole of it, because every field is the
    query restated: the treatment, the outcome, the latent, the two proxy
    SETS, the covariates the conditions were read within, and the channel
    that decides which algebra recovers the effect. Nothing about the graph
    is re-derived a second time — the criterion rule owns that, and it owns
    it on the same roles once these are held equal to them.

    The proxy roles are compared as SETS and the covariates as a set too:
    the producer sorts them, and which shadow of one confounder is written
    first is not a fact about anything.
    """

    from .rules import _atom_label_verifier as _label

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"proximal_estimand: {msg}", step_index=None,
            rule="proximal_estimand",
        )

    for field, declared in (
        ("treatment", getattr(query, "treatment", None)),
        ("outcome", getattr(query, "outcome", None)),
        ("latent", getattr(query, "latent", None)),
    ):
        if declared is None:
            continue
        if block.get(field) != _label(declared):
            _err(f"names {block.get(field)!r} as the {field} beside a query "
                 f"that asks about {_label(declared)!r}")

    for field in ("treatment_proxy", "outcome_proxy", "covariates"):
        declared = getattr(query, field, None)
        if declared is None:
            continue
        stated = frozenset(block.get(field) or ())
        if stated != frozenset(_label(a) for a in declared):
            _err(f"names {sorted(stated)} as {field} beside a query that "
                 f"declares {sorted(_label(a) for a in declared)}")

    # The channel's discriminator is its TYPE, not a field on it — the query
    # carries a DiscreteChannel or a BridgeChannel — while the envelope
    # carries the same distinction as a token, because a reader's surface
    # cannot dispatch on a Python class. So the token is what the type is.
    from ..types import BridgeChannel, DiscreteChannel

    channel = getattr(query, "channel", None)
    kind = ("discrete_channel" if isinstance(channel, DiscreteChannel)
            else "bridge_channel" if isinstance(channel, BridgeChannel)
            else None)
    if kind is not None and block.get("channel_kind") != kind:
        _err(f"says the effect is recovered through "
             f"{block.get('channel_kind')!r} while the query declares "
             f"{kind!r}")
    cardinality = getattr(channel, "latent_cardinality", None)
    if cardinality is not None and block.get("latent_cardinality") != cardinality:
        _err(f"assumes the unobserved confounder has "
             f"{block.get('latent_cardinality')!r} states while the query "
             f"declares {cardinality!r}")


def verify_longitudinal_identification(
    block: dict, spec, graph, bidirected,
) -> None:
    """Re-derive the sequential back door of a time-varying strategy.

    ``identified`` is the flag that decides whether a number is reported at
    all: true says the strategy contrast is point-identified by the
    g-formula, false says an unblocked back door remains at some treatment
    and the numeric layer refuses. ``verify_longitudinal_numeric`` audits
    the numbers under it and reads ``numeric_estimate``, so the flag that
    licensed them, and the history it is a claim about, were re-derived by
    nobody — the treatments could be reordered in time, a confounder block
    emptied, the outcome renamed to a treatment.

    Two things are checked and they are different in kind.

    The first is that the block describes the STRATEGY THE PROGRAM
    DECLARED. Treatments, outcome and per-time covariate blocks all come
    from ``options.longitudinal``; a block naming others describes a
    question nobody asked, and the order is part of the description because
    the history is built by walking it. That reading needs each declared
    name to be one node: on a program unrolled in time a column's variable
    has a node per step, and a block naming one of them names a step the
    declaration never chose.

    The second is the criterion itself, per time. H_k is the measured
    history — every covariate block up to and including k, plus the
    treatments before k — and each A_k needs every back-door path to Y
    blocked by it. That is the ordinary back-door criterion asked K times
    of a growing set, so it is re-derived the way the scalar one is: no
    member of H_k may descend from A_k, and A_k must be m-separated from Y
    given H_k once A_k's outgoing edges are cut.

    Which treatment failed is not re-derived and not claimed here: the
    block records only whether all of them held. The gap beside it names
    the first failure, and that is the gap report's own object.
    """
    from .rules import (
        _atom_label_verifier,
        _verifier_directed_descendants,
        _verifier_is_m_connected,
        _verifier_nodes_by_label,
    )

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"longitudinal_identification: {msg}", step_index=None,
            rule="longitudinal_identification",
        )

    label = _verifier_nodes_by_label(graph)

    def _node(name: str):
        found = label.get(name)
        if found is None:
            _err(f"names {name!r}, which is not a node in the graph")
        return found

    declared = (spec or {}) if isinstance(spec, dict) else {}
    held_at: dict = {}
    for node in graph.nodes:
        held_at.setdefault(node.predicate, []).append(node)
    for name in (*(declared.get("treatments") or ()), declared.get("outcome"),
                 *(c for blk in declared.get("confounders_by_time") or ()
                   for c in blk)):
        nodes = held_at.get(name, ()) if isinstance(name, str) else ()
        if len(nodes) > 1:
            _err(f"is written for a declaration naming {name!r}, which this "
                 f"graph holds at {len(nodes)} nodes ("
                 f"{', '.join(sorted(_atom_label_verifier(n) for n in nodes))}"
                 f"); which of them the declaration meant is written nowhere")
    for field, stated in (
        ("treatments", [t.predicate for t in
                        (_node(s) for s in block.get("treatments") or ())]),
        ("outcome", _node(block["outcome"]).predicate
         if block.get("outcome") else None),
        ("confounders_by_time",
         [[_node(s).predicate for s in blk]
          for blk in block.get("confounders_by_time") or ()]),
    ):
        if declared.get(field) is not None and declared[field] != stated:
            _err(f"records {field}={stated!r} while the program declares "
                 f"{declared[field]!r}")

    treatments = [_node(s) for s in block.get("treatments") or ()]
    outcome = _node(block["outcome"]) if block.get("outcome") else None
    blocks_by_time = [[_node(s) for s in blk]
                      for blk in block.get("confounders_by_time") or ()]
    if not treatments or outcome is None:
        return
    if len(blocks_by_time) != len(treatments):
        _err(f"records {len(blocks_by_time)} covariate block(s) for "
             f"{len(treatments)} treatment(s); the history is built by "
             f"walking them together")

    bidir = frozenset(bidirected or ())
    history: list = []
    holds = True
    for index, a_k in enumerate(treatments):
        history.extend(blocks_by_time[index])
        held = frozenset(history)
        cut = graph.copy()
        cut.remove_edges_from(list(cut.out_edges(a_k)))
        if held & (_verifier_directed_descendants(graph, a_k) | {a_k, outcome}):
            holds = False
        elif _verifier_is_m_connected(cut, bidir, a_k, outcome, held):
            holds = False
        history.append(a_k)
        if not holds:
            break

    if bool(block.get("identified")) != holds:
        _err(f"says identified={block.get('identified')!r} while the measured "
             f"history {'does' if holds else 'does not'} block every "
             f"back-door path from every treatment to the outcome")
    if holds and not (block.get("assumptions") or ()):
        _err("claims the g-formula identifies the contrast and names none of "
             "the untestable premises it rests on")


def verify_mediation_decomposition(
    block: dict, graph, bidirected, query,
) -> None:
    """Independently re-derive a mediation block's identifiability claim.

    One function for both blocks, because there is one criterion. Pearl's
    2001 conditions with the mediator replaced by a SET
    (VanderWeele-Vansteelandt 2014) reduce to his own at a singleton: the
    graph with every set member's outgoing edges cut is the graph with the
    one member's cut, the per-member separations are the one separation,
    and the membership restriction is already written over a set on both
    routes. A second transcription for the single-mediator case would be
    one more place for the two to disagree about the same theorem.

    What a reader is told from here is which decomposition they are being
    given and what has to hold for it — the natural effects, or only the
    controlled one, or neither — so what is re-derived is the WITNESS:

      M1  Y ⊥ X | W        in G[x̄]
      M2  M_j ⊥ X | W      in G[x̄], each member
      M3  M_j ⊥ Y | X, W   in G[m̄], every member's outgoing edges cut
      M4  W holds no descendant of X

      C1  Y ⊥ X | W and Y ⊥ M_j | W  in G[x̄, m̄]
      C2  W holds no descendant of X or of any member

    A claim of identifiability names the W that carries it, so the claim
    is checkable in full: the named set either satisfies the conditions or
    it does not. A claim of NON-identifiability names no witness, and it is
    the claim that withholds an answer, so it is held to being negative the
    way ``c_factor`` and ``joint_general_id`` are — a W that satisfies
    every condition and went unnamed is the failure.

    ``failed_condition`` is checked for AGREEMENT and not re-derived, and
    the distinction is the point. Which condition is named is the label of
    the candidate that got FURTHEST along a fixed order, searched without
    the membership restriction so that an intermediate confounder can be
    named rather than hidden. Furthest-along-an-order is a property of that
    search, not of the graph, and a verifier recomputing it would be
    transcribing the producer's policy and agreeing by construction. What
    IS a fact about the graph is that a condition is named exactly when
    something failed, and that is checked.
    """
    from itertools import combinations

    from .rules import (
        _verifier_directed_descendants,
        _verifier_is_m_connected,
        _verifier_nodes_by_label,
    )

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"mediation_decomposition: {msg}", step_index=None,
            rule="mediation_decomposition",
        )

    label = _verifier_nodes_by_label(graph)

    def _node(name: str):
        found = label.get(name)
        if found is None:
            _err(f"names {name!r}, which is not a node in the graph")
        return found

    x = getattr(getattr(query, "intervention", None), "atom", None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    if x is None or y is None or x not in graph or y not in graph:
        return

    # The two blocks spell the same thing singular and plural.
    stated = block.get("mediators")
    if stated is None:
        one = block.get("mediator")
        stated = [one] if one is not None else []
    mediators = frozenset(_node(s) for s in stated)
    if not mediators:
        return

    declared = getattr(query, "mediators", ()) or ()
    if not declared:
        single = getattr(query, "mediator", None)
        declared = (single,) if single is not None else ()
    if frozenset(declared) != mediators:
        _err(f"names {sorted(stated)} as the mediator(s) beside a query that "
             f"declares "
             f"{sorted(m.predicate for m in declared if m is not None)}")

    bidir = frozenset(bidirected or ())

    def _cut(nodes):
        g = graph.copy()
        for node in nodes:
            g.remove_edges_from(list(g.out_edges(node)))
        return g

    g_bar_x = _cut({x})
    g_bar_m = _cut(mediators)
    g_bar_xm = _cut(mediators | {x})
    desc_x = _verifier_directed_descendants(graph, x)
    forbidden_nde = frozenset(desc_x)
    forbidden_cde = frozenset(desc_x).union(
        *(_verifier_directed_descendants(graph, m) for m in mediators))

    def _nde_holds(w) -> bool:
        held = frozenset(w)
        if _verifier_is_m_connected(g_bar_x, bidir, x, y, held):
            return False
        if any(_verifier_is_m_connected(g_bar_x, bidir, x, m, held)
               for m in mediators):
            return False
        if any(_verifier_is_m_connected(g_bar_m, bidir, m, y, held | {x})
               for m in mediators):
            return False
        return not (held & forbidden_nde)

    def _cde_holds(w) -> bool:
        held = frozenset(w)
        if _verifier_is_m_connected(g_bar_xm, bidir, x, y, held):
            return False
        if any(_verifier_is_m_connected(g_bar_xm, bidir, m, y, held)
               for m in mediators):
            return False
        return not (held & forbidden_cde)

    # A mediator that does not mediate makes both arms vacuous, so it is
    # settled first and on its own terms: some directed path from the
    # treatment through this member to the outcome, per member.
    import networkx as nx

    mediates = all(
        m != x and m != y
        and nx.has_path(graph, x, m) and nx.has_path(graph, m, y)
        for m in mediators)
    key = "mediator_set_valid" if "mediator_set_valid" in block \
        else "mediator_valid"
    if bool(block.get(key)) != mediates:
        _err(f"says {key}={block.get(key)!r} for {sorted(stated)}; the graph "
             f"{'does' if mediates else 'does not'} carry a directed path "
             f"from the treatment through every one of them to the outcome")
    if not mediates:
        return

    pool = [n for n in graph.nodes if n != x and n != y and n not in mediators]

    for arm, holds in (("nde_nie", _nde_holds), ("cde", _cde_holds)):
        attempt = block.get(arm)
        if not isinstance(attempt, dict):
            continue
        claims = bool(attempt.get("identifiable"))
        named = attempt.get("adjustment") or []
        failed = attempt.get("failed_condition")

        if claims != (failed is None):
            _err(f"{arm} says identifiable={claims} beside "
                 f"failed_condition={failed!r}; a condition is named exactly "
                 f"when one failed")
        if claims and not bool(attempt.get("assumptions") or ()):
            _err(f"{arm} claims identifiability and names no assumption it "
                 f"rests on")

        if claims:
            w = frozenset(_node(s) for s in named)
            if not holds(w):
                _err(f"{arm} claims identifiability adjusting on "
                     f"{sorted(named)}, which does not satisfy the "
                     f"conditions")
            continue

        if named:
            _err(f"{arm} is not identifiable and still names an adjustment "
                 f"set {sorted(named)}")
        for size in range(len(pool) + 1):
            for combo in combinations(pool, size):
                if holds(frozenset(combo)):
                    _err(f"{arm} is reported non-identifiable while "
                         f"{sorted(n.predicate for n in combo)} satisfies "
                         f"every condition — the answer was withheld from a "
                         f"reader who could have had it")

    # `strategy` is the one field where the two blocks genuinely differ, and
    # the difference is a vocabulary rather than a rule: the joint block has
    # a member for BOTH arms identifiable, which the singular one has no room
    # for and answers by naming the stronger. Which vocabulary applies is read
    # off the block, from the same key that told the validity field apart.
    strategy = block.get("strategy")
    if strategy is not None:
        natural = bool((block.get("nde_nie") or {}).get("identifiable"))
        controlled = bool((block.get("cde") or {}).get("identifiable"))
        if natural and controlled:
            expected = "nde_nie+cde" if "mediators" in block else "nde_nie"
        elif natural:
            expected = "nde_nie"
        elif controlled:
            expected = "cde"
        else:
            expected = "none"
        if strategy != expected:
            _err(f"names {strategy!r} as the strategy while the arms it "
                 f"reports identifiable make it {expected!r}")


def verify_vector_iv_identification(
    block: dict, graph, bidirected, query,
) -> None:
    """Independently re-derive the instruments claimed for a treatment VECTOR.

    ``verify_vector_iv_region`` audits the region these instruments produce
    — the inverted quadratic, its shape, every coordinate projection —
    from the recorded second moments. It says nothing about whether the
    things called instruments are instruments, because the moments arrive
    already built from whichever columns were chosen. So the region could
    be exact arithmetic on the wrong variables, and the block naming them
    passed the public door saying anything: that the treatments are their
    own instruments, that the outcome is one, that an instrument moves
    something it cannot reach.

    Validity is read on the treatment SET and is not a conjunction of the
    scalar tests. Edges are cut out of every treatment at once, so an
    instrument reaching the outcome through ANOTHER treatment in the vector
    is admitted here — that path is inside the intervention — and would be
    correctly rejected by the scalar test, where the other treatment is a
    confounder. Getting this backwards in either direction is the failure
    this re-derivation exists to catch, so both faces are exercised by the
    tests rather than only the rejecting one.

    ``relevance`` is reported and not required: the region covers whether
    or not the instruments move anything, and what relevance predicts is
    whether it comes back bounded. Reported is not unchecked — an empty
    ``moves`` is a fact about the graph, so it is re-derived like the rest,
    in the ORIGINAL graph, where relevance lives.

    The order of ``treatments`` is checked and not sorted away. The
    region's coordinate projections are indexed by this list, so a reader
    told which interval belongs to which treatment is reading this order.
    """
    from .rules import _verifier_directed_descendants, _verifier_is_m_connected

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"vector_iv_identification: {msg}", step_index=None,
            rule="vector_iv_identification",
        )

    by_predicate: dict = {}
    for node in graph.nodes:
        by_predicate.setdefault(node.predicate, node)

    def _node(name: str):
        found = by_predicate.get(name)
        if found is None:
            _err(f"names {name!r}, which is not a node in the graph")
        return found

    primary = getattr(getattr(query, "intervention", None), "atom", None)
    extras = tuple(
        getattr(i, "atom", i)
        for i in (getattr(query, "extra_interventions", ()) or ()))
    vector = tuple(a for a in (primary,) + extras if a is not None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    if not vector or y is None or y not in graph:
        return
    if any(t not in graph for t in vector):
        return

    if list(block.get("treatments") or ()) != [t.predicate for t in vector]:
        _err(f"names the treatment vector {list(block.get('treatments') or ())} "
             f"beside a query that intervenes, in order, on "
             f"{[t.predicate for t in vector]}")
    if block.get("outcome") != y.predicate:
        _err(f"names {block.get('outcome')!r} as the outcome beside a query "
             f"whose outcome is {y.predicate!r}")

    treatments = frozenset(vector)
    bidir = frozenset(bidirected or ())
    cut = graph.copy()
    for t in treatments:
        cut.remove_edges_from(list(cut.out_edges(t)))
    descendants = frozenset().union(
        *(_verifier_directed_descendants(graph, t) for t in treatments))

    instruments = [_node(z) for z in block.get("instruments") or ()]
    w = frozenset(_node(s) for s in block.get("conditioning") or ())
    if w & (treatments | {y} | frozenset(instruments)):
        _err(f"holds {sorted(block.get('conditioning') or [])}, which meets "
             f"the treatments, the outcome or an instrument")
    if w & descendants:
        _err(f"holds {sorted(block.get('conditioning') or [])}, which contains "
             f"a descendant of a treatment — conditioning on a mediator of "
             f"any treatment in the vector breaks what it breaks in the "
             f"scalar case")

    for z in instruments:
        if z in treatments or z == y:
            _err(f"names {z.predicate!r} as an instrument, which is "
                 f"{'a treatment' if z in treatments else 'the outcome'}")
        if _verifier_is_m_connected(cut, bidir, z, y, w):
            _err(f"names {z.predicate!r} as an instrument valid given "
                 f"{sorted(block.get('conditioning') or [])}, while it reaches "
                 f"the outcome with every treatment's outgoing edges cut")

    relevance = block.get("relevance")
    if relevance is None:
        return
    if [r.get("instrument") for r in relevance] != [
            z.predicate for z in instruments]:
        _err(f"reports relevance for "
             f"{[r.get('instrument') for r in relevance]} beside instruments "
             f"{[z.predicate for z in instruments]}")
    for entry, z in zip(relevance, instruments):
        moves = sorted(
            t.predicate for t in treatments
            if _verifier_is_m_connected(graph, bidir, z, t, w))
        if sorted(entry.get("moves") or ()) != moves:
            _err(f"says {z.predicate!r} moves "
                 f"{sorted(entry.get('moves') or ())}; given "
                 f"{sorted(block.get('conditioning') or [])} it is "
                 f"m-connected to {moves}")


def verify_joint_identification(block: dict, graph, bidirected, query) -> None:
    """Independently re-derive the identification of a do() over a SET.

    The scalar block and this one answer the same reader question — where
    did this number come from — and the schema says outright that their
    ``pattern`` vocabularies are disjoint, which is why one verifier
    dispatching on that key could never have reached this block. It went
    unread for exactly that reason: an answer telling a reader to control
    for {W} over a treatment vector passed the public door whatever W said,
    while the scalar sentence beside it was re-derived from the graph.

    The criterion is the treatment-SET back door, and it is not a
    conjunction of the scalar ones. Edges are cut out of EVERY treatment at
    once — a path from one treatment through another into the outcome is
    inside the intervention, not a back door — and the held set may contain
    a descendant of no treatment rather than of one.

    ``joint_general_id`` is the negative claim, and it is held to being
    negative the way ``c_factor`` is: identified precisely because no
    adjustment set exists, so a valid one that went unnamed is the failure.
    The search is over subsets, the same shape of work the producer does,
    because what is being checked is that nothing was there.
    """
    from itertools import combinations

    from .rules import (
        _verifier_directed_descendants,
        _verifier_is_m_connected,
        _verifier_nodes_by_label,
    )

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"joint_identification: {msg}", step_index=None,
            rule="joint_identification",
        )

    label = _verifier_nodes_by_label(graph)

    def _node(name: str):
        found = label.get(name)
        if found is None:
            _err(f"names {name!r}, which is not a node in the graph")
        return found

    primary = getattr(getattr(query, "intervention", None), "atom", None)
    extras = tuple(
        getattr(i, "atom", i)
        for i in (getattr(query, "extra_interventions", ()) or ()))
    treatments = frozenset(a for a in (primary,) + extras if a is not None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    given = frozenset(
        getattr(g, "atom", g) for g in (getattr(query, "given", ()) or ()))
    if not treatments or y is None or y not in graph:
        return
    if any(t not in graph for t in treatments):
        return

    named = frozenset(_node(s) for s in block.get("treatments") or ())
    if named != treatments:
        _err(f"names the treatment vector "
             f"{sorted(block.get('treatments') or [])} beside a query that "
             f"intervenes on "
             f"{sorted(f'{t.predicate}({chr(44).join(a.name for a in t.args)})' for t in treatments)}")

    stated = block.get("conditioned_on")
    if stated is not None and frozenset(_node(s) for s in stated) != given:
        _err(f"records conditioned_on={sorted(stated)}, which is not what "
             f"the question conditions on")

    bidir = frozenset(bidirected or ())
    cut = graph.copy()
    for t in treatments:
        cut.remove_edges_from(list(cut.out_edges(t)))
    descendants = frozenset().union(
        *(_verifier_directed_descendants(graph, t) for t in treatments))

    def _joint_adjustment_valid(w) -> bool:
        held = frozenset(w) | given
        if held & (descendants | treatments | {y}):
            return False
        return not any(
            _verifier_is_m_connected(cut, bidir, t, y, held)
            for t in treatments)

    pattern = block.get("pattern")
    if pattern == "joint_backdoor":
        w = frozenset(_node(s) for s in block.get("adjustment_set") or ())
        if not _joint_adjustment_valid(w):
            _err(f"claims joint back-door adjustment on "
                 f"{sorted(block.get('adjustment_set') or [])}, which does "
                 f"not satisfy the treatment-set back-door criterion")
        return

    if pattern != "joint_general_id":
        _err(f"unknown pattern {pattern!r}")

    pool = [n for n in graph.nodes
            if n not in (descendants | treatments | {y} | given)]
    for size in range(len(pool) + 1):
        for combo in combinations(pool, size):
            if _joint_adjustment_valid(frozenset(combo)):
                _err(f"claims the general solution while "
                     f"{sorted(n.predicate for n in combo)} is a valid joint "
                     f"adjustment set that went unnamed")


def verify_feedback_loop(
    block: dict, iv_identification: "dict | None", feedback, query,
) -> None:
    """The reason a reader is given for an answer the DAG did not compute.

    This block is a negative claim — these routes were WITHDRAWN — and the
    step rule beside it says why that is worth forging: it replaces a
    correct back-door answer with an instrumental-variable one resting on
    linearity. The rule re-derives the loop from the PROGRAM for exactly
    that reason, and it re-derives the loop the DERIVATION names. This
    block is a third object, and it is the one the report and the gap list
    read, so it is re-derived from the program too.

    Three of its facts can be settled and one cannot.

    ``left`` / ``right`` name a pair the program declares, or nothing
    withdrew anything. ``treatment`` / ``outcome`` are the query's own two
    ends, recorded here because whether a loop reaches an estimand is a
    fact about the pair and not about the loop alone — so a block naming
    somebody else's query is naming a fact it did not establish.

    ``reduction`` says the two-equation system applies, and both of its
    faces are checked. Present, the loop must be exactly between the two
    ends, since Haavelmo's reduction is what being between them buys.
    Absent, no instrument may stand beside it — under a loop there is no
    coefficient for an instrument to identify until the pair is read as two
    equations, so an IV answer here without the reduction is an answer
    whose reader was not told the quantity changed.

    ``withdrew`` stays the producer's word. It names route ids, and a
    verifier that recomputed which routes a loop takes away would be
    reading the producer's route table — agreeing by construction, which is
    what an independent re-derivation is defined against.
    """

    from .rules import _atom_label_verifier as _label

    def _err(msg: str) -> "NoReturn":
        raise VerificationError(
            f"feedback_loop: {msg}", step_index=None, rule="feedback_loop",
        )

    declared = {frozenset(_label(a) for a in pair)
                for pair in (feedback or frozenset())}
    left, right = block.get("left"), block.get("right")
    if frozenset({left, right}) not in declared:
        _err(f"names a loop between {left!r} and {right!r}; the program "
             f"declares {sorted(sorted(p) for p in declared)}")

    x = getattr(getattr(query, "intervention", None), "atom", None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    for field, atom in (("treatment", x), ("outcome", y)):
        if atom is None:
            continue
        if block.get(field) != _label(atom):
            _err(f"records {field}={block.get(field)!r} beside a query whose "
                 f"{field} is {_label(atom)!r}")

    if block.get("reduction") is not None:
        if frozenset({left, right}) != frozenset(
                {block.get("treatment"), block.get("outcome")}):
            _err(f"claims the two-equation reduction while the loop it names "
                 f"runs between {left!r} and {right!r} rather than between "
                 f"the treatment and the outcome")
    elif isinstance(iv_identification, dict):
        _err("names no reduction beside an answer that reached an "
             "instrument; under a loop an instrument identifies a "
             "coefficient of the two-equation system or nothing at all")


def verify_recovery_verdicts_are_owed(result: object, program: object,
                                      context: VerificationContext) -> None:
    """The two verdicts on a biased sample are on the answers that owe them.

    Whether an effect survives a sample restricted on a common effect of the
    treatment and the outcome, and whether it can be recovered from the rows
    a declared missingness left observed, are each a block, audited for what
    it says where it is. Where it was not, nothing asked: removed, each of
    the ten on the corpus passed every door, and a selection verdict added
    to an answer whose sample is restricted on no common effect passed too
    -- telling a reader of a bias the sample does not carry, and how to
    undo it.

    Which answers owe one is a fact about the program, the question and the
    ground graph, all of them here. A selection verdict: the question is an
    effect, and some atom the program restricts the sample on is a directed
    common effect of its treatment and outcome -- the recovery's own scope,
    whose criterion is written for selection nodes with no latent parents.
    A restriction on a collider whose arms run through latent causes owes
    the caveat (held in data_gap_rules) and no verdict. A missing-data
    verdict: the question is an effect whose treatment and outcome are
    nodes, and the program declares a missingness indicator. Held both ways.
    """
    from collections.abc import Mapping

    from ..types import MissingnessIndicator, ObservationStatement
    from .data_gap_rules import _a_common_effect
    from .rules import _atom_label_verifier as _label

    if not isinstance(result, Mapping):
        return
    extensions = result.get("extensions")
    carried = extensions if isinstance(extensions, Mapping) else {}
    query, graph = context.query, context.graph
    statements = getattr(program, "statements", ())
    colliders: list[str] = []
    nodes = False
    question = "a question that is no effect"
    if isinstance(query, EffectQuery):
        x, y = query.intervention.atom, query.target.atom
        colliders = sorted({_label(st.atom) for st in statements
                            if isinstance(st, ObservationStatement)
                            and _a_common_effect(graph, x, y, st.atom)})
        nodes = x in graph and y in graph
        question = f"the effect of {_label(x)} on {_label(y)}"
    indicators = [st.id for st in statements
                  if isinstance(st, MissingnessIndicator)]

    def _refuse(rule: str, msg: str) -> NoReturn:
        raise VerificationError(f"{rule}: {msg}", step_index=None, rule=rule)

    selection = carried.get("selection_recovery") is not None
    if colliders and not selection:
        _refuse("selection_recovery",
                f"the program restricts the sample on {colliders}, a common "
                f"effect in {question}, and the answer carries no "
                f"selection_recovery block: a reader is not told whether the "
                f"effect survives the restriction")
    if selection and not colliders:
        _refuse("selection_recovery",
                f"the answer carries a selection_recovery block, and in "
                f"{question} no atom the program restricts the sample on is a "
                f"common effect of the treatment and the outcome: a reader is "
                f"told of a bias the sample does not carry, and how to undo it")
    owes_missing = nodes and bool(indicators)
    missing = carried.get("missing_data_recovery") is not None
    if owes_missing and not missing:
        _refuse("missing_data_recovery",
                f"the program declares missingness indicators {indicators} "
                f"and asks {question}, and the answer carries no "
                f"missing_data_recovery block: a reader is not told whether "
                f"the effect can be recovered from the rows that were observed")
    if missing and not owes_missing:
        if not indicators:
            reason = "the program declares no missingness indicator"
        elif not isinstance(query, EffectQuery):
            reason = "the question is no effect"
        else:
            reason = f"{question} is not asked of two nodes of the graph"
        _refuse("missing_data_recovery",
                f"the answer carries a missing_data_recovery block and owes "
                f"none: {reason}")


def verify_selection_recovery(block: dict, graph, observations, query) -> None:
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

    Which nodes the verdict is about is read from the premises, not from
    the block. The treatment and outcome are the question's atoms and the
    selection nodes are the atoms the program restricts the sample on
    (``observations``), and the block's names for them have to be theirs.
    The adjustment set is the one part the program does not name, and the
    block names it by predicate -- which on a program unrolled in time, or
    about several people, can mean more than one node -- so it is held to
    the claim its names make: some reading of them as distinct nodes the
    search could have chosen satisfies every condition. Each name used to
    be resolved to whichever node of its predicate the graph listed last,
    which refused honest blocks whose variable had a second node.
    """
    import networkx as nx
    from itertools import product

    from ..runtime.structural_solver import (
        is_d_connected,
        backdoor_paths,
        _path_is_open,
    )

    def _err(msg: str) -> NoReturn:
        raise VerificationError(
            f"selection_recovery: {msg}",
            step_index=None, rule="selection_recovery",
        )

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

    def _rederive_ledger(x_pred, s_nodes, zp, zm):
        z_all = list(zp) + list(zm)
        if not z_all:
            return []
        if all(_dsep(s, zi, ()) for zi in z_all for s in s_nodes):
            return []
        zp_preds = [n.predicate for n in zp]
        zm_preds = [n.predicate for n in zm]
        if not zm_preds:
            return [_unbiased(f"P({_names(zp_preds)})")]
        return [_unbiased(
            f"P({_cond(x_pred, _names(zp_preds), _names(zm_preds))})")]

    def _unbiased(expression: str) -> dict:
        """One ledger entry in the shape the envelope carries.

        The role word and the expression are two things, so the entry is a
        statement: which sentence, plus this occasion's expression. Spelled
        out from the vocabulary's name and token rather than imported from
        the producer — a re-derivation that reached for the producer's own
        words would agree with it by construction.
        """
        return {"vocabulary": "unbiased_distribution", "token": "unbiased",
                "said": {"expression": expression}}

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

    def _sbd_admissible_exists(x_node, y_node, s_nodes, max_size):
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

    def _conditional_z_exists(x_node, y_node, s_nodes, max_size):
        from itertools import combinations
        forbidden = {x_node, y_node} | set(s_nodes)
        cands = [n for n in graph.nodes if n not in forbidden]
        for size in range(1, min(len(cands), max_size) + 1):
            for combo in combinations(cands, size):
                if _s_all_dsep_y(s_nodes, y_node, (x_node,) + combo):
                    return True
        return False

    def _readings(names, taken):
        """Every way to read ``names`` as distinct nodes outside ``taken``.

        A name is a predicate, and the nodes it can mean are that
        predicate's nodes the search could have offered -- never the
        treatment, the outcome or a selection node, which it excludes.
        """
        pools = []
        for name in names:
            pool = [n for n in graph.nodes
                    if n.predicate == name and n not in taken]
            if not pool:
                _err(f"{name!r} names no node the adjustment set could hold")
            pools.append(pool)
        for reading in product(*pools):
            if len(set(reading)) == len(reading):
                yield reading

    def _some_reading_holds(failures) -> None:
        """Refuse unless one reading breaks nothing.

        The reason given is the first reading's, which is the only one
        when each name has one node -- every program the corpus holds.
        """
        first = None
        for failure in failures:
            if failure is None:
                return
            first = first or failure
        _err(first or "the adjustment set's names cannot be read as "
                      "distinct nodes")

    def _effect_reading_breaks(zp, zm):
        for n in zp:
            if n in desc_x:
                return f"z_plus member {n.predicate!r} is a descendant of X"
        for n in zm:
            if n not in desc_x:
                return f"z_minus member {n.predicate!r} is not a descendant of X"
        if not _s_all_dsep_y(s_nodes, y, (x,) + tuple(zp) + tuple(zm)):
            return "SBD condition (1) fails: S is not d-separated from Y | X,Z"
        if not _zplus_blocks(x, y, zp):
            return "SBD condition (2) fails: Z⁺ leaves a back-door path open"
        ledger = _rederive_ledger(x.predicate, s_nodes, zp, zm)
        if ledger != list(block["external_data_needed"]):
            return (
                f"external_data_needed mismatch: recomputed {ledger}, "
                f"recorded {block['external_data_needed']}"
            )
        return None

    kind = block.get("query_kind")
    intervention = getattr(query, "intervention", None)
    target = getattr(query, "target", None)
    if intervention is None or target is None:
        _err("block present on a question with no treatment and outcome")
    x, y = intervention.atom, target.atom
    for role, atom in (("treatment", x), ("outcome", y)):
        if atom not in graph:
            _err(f"the question's {role} {atom.predicate!r} is not a node "
                 f"in the graph")
        if block.get(role) != atom.predicate:
            _err(f"{role} {block.get(role)!r} is not the question's "
                 f"{atom.predicate!r}")
    s_nodes = []
    for observation in observations:
        node = observation.atom
        if node in graph and node not in (x, y) and node not in s_nodes:
            s_nodes.append(node)
    if not s_nodes:
        _err("the program restricts the sample on no node of the graph")
    restricted = [s.predicate for s in s_nodes]
    if list(block.get("selection_nodes") or ()) != restricted:
        _err(
            f"selection_nodes {block.get('selection_nodes')!r} are not the "
            f"nodes the program restricts the sample on ({restricted!r})"
        )
    desc_x = nx.descendants(graph, x)
    taken = {x, y, *s_nodes}
    recoverable = block["recoverable"]
    criterion = block["criterion"]
    zp_preds = list(block["z_plus"])
    zm_preds = list(block["z_minus"])
    # The range the producer's verdict is relative to. Read rather than
    # assumed: a negative verdict says "no admissible set of size ≤ k", and
    # re-searching to some OTHER k refutes a claim nobody made — in the
    # direction that matters (producer searched wider) it would confirm a
    # false negative rather than catch it. Both sides used to hold their own
    # literal 4, which made the two agree by construction rather than by the
    # theory, on exactly the verdict this search exists to challenge.
    budget = block.get("search_budget")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        _err(
            f"search_budget must be a non-negative integer, got {budget!r}; "
            f"without it a negative verdict has no quantifier to re-derive"
        )

    if kind == "effect":
        if recoverable:
            if criterion != "selection_backdoor":
                _err(f"effect recoverable but criterion is {criterion!r}")
            # The search behind the verdict looks at sets no larger than
            # its recorded range, so a larger witness is not one it found;
            # holding it there also bounds the readings enumerated below.
            if len(zp_preds) + len(zm_preds) > budget:
                _err(f"adjustment set of {len(zp_preds) + len(zm_preds)} is "
                     f"larger than the recorded search_budget {budget}")
            _some_reading_holds(
                _effect_reading_breaks(zp, zm)
                for zp in _readings(zp_preds, taken)
                for zm in _readings(zm_preds, taken | set(zp))
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
            if _sbd_admissible_exists(x, y, s_nodes, budget):
                _err(
                    f"block claims P(y|do(x)) is not SBD-recoverable within "
                    f"|Z| <= {budget}, but an admissible selection-backdoor "
                    f"set that size or smaller exists"
                )
    elif kind == "conditional":
        if recoverable:
            if criterion == "conditional_independence":
                if not _s_all_dsep_y(s_nodes, y, (x,)):
                    _err("claims Y ⊥ S | X but they are d-connected")
            elif criterion == "external_data":
                named = list(block["adjustment_set"])
                if len(named) > budget:
                    _err(f"adjustment set of {len(named)} is larger than "
                         f"the recorded search_budget {budget}")
                _some_reading_holds(
                    None if _s_all_dsep_y(s_nodes, y, (x,) + tuple(z))
                    else "claims Y ⊥ S | X,Z but they are d-connected given X,Z"
                    for z in _readings(named, taken)
                )
            else:
                _err(f"conditional recoverable but criterion is {criterion!r}")
        else:
            if _s_all_dsep_y(s_nodes, y, (x,)) or _conditional_z_exists(
                x, y, s_nodes, budget
            ):
                _err(
                    f"block claims P(y|x) is not s-recoverable within "
                    f"|Z| <= {budget}, but Y is d-separable from S given X "
                    f"(or X and some observed Z that size or smaller)"
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
    recoverability verdict, and recovery formula match the re-derivation,
    and so does everything the block tells a reader beside them: the
    partially observed variables, the factors and the target each stands
    for, the adjustment set, the factors the estimand requires and why a
    negative is negative -- in the spelling the block uses.

    When the block carries the multi-factor sub-blocks (``covariate_recovery``
    / ``estimand``), it also independently re-derives the covariate marginal
    P(Z | given) recovery and the combined interventional estimand verdict
    (recoverable iff BOTH the conditional and the covariate factor are), and
    checks those too. A bare conditional-only block skips that section.
    """
    import networkx as nx
    from itertools import combinations, permutations

    from ..runtime.structural_solver import is_d_connected, minimal_adjustment_sets
    from ..types import Atom

    def _err(msg: str) -> NoReturn:
        raise VerificationError(
            f"missing_data_recovery: {msg}",
            step_index=None, rule="missing_data_recovery",
        )

    R_PREFIX = "__R__"

    def _dsep(g, a, b, cond):
        return not is_d_connected(g, a, b, tuple(cond))

    # --- rebuild the m-graph (independent transcription) ---
    # The program's atoms are nodes as they stand, and each partially
    # observed node has its own R, carrying that node's arguments and
    # time. Looked up by predicate, a variable with several nodes kept
    # the last one, on this side and the producer's independently.
    # An atom that is not a node is refused rather than passed over:
    # dropping it re-derives a verdict about a different program, and
    # this side does not run the input check that refuses one upstream.
    from .rules import _atom_label_verifier as _label

    m = base_graph.copy()
    r_of_var: dict = {}
    for mi in indicators:
        var_node = mi.missing_var
        if var_node not in base_graph:
            _err(f"indicator {mi.id}: missing_var {_label(var_node)} "
                 f"is not a node of the graph")
        r_atom = Atom(
            predicate=f"{R_PREFIX}{var_node.predicate}",
            args=var_node.args,
            time_index=var_node.time_index,
        )
        m.add_node(r_atom)
        r_of_var[var_node] = r_atom
        for parent in mi.caused_by:
            if parent not in base_graph:
                _err(f"indicator {mi.id}: caused_by {_label(parent)} "
                     f"is not a node of the graph")
            m.add_edge(parent, r_atom)
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
    x = query.intervention.atom
    y = query.target.atom
    if x not in base_graph or y not in base_graph:
        _err("treatment or outcome not in graph")
    given = tuple(g.atom for g in query.given if g.atom in base_graph)
    z: tuple[Atom, ...] = ()
    try:
        adj = minimal_adjustment_sets(base_graph, x, y, given=given)
        if adj:
            smallest = min(adj, key=len)
            z = tuple(sorted(smallest, key=lambda a: a.predicate))
    except Exception:
        z = ()
    x_list = [x, *given, *z]
    y_list = [y]

    # The range the producer's verdict is relative to, read off the block.
    # A negative verdict is "no recovering factorization with conditioning
    # sets of size <= k", so re-searching to some other k re-derives a claim
    # nobody made; the two sides used to hold their own literal 4, which is
    # agreement by shared constant rather than by the theory.
    budget = block.get("search_budget")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        _err(
            f"search_budget must be a non-negative integer, got {budget!r}; "
            f"without it a negative verdict has no quantifier to re-derive"
        )

    # --- re-search the ordered factorization (reusable for any factor) ---
    def _pick_xi(yi, later):
        later_list = list(later)
        later_set = set(later_list)
        for size in range(0, min(len(later_list), budget) + 1):
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

    def _target_of(yl, xl):
        ynames = ", ".join(a.predicate for a in yl)
        xnames = ", ".join(a.predicate for a in xl)
        return f"P({ynames} | {xnames})" if xl else f"P({ynames})"

    def _formula_of(yl, xl, factors):
        target = _target_of(yl, xl)
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

    # --- what the block tells a reader beside the verdict ---
    # A report shows the partially observed variables, the factors a
    # recovery is assembled from and the target each stands for, and why a
    # negative is negative. None of them restates the verdict, so holding
    # the verdict held none of them: each could be emptied, renamed or
    # replaced on an answer the door took.
    def _hold(where, recorded, restated):
        if recorded != restated:
            _err(f"{where}: recomputed {restated!r}, recorded {recorded!r}")

    def _hold_factor_row(where, part, yl, xl, factors):
        _hold(f"{where}target", part.get("target"), _target_of(yl, xl))
        _hold(f"{where}factorization", part.get("factorization"), [
            {"factor": yi.predicate,
             "conditioned_on": [a.predicate for a in xi]}
            for yi, xi in factors or ()])
        if factors is None:
            _hold(f"{where}recovery_formula", part.get("recovery_formula"), "")
            _hold(f"{where}failure_reason", part.get("failure_reason"), {
                "token": "no_recoverable_ordered_factorization",
                "vocabulary": "missing_data_shortfall"})
        else:
            _hold(f"{where}failure_reason", part.get("failure_reason"), None)

    _hold_factor_row("", block, y_list, x_list, cond_factors)
    _hold("partially_observed", block.get("partially_observed"),
          sorted(v.predicate for v in vm))
    # Ordered factorization is sufficient and not necessary: no negative
    # from it is a proof, and a block saying its criterion is complete
    # tells a reader one is.
    _hold("complete_criterion", block.get("complete_criterion"), False)

    # --- covariate marginal P(Z | given) + full-estimand combination ---
    # Only when the block carries the multi-factor sub-blocks (the real
    # scheduler path always does; a bare conditional-only block skips this).
    if "estimand" in block or block.get("covariate_recovery") is not None:
        z_list = list(z)
        _hold("adjustment_set", block.get("adjustment_set"),
              [a.predicate for a in z_list])
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
            _hold_factor_row("covariate_recovery.", cov_block, z_list,
                             list(given), cov_factors)
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
            gnames = ", ".join(a.predicate for a in given)
            estimand = (
                f"P({y.predicate} | do({x.predicate}), {gnames})"
                if given else f"P({y.predicate} | do({x.predicate}))"
            )
            _hold("estimand.target", est_block.get("target"), estimand)
            factors = [("adjusted_conditional", "the_adjusted_conditional",
                        _target_of(y_list, x_list), cond_recoverable)]
            if z_list:
                factors.append(("covariate_marginal", "the_covariate_marginal",
                                _target_of(z_list, list(given)),
                                cov_recoverable))
            _hold("estimand.requires", est_block.get("requires"), [
                {"token": role, "vocabulary": "recovery_factor",
                 "said": {"target": target}}
                for role, _shortfall, target, _ok in factors])
            _hold("estimand.failure_reason", est_block.get("failure_reason"),
                  None if est_recoverable else {
                      "token": "a_product_is_blocked_by_its_factors",
                      "vocabulary": "missing_data_shortfall",
                      "words": {"factors": [
                          {"token": shortfall,
                           "vocabulary": "missing_data_shortfall",
                           "said": {"target": target}}
                          for _role, shortfall, target, ok in factors
                          if not ok]}})
            if not est_recoverable:
                _hold("estimand.recovery_formula",
                      est_block.get("recovery_formula"), "")
            if est_recoverable:
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
    # One terminal is admitted by its PREMISE rather than by its name.
    # An effect query ending in an instrument, on a graph whose back-door
    # set is plainly there, is the swap `feedback_loop_withdraws_adjustment`
    # exists to refuse: a correct adjustment answer replaced by one resting
    # on linearity. So the licence has to be in the same derivation. It
    # reached here as a gap of the other kind — the route emits this
    # terminal on the structural door, every test of it goes through the
    # numeric one, and an honest answer was refused at the public door for
    # as long as nobody asked the question at the door it uses.
    if last_rule == "identify_via_iv":
        if not any(step.rule == "feedback_loop_withdraws_adjustment"
                   for step in derivation):
            raise VerificationError(
                "an effect query ended in identify_via_iv with nothing in "
                "the derivation withdrawing the routes a DAG would have "
                "taken; an instrument is the escalation, not the first "
                "answer",
                step_index=len(derivation) - 1, rule=last_rule,
            )
    elif last_rule not in (
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

    The single ``causation_probability_bounds`` rule
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

    if derivation[-1].rule != "causation_probability_bounds":
        raise VerificationError(
            "causation derivation must end in "
            "'causation_probability_bounds'",
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
    block: object = None,
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
    # The rule above worked the whole counterfactual out, and a step's
    # output has room for one number of it. Asked again here, where the
    # block carrying the rest can be put beside it.
    verify_scm_counterfactual_display(block, abduct_act_predict(context))


_SCM_FIT_TOL = 1e-6


def _atom_spellings(atom) -> tuple[str, ...]:
    """The ways this envelope writes one variable as a key.

    Two, because two producers write this block and they are keyed on
    different things: the declared path spells the ATOM a question names,
    and the data path spells the COLUMN a coefficient was fitted from.
    Both are restated here rather than imported, and pinned to their
    producers by a test.

    Either is accepted for either path, PROVIDED it names one variable and
    not two — the caller drops a spelling shared by two atoms. What a key
    must do is say which variable it is about; which of the two spellings a
    producer picked is not something a reader is harmed by, and a rule
    insisting on one would refuse the other path's honest answer.
    """
    args = ",".join(a.name for a in atom.args)
    full = f"{atom.predicate}({args})"
    if getattr(atom, "time_index", None) is not None:
        t = atom.time_index.value
        full = f"{full}@t" if t == 0 else f"{full}@t{t:+d}"
    return (full, atom.predicate)


def _match_display_map(shown, expected: dict, what: str) -> None:
    """One map in the display copy, against what the re-run worked out.

    Both directions and the binding between them: a key naming nothing is
    refused, a variable the re-run has and the block does not is refused,
    and every value has to agree. Anything less lets a display copy drop
    the variable that would have told a reader something.
    """
    def _fail(why: str) -> NoReturn:
        raise VerificationError(
            f"extensions.scm_counterfactual.{what} {why} — the display copy "
            f"diverges from the counterfactual the verifier re-derived, and "
            f"it is the only place a reader meets these numbers",
            step_index=None, rule="scm_counterfactual_display_check",
        )

    if not isinstance(shown, dict):
        _fail("is not a mapping")

    # A spelling is usable only where it has ONE referent. The bare
    # predicate does not carry the argument, so a world holding two atoms
    # over the same predicate has a spelling that names both; binding it to
    # whichever came first would make this rule's meaning a fact about dict
    # order. The data path already refuses that on its own side, which is
    # what says this is one invariant and not two.
    by_name: dict[str, object] = {}
    ambiguous: set[str] = set()
    for atom in expected:
        for spelling in _atom_spellings(atom):
            if by_name.setdefault(spelling, atom) != atom:
                ambiguous.add(spelling)
    for spelling in ambiguous:
        by_name.pop(spelling, None)

    seen: dict[object, object] = {}
    for key, value in shown.items():
        atom = by_name.get(str(key))
        if atom is None:
            if str(key) in ambiguous:
                _fail(f"names {key!r}, which is the name of more than one "
                      f"variable in this counterfactual and does not say "
                      f"which")
            _fail(f"names {key!r}, which is not a variable this "
                  f"counterfactual is about")
        if atom in seen:
            _fail(f"names {key!r} for a variable it has already given")
        seen[atom] = value
    if missing := sorted(_atom_spellings(a)[0] for a in expected
                         if a not in seen):
        _fail(f"is silent about {missing}")
    for atom, value in seen.items():
        want = float(expected[atom])
        if not isinstance(value, (int, float)) or \
                abs(float(value) - want) > _SCM_FIT_TOL:
            _fail(f"gives {_atom_spellings(atom)[0]} as {value!r} and it is "
                  f"{want!r}")


def verify_scm_counterfactual_display(block, world) -> None:
    """The block a reader meets, against the world the verifier re-derived.

    ``extensions.scm_counterfactual`` is a display copy, and the numbers in
    it are answer-grade: the abducted exogenous terms and the whole
    counterfactual assignment reach a reader HERE and nowhere else. The
    derivation carries one of them — the point — so auditing the chain
    leaves every other entry free, along with the two names and the value
    that say which counterfactual this even is.

    The same sentence ``_verify_causation_extensions_match`` was written
    for, about the other block that carries answer-grade numbers a reader
    sees only in the copy. That one had it; this one did not.

    Skips quietly when there is no block. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    if not isinstance(block, dict):
        return
    _match_display_map(block.get("counterfactual_values"), world.values,
                       "counterfactual_values")
    _match_display_map(block.get("abducted_noise"), world.noise,
                       "abducted_noise")

    def _fail(why: str) -> NoReturn:
        raise VerificationError(
            f"extensions.scm_counterfactual {why} — a reader is told which "
            f"counterfactual this is by these three fields, and every number "
            f"beside them is an answer to whatever they say",
            step_index=None, rule="scm_counterfactual_display_check",
        )

    if str(block.get("target")) not in _atom_spellings(world.target):
        _fail(f"says its target is {block.get('target')!r} and the question "
              f"asked about {_atom_spellings(world.target)[0]!r}")
    intervention = block.get("intervention")
    if not isinstance(intervention, dict):
        _fail("carries no intervention")
    if str(intervention.get("variable")) not in _atom_spellings(
            world.intervened):
        _fail(f"says it intervened on {intervention.get('variable')!r} and "
              f"the question intervened on "
              f"{_atom_spellings(world.intervened)[0]!r}")
    shown_value = intervention.get("value")
    want_value = float(world.values[world.intervened])
    if not isinstance(shown_value, (int, float)) or \
            abs(float(shown_value) - want_value) > _SCM_FIT_TOL:
        _fail(f"says it set that variable to {shown_value!r} and the "
              f"counterfactual was computed at {want_value!r}")
    shown_target = block.get("target_value")
    want_target = float(world.values[world.target])
    if not isinstance(shown_target, (int, float)) or \
            abs(float(shown_target) - want_target) > _SCM_FIT_TOL:
        _fail(f"gives the answer as {shown_target!r} and the re-derived "
              f"counterfactual is {want_target!r}")


def verify_scm_counterfactual_numeric(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result,
    num_est: dict,
    block: object = None,
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
    verify_scm_counterfactual_display(
        block, _recheck_scm_counterfactual_fit(context, num_est))


def _recheck_scm_counterfactual_fit(
    context: VerificationContext, num_est: dict,
) -> Counterfactual:
    """Independent re-solve of the OLS moments + re-run of abduction-action-
    prediction. Raises VerificationError on any mismatch.

    Hands back the whole world it worked out, for the reason
    :func:`themis.verifier.rules.abduct_act_predict` does: the block that
    shows a reader these numbers is held against them.
    """
    import numpy as np
    import networkx as nx

    graph = context.graph
    q = _query_as(context, SCMCounterfactualQuery)
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

    recorded_iv = num_est.get("intervention_value")
    if recorded_iv is None:
        raise VerificationError(
            "scm_counterfactual numeric: numeric_estimate carries no "
            "intervention_value",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )
    iv_val = float(recorded_iv)
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
    return Counterfactual(noise=noise, values=cf,
                          intervened=x_atom, target=y_atom)


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
        probe, quantity = _probe_the_conjunction(formula, context.query,
                                                 context)
        if probe.status in _PROBE_REFUSES:
            raise VerificationError(
                f"counterfactual formula fails semantic verification for "
                f"{quantity} against models consistent with the graph. "
                f"{probe.detail}",
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

    The derivation must end in one of the three proximal numeric terminals,
    atop a ``proximal_criterion`` structural witness. The rule handlers re-run
    ``identify_proximal`` to confirm proximal-identifiability (safety-critical:
    a number is licensed ONLY for an identified effect) and then re-derive the
    number itself: formula (5) is a matrix inversion of a contingency table,
    the estimate records that table as counts, and the terminal rule rebuilds
    M / py / pw and runs the formula again. The bridge terminal does the same
    thing one regime over — the sieve's cross-moments are recorded and the
    solve is taken again at every penalty. The null-test terminal does it for
    a run that produced no number at all: the per-cell moments are recorded
    and the chi-square is re-solved from them. Unlike the data-refit
    estimators none of these is a metadata audit: all three computations are
    exactly re-derivable from statistics small enough to carry, so the
    ceiling those verifiers declare does not apply here.

    The structural witness is required of the test exactly as it is of the
    other two, and that is not a formality: Miao's model (f) is what licenses
    the decomposition the null is read off, so a graph that does not certify
    is a graph in which the test means nothing either. What the test drops is
    the channel's invertibility, which is a fact about the sample — never the
    identification argument, which is a fact about the diagram.

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
    terminals = ("numeric_proximal_estimate", "numeric_proximal_bridge_estimate",
                 "numeric_proximal_null_test")
    if derivation[-1].rule not in terminals:
        raise VerificationError(
            f"proximal numeric derivation must end in one of {terminals};"
            f" got {derivation[-1].rule!r}",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
