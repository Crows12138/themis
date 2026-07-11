"""Verifier layer (slice V0+).

Independent of ``themis.runtime.*``. Given a derivation and a
verification context (graph + query + optional Theta), re-runs each
named rule and confirms the derivation legitimately leads from the
premises to the claimed result.

Public surface (re-exports from sub-modules):

- Per-query-kind verifiers: ``verify_cause`` / ``verify_assoc`` /
  ``verify_identify`` / ``verify_effect_structural`` /
  ``verify_numeric`` / ``verify_numeric_estimate`` /
  ``verify_counterfactual`` / ``verify_causation`` (PN/PS/PNS,
  Tian-Pearl 2000 — independently re-derives the observational joint
  from theta and the Tian-Pearl bounds/points) /
  ``verify_scm_counterfactual`` (linear-SCM point, Pearl Primer §4.2 —
  independently re-runs abduction-action-prediction from the edge
  coefficients + the unit's observations) /
  ``verify_counterfactual_conjunction`` (general counterfactual
  identification, Shpitser-Pearl ID* R-336 — pins the id_star terminal
  rule and runs an independent Monte-Carlo semantic probe: samples SCMs
  consistent with the ADMG, computes the true P(γ) by counterfactual MC
  over a shared exogenous background, and rejects a formula that computes
  the wrong number) /
  ``verify_ovb_sensitivity`` (Cinelli-Hazlett OVB sensitivity — a second
  independent transcription of the robustness-value / partial-R² / bound
  closed forms, recomputed from the recorded t-value + dof + benchmark
  partial R²s) /
  ``verify_e_value`` (VanderWeele-Ding E-value sensitivity — the
  risk-ratio-scale sibling of the OVB block; a second independent
  transcription of E = RR + √(RR·(RR−1)), re-deriving the risk ratio and
  both E-values from the audited headline ATE + the recorded conversion
  input (baseline rate / outcome SD), so a tampered E-value is rejected) /
  ``verify_dose_response_curve`` (dose-response curve construction
  invariants — the curve values come from a black-box EconML fit and can't
  be re-derived, but the array (the answer) gets a semantic audit the
  metadata-only path skips: one point per sampling point with matching x,
  reference-point effect 0, and every point inside its own interval; catches
  a corrupted / reordered curve or a point escaping its CI) /
  ``verify_selection_recovery`` (Bareinboim-Pearl recoverability from
  selection bias — re-derives the selection-backdoor conditions and the
  Theorem-3.5 recovery formula against the graph, validates the returned
  adjustment-set witness, and re-searches to confirm a negative verdict) /
  ``verify_missing_data_recovery`` (Mohan-Pearl-Tian recoverability from
  missing data — rebuilds the m-graph from the declared indicators,
  reclassifies MCAR/MAR/MNAR, and re-searches the ordered factorization to
  re-derive the recoverability verdict + recovery formula)
- Numeric-end verifiers (data-based overlays that re-derive the reported
  numbers from the recorded sufficient statistics, not the raw data):
  ``verify_proximal_effect`` / ``verify_proximal_numeric`` (Miao-2018
  proximal do-effect), ``verify_causation_numeric`` (PN/PS/PNS plug-in),
  ``verify_ctf_conjunction_numeric`` (ID*/IDC* counterfactual conjunction),
  ``verify_mediation_numeric`` (the numbers riding on a mediation structural
  result: the VanderWeele ratio-scale four-way split re-derived from the
  recorded logistic coefficients, plus construction-identity checks on the
  difference-scale four-way and the Imai NDE/NIE decomposition whose
  simulation-based values aren't re-derivable),
  ``verify_longitudinal_numeric`` (the time-varying strategy contrast riding
  on a g-formula / sequential-back-door identification: the IPW-MSM contrast
  re-derived from the recorded marginal-structural-model coefficients, plus
  construction-identity checks on the black-box g-formula Monte-Carlo means
  that aren't re-derivable)
- Pre-flight data diagnostic: ``verify_type_reconciliation`` (2026-07-11,
  borrow-list #3 — re-derives every declared_type_data_mismatch verdict from
  the recorded sufficient statistics in extensions.type_reconciliation
  [n_unique / dtype_kind / observed_values] and confirms the attached gaps
  match; catches a producer that mis-classifies a column, mislabels a
  verdict, or fabricates / drops a gap)
- Discovery-layer verifier: ``verify_markov_blanket`` (2026-07-11, borrow-list
  #4 — the first per-number audit to reach the causal-discovery layer. Re-checks
  the completeness + minimality Markov-blanket definition directly on the
  returned set, recomputing every Fisher-Z conditional-independence test from
  the recorded correlation matrix [the complete sufficient statistic under joint
  continuity] with an independent reimplementation, without re-running the
  grow-shrink search; rejects a fabricated / trimmed blanket, a corrupted
  correlation matrix, or a recorded test that disagrees with the recomputation)
- Bounds-result verifiers (iter 126/127/130) — trilogy complete for
  the 3 implemented BoundsMethod producers:
  * ``verify_manski_tamer_bounds_result`` (iter 126) re-derives the
    iter 119 Manski-Tamer producer's symbolic expressions
    independently from program shape + the monotonicity declaration
    in ``program.extensions``.
  * ``verify_manski_natural_bounds_result`` (iter 127) re-derives the
    Phase 12 Manski-natural producer's canonical assumption-free
    expressions; rejects non-empty assumption tuples (Manski natural
    is by definition the no-assumption baseline).
  * ``verify_balke_pearl_iv_bounds_result`` (iter 130) audits the
    canonical reference-shape lower/upper expressions, the
    iv1/iv2/iv3 assumption tag set, and that target/treatment
    predicates from the query appear in the expression.
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
    verify_causation,
    verify_causation_numeric,
    verify_cause,
    verify_counterfactual,
    verify_counterfactual_conjunction,
    verify_ctf_conjunction_numeric,
    verify_dose_response_curve,
    verify_e_value,
    verify_effect_structural,
    verify_identify,
    verify_longitudinal_numeric,
    verify_mediation_numeric,
    verify_missing_data_recovery,
    verify_numeric,
    verify_numeric_estimate,
    verify_ovb_sensitivity,
    verify_proximal_effect,
    verify_proximal_numeric,
    verify_scm_counterfactual,
    verify_selection_recovery,
)
from .bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
    verify_manski_natural_bounds_result,
    verify_manski_tamer_bounds_result,
)
from .type_reconciliation_rules import verify_type_reconciliation
from .markov_blanket_rules import verify_markov_blanket

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
    "verify_causation",
    "verify_causation_numeric",
    "verify_cause",
    "verify_counterfactual",
    "verify_counterfactual_conjunction",
    "verify_ctf_conjunction_numeric",
    "verify_dose_response_curve",
    "verify_e_value",
    "verify_effect_structural",
    "verify_balke_pearl_iv_bounds_result",
    "verify_identify",
    "verify_longitudinal_numeric",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_markov_blanket",
    "verify_mediation_numeric",
    "verify_numeric",
    "verify_numeric_estimate",
    "verify_missing_data_recovery",
    "verify_ovb_sensitivity",
    "verify_proximal_effect",
    "verify_proximal_numeric",
    "verify_scm_counterfactual",
    "verify_selection_recovery",
    "verify_type_reconciliation",
]
