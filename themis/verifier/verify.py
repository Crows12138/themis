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
    DerivationStep,
    EffectQuery,
    IdentifyQuery,
    NumericResult,
    ProbabilityQuery,
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
from .rules import dispatch_rule, known_rule


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
    q: IdentifyQuery = context.query

    if step.rule == "backdoor_criterion":
        if step.inputs.get("x") != q.intervention.atom:
            raise VerificationError(
                "backdoor_criterion.x does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        if step.inputs.get("y") != q.target:
            raise VerificationError(
                "backdoor_criterion.y does not match verification context query",
                step_index=step_index,
                rule=step.rule,
            )
        step_given = step.inputs.get("given", frozenset())
        if frozenset(step_given) != frozenset(q.given):
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


def _assert_numeric_query_binding(
    step: DerivationStep,
    context: VerificationContext,
    step_index: int,
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

    if isinstance(q, ProbabilityQuery):
        if step.rule == "formula_evaluation":
            formula = step.inputs.get("formula")
            # The formula input may come from a StepRef or be the direct
            # ProbabilityRefExpr; binding only makes sense in the direct
            # case (probability queries don't route through R4).
            if (
                formula is not None
                and not isinstance(formula, StepRef)
            ):
                from ..types import ProbabilityRefExpr
                if isinstance(formula, ProbabilityRefExpr):
                    if formula.target != q.target:
                        raise VerificationError(
                            "formula_evaluation.formula.target does not match probability query",
                            step_index=step_index, rule=step.rule,
                        )
                    if tuple(formula.given) != tuple(q.given):
                        raise VerificationError(
                            "formula_evaluation.formula.given does not match probability query",
                            step_index=step_index, rule=step.rule,
                        )


def _walk(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    binding_asserter: Callable[[DerivationStep, VerificationContext, int], None],
) -> None:
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

        binding_asserter(step, context, i)

        for key, value in step.inputs.items():
            if isinstance(value, StepRef):
                if value.step_id not in step_output_by_id:
                    raise StepRefError(
                        f"{step.rule}.{key} = StepRef({value.step_id!r}) but "
                        f"no earlier step has that id",
                        step_index=i, rule=step.rule,
                    )

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

    _walk(derivation, context, _assert_numeric_query_binding)

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
