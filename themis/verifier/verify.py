"""Top-level verifier entry for identify derivations (slice V0).

``verify_identify(derivation, context, claimed_result)``:

1. Walks ``derivation`` in order.
2. For each step, checks that the cited rule is known.
3. Dispatches to the rule handler with the step's inputs (with
   StepRefs resolved via an internal step-output map) and the claimed
   output. The handler either accepts silently or raises a
   ``VerificationError`` subclass.
4. Confirms the last step's output matches ``claimed_result``.

A derivation that raises nothing is ``accepted``. A derivation that
raises any ``VerificationError`` is ``rejected`` and the caller can
inspect ``step_index`` / ``rule`` on the exception.
"""
from __future__ import annotations

from ..types import DerivationStep, StepRef, StructuralResult
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


def verify_identify(
    derivation: tuple[DerivationStep, ...],
    context: VerificationContext,
    claimed_result: StructuralResult,
) -> None:
    """Verify an identify-query derivation.

    Raises ``VerificationError`` on reject. Returns ``None`` on accept.

    Empty derivation is always rejected — if the caller couldn't
    produce a derivation, there is nothing to verify.
    """
    if not derivation:
        raise VerificationError(
            "derivation is empty; nothing to verify",
            step_index=None, rule=None,
        )

    step_output_by_id: dict[str, object] = {}

    for i, step in enumerate(derivation):
        if not known_rule(step.rule):
            raise RuleNotFoundError(
                f"unknown rule: {step.rule!r}",
                step_index=i, rule=step.rule,
            )

        # StepRef sanity: any ref must point at an earlier step that's
        # already been verified. Rules that resolve refs themselves
        # (R5) get step_output_by_id directly, but we still pre-validate
        # that any obvious top-level StepRef points at a known id.
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
            step_output_by_id=step_output_by_id,
        )

        if step.step_id is not None:
            if step.step_id in step_output_by_id:
                raise VerificationError(
                    f"duplicate step_id {step.step_id!r}",
                    step_index=i, rule=step.rule,
                )
            step_output_by_id[step.step_id] = step.output

    # Last step's output must match the claimed result.
    final = derivation[-1].output
    if final != claimed_result:
        raise VerificationError(
            f"last derivation step output does not equal claimed result",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
