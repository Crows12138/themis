"""Verifier layer (slice V0).

Independent of ``themis.runtime.*``. Given a derivation and a
verification context (graph + query + optional Theta), re-runs each
named rule and confirms the derivation legitimately leads from the
premises to the claimed result.

See VERIFIER_DESIGN.md for the operational definition of 严格 this
layer is implementing.
"""
from .errors import (
    RuleNotFoundError,
    StepRefError,
    UnknownRuleInputError,
    VerificationError,
)
from .context import VerificationContext
from .verify import verify_identify

__all__ = [
    "RuleNotFoundError",
    "StepRefError",
    "UnknownRuleInputError",
    "VerificationContext",
    "VerificationError",
    "verify_identify",
]
