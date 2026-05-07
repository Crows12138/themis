"""Verifier layer (slice V0+).

Independent of ``themis.runtime.*``. Given a derivation and a
verification context (graph + query + optional Theta), re-runs each
named rule and confirms the derivation legitimately leads from the
premises to the claimed result.

Public surface (re-exports from sub-modules):

- Per-query-kind verifiers: ``verify_cause`` / ``verify_assoc`` /
  ``verify_identify`` / ``verify_effect_structural`` /
  ``verify_numeric`` / ``verify_numeric_estimate`` /
  ``verify_counterfactual``
- Bounds-result verifiers (iter 126/127):
  * ``verify_manski_tamer_bounds_result`` (iter 126) re-derives the
    iter 119 Manski-Tamer producer's symbolic expressions
    independently from program shape + the monotonicity declaration
    in ``program.extensions``.
  * ``verify_manski_natural_bounds_result`` (iter 127) re-derives the
    Phase 12 Manski-natural producer's canonical assumption-free
    expressions; rejects non-empty assumption tuples (Manski natural
    is by definition the no-assumption baseline).
- ``VerificationContext`` — the (graph, query, theta) bundle that
  every verifier reads
- Serialization round-trip: ``derivation_to_dict`` /
  ``derivation_from_dict`` / ``context_to_dict`` /
  ``context_from_dict``; raises ``DerivationSerializationError`` on
  malformed input
- Errors — ``VerificationError`` (base) + the three input-class
  failures: ``RuleNotFoundError`` / ``UnknownRuleInputError`` /
  ``StepRefError``

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
from .serialization import (
    DerivationSerializationError,
    context_from_dict,
    context_to_dict,
    derivation_from_dict,
    derivation_to_dict,
)
from .verify import (
    verify_assoc,
    verify_cause,
    verify_counterfactual,
    verify_effect_structural,
    verify_identify,
    verify_numeric,
    verify_numeric_estimate,
)
from .bounds_rules import (
    verify_manski_natural_bounds_result,
    verify_manski_tamer_bounds_result,
)

__all__ = [
    "DerivationSerializationError",
    "RuleNotFoundError",
    "StepRefError",
    "UnknownRuleInputError",
    "VerificationContext",
    "VerificationError",
    "context_from_dict",
    "context_to_dict",
    "derivation_from_dict",
    "derivation_to_dict",
    "verify_assoc",
    "verify_cause",
    "verify_counterfactual",
    "verify_effect_structural",
    "verify_identify",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_numeric",
    "verify_numeric_estimate",
]
