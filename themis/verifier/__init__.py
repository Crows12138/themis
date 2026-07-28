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
  ``verify_scm_counterfactual_numeric`` (the DATA end: re-solves each
  node's OLS from the recorded moment matrices and re-runs abduction-
  action-prediction from the fitted slopes + the unit) /
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
  ``verify_counterfactual_cell_numeric`` (the single binary counterfactual
  cell re-solved from the reported empirical joint + interventional risk),
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
  ``verify_combined_measurement_correction_numeric`` (frontier E, both channels
  — the doubly corrected effect when the exposure AND the outcome are
  misclassified: the corrected point, the naive point and each channel's det
  re-derived by an independent transcription of the two-sided inversion
  p_true(z)=M_x⁻¹p_obs(z)(M_y⁻¹)ᵀ from the two recorded matrices + the same
  per-stratum 2×k joint tables. Adds one check the single-channel verifiers
  cannot make — the recorded det of the composed map must equal
  det(M_x)^k·det(M_y)², which catches a joint determinant carried over from a
  different pair of matrices — and rejects any claim of differential
  misclassification, which the two-sided factorisation does not license. Shares
  the same terminal),
  ``verify_regression_calibration_numeric`` (continuous mismeasurement — the
  de-attenuated slope of a continuously-mismeasured EXPOSURE by regression
  calibration: the corrected point, the naive (attenuated) slope, and the
  reliability λ=1−σ²_u/Var(W|Z) re-derived by an independent transcription of the
  moment correction β=(Σ_WZ−E)⁻¹Cov((W,Z),Y) from the recorded design covariance
  matrix + σ²_u; rejects a forged point / naive / reliability, a non-symmetric
  covariance, a degenerate reliability (σ²_u≥Var(W|Z)) that shipped a point, or a
  slope vector inconsistent with the covariance. Shares the
  ``numeric_measurement_correction_estimate`` terminal),
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
- Discovery-layer verifier: ``verify_orientation_propagation`` (2026-07-17,
  interactive equivalence-class resolution — Phase 1. Re-derives the Meek
  closure of a CPDAG under direction constraints from the recorded input CPDAG
  + constraints, with a second standalone transcription of rules R1-R4 and the
  constraint-application / conflict-detection logic — no producer call, no
  causal-learn. Rejects an ``oriented`` set that disagrees with the independent
  closure, a data-contradicting constraint that was silently applied instead of
  surfaced as a conflict, or an unjustified provenance entry)
- Discovery-layer verifier: ``verify_orientation_questions`` (2026-07-17,
  interactive equivalence-class resolution — Phase 2. Audits the compiled,
  leverage-ranked orientation question set: re-runs each remaining edge's two
  Meek cascades from the recorded post-propagation CPDAG with a second
  transcription of R1-R4, and checks every ``leverage`` / ``guaranteed`` /
  ``unlocks`` number, that conflicts are echoed exactly, that there is one
  question per remaining edge, and that the ranking is by descending leverage —
  no producer call)
- Discovery-layer verifier: ``verify_orientation_session`` (2026-07-17,
  interactive equivalence-class resolution — Phase 3. Audits an
  ``orientation_session`` artifact: delegates to ``verify_orientation_propagation``
  and ``verify_orientation_questions`` for the embedded Phase 1 / Phase 2 dicts,
  then certifies the session glue — that the constraints are the latest-wins
  projection of the recorded answers, the embedded artifacts are the session's
  own, ``deferred`` is exactly the still-open unknowns, the source trail credits
  every applied answer with its true entailment and no rejected one, and the
  status is correct — all re-derived from the answers, no producer call)
- Discovery-layer verifier: ``verify_orientation_ledger_export`` (2026-07-17,
  interactive equivalence-class resolution — Phase 5, ledger wiring. Audits an
  ``orientation_ledger_export`` artifact: delegates the embedded session to
  ``verify_orientation_session``, then independently re-derives every oriented
  edge's ledger ``source`` — with a second transcription of the ``llm_proposal``
  taint propagation through the Meek closure — and checks the ``edges``,
  ``proposal_edges``, ``cause_statements`` sources, and ``graph_learned_from_data``
  match; under-disclosure of a proposal-rooted edge is what it catches)
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
    verify_counterfactual_cell_numeric,
    verify_counterfactual_conjunction,
    verify_ctf_conjunction_numeric,
    verify_dose_response_curve,
    verify_e_value,
    verify_effect_structural,
    verify_combined_measurement_correction_numeric,
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
    verify_regression_calibration_numeric,
    verify_scm_counterfactual,
    verify_scm_counterfactual_numeric,
    verify_selection_recovery,
)
from .bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
    verify_manski_natural_bounds_result,
    verify_manski_tamer_bounds_result,
)
from .type_reconciliation_rules import verify_type_reconciliation
from .markov_blanket_rules import verify_markov_blanket
from .orientation_rules import verify_orientation_propagation
from .orientation_question_rules import verify_orientation_questions
from .orientation_session_rules import verify_orientation_session
from .orientation_ledger_rules import verify_orientation_ledger_export
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
    "verify_counterfactual_cell_numeric",
    "verify_counterfactual_conjunction",
    "verify_ctf_conjunction_numeric",
    "verify_dose_response_curve",
    "verify_e_value",
    "verify_effect_structural",
    "verify_combined_measurement_correction_numeric",
    "verify_exposure_measurement_correction_numeric",
    "verify_balke_pearl_iv_bounds_result",
    "verify_identify",
    "verify_longitudinal_numeric",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_markov_blanket",
    "verify_orientation_propagation",
    "verify_orientation_questions",
    "verify_orientation_session",
    "verify_orientation_ledger_export",
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
    "verify_regression_calibration_numeric",
    "verify_scm_counterfactual",
    "verify_scm_counterfactual_numeric",
    "verify_selection_recovery",
    "verify_selection_recovery_numeric",
    "verify_type_reconciliation",
]
