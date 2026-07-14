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
  that aren't re-derivable),
  ``verify_iv_overid_numeric`` (over-identified 2SLS: the 2SLS point AND the
  Sargan over-identification test — J and its p-value — re-derived by an
  independent transcription of the closed forms from the recorded residualised
  moment matrices Z'Z / Z'x / Z'y / xx / xy / yy; rejects a tampered point, a
  forged Sargan statistic, or a corrupted moment. Its derivation terminal
  ``numeric_iv_overid_estimate`` does only metadata + structural licensing
  because the moment matrices don't fit derivation-input serialization),
  ``verify_measurement_correction_numeric`` (frontier E — the de-attenuated
  effect on a misclassified discrete outcome: the corrected point, the naive
  (attenuated) point, and det(M) re-derived by an independent transcription of
  the per-stratum confusion-matrix inversion p_true=M⁻¹p_obs from the recorded
  matrix + value-count vectors; rejects a tampered point, a non-stochastic or
  det-inconsistent matrix, a dropped stratum, or a missing arm. Its derivation
  terminal ``numeric_measurement_correction_estimate`` does only metadata +
  structural licensing because the matrix + count vectors don't fit
  derivation-input serialization),
  ``verify_exposure_measurement_correction_numeric`` (frontier E, exposure side
  — the de-attenuated effect of a misclassified binary EXPOSURE: the corrected
  point, the naive (attenuated) point, and det(M) re-derived by an independent
  transcription of the matrix method p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z) applied on
  the exposure margin, from the recorded matrix + per-stratum 2×k joint tables;
  rejects a tampered point, a non-stochastic or det-inconsistent matrix, a
  dropped stratum, an empty observed arm, or a degenerate recovered exposure
  marginal. Shares the ``numeric_measurement_correction_estimate`` terminal),
  ``verify_selection_recovery_numeric`` (§S9.1 numeric end — the ATE recovered
  from selection bias by the Bareinboim-Pearl selection-backdoor formula
  (Theorem 3.5): re-runs the sum μ(x)=Σ_{z⁺}[Σ_{z⁻} E_biased[Y|x,z,S]·P_ref(z⁻|x,z⁺)]·P_ref(z⁺)
  from the recorded per-stratum biased counts + external unbiased weight
  tables, and checks the two arms, the point, and the weight-table
  normalisation; rejects a forged point or a tampered stratum),
  ``verify_missing_data_numeric`` (§S9.2 numeric end — the back-door ATE
  recovered from data that itself has missing values by the Mohan-Pearl-Tian
  ordered factorization: re-runs the g-formula Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)
  from the recorded per-stratum {n, y_sum} conditionals + {z, count} marginal
  tables (the recovered estimate and, when present, the naive listwise foil),
  and checks the reported point, the marginal normalisation, and that no
  contributing stratum was dropped; rejects a forged point or a tampered
  stratum)
- Pre-flight data diagnostic: ``verify_type_reconciliation`` (2026-07-11,
  borrow-list #3 — re-derives every declared_type_data_mismatch verdict from
  the recorded sufficient statistics in extensions.type_reconciliation
  [n_unique / dtype_kind / observed_values] and confirms the attached gaps
  match; catches a producer that mis-classifies a column, mislabels a
  verdict, or fabricates / drops a gap)
- Discovery-layer verifier: ``verify_markov_blanket`` (2026-07-11, borrow-list
  #4 — the first per-number audit to reach the causal-discovery layer. Re-checks
  the completeness + minimality Markov-blanket definition directly on the
  returned set, recomputing every conditional-independence test from the
  recorded sufficient statistic — the correlation matrix (continuous, Fisher-Z)
  or the sparse joint contingency counts (discrete, chi-square) — with an
  independent reimplementation, without re-running the grow-shrink search;
  rejects a fabricated / trimmed blanket, a corrupted sufficient statistic, or a
  recorded test that disagrees with the recomputation)
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
    verify_exposure_measurement_correction_numeric,
    verify_identify,
    verify_iv_overid_numeric,
    verify_longitudinal_numeric,
    verify_measurement_correction_numeric,
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
from .selection_numeric_rules import verify_selection_recovery_numeric
from .missing_numeric_rules import verify_missing_data_numeric

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
    "verify_exposure_measurement_correction_numeric",
    "verify_balke_pearl_iv_bounds_result",
    "verify_identify",
    "verify_longitudinal_numeric",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_markov_blanket",
    "verify_iv_overid_numeric",
    "verify_measurement_correction_numeric",
    "verify_mediation_numeric",
    "verify_numeric",
    "verify_numeric_estimate",
    "verify_missing_data_numeric",
    "verify_missing_data_recovery",
    "verify_ovb_sensitivity",
    "verify_proximal_effect",
    "verify_proximal_numeric",
    "verify_scm_counterfactual",
    "verify_selection_recovery",
    "verify_selection_recovery_numeric",
    "verify_type_reconciliation",
]
