"""Verifier error hierarchy.

Every reject the verifier produces is an instance of ``VerificationError``
or a subclass. Subclasses carry structured detail so callers (tests, a
future CLI) can reason about *why* rejection happened without parsing
messages.
"""
from __future__ import annotations


class VerificationError(Exception):
    """Base class. A derivation that raises this is rejected."""

    def __init__(
        self,
        message: str,
        *,
        step_index: int | None = None,
        rule: str | None = None,
    ):
        super().__init__(message)
        self.step_index = step_index
        self.rule = rule


class RuleNotFoundError(VerificationError):
    """The derivation cites a rule name the verifier does not implement."""


class UnknownRuleInputError(VerificationError):
    """A rule input dict is missing a required key, or has an unexpected
    key. The rule may also raise this when a value is the wrong type."""


class StepRefError(VerificationError):
    """A ``StepRef`` points at a missing / future / wrong-typed step."""


class RuleCheckFailed(VerificationError):
    """The rule's own re-computation does not match the claimed output,
    or its preconditions are violated (e.g. backdoor_criterion on a Z
    that contains a descendant of X)."""
