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
  re-derive the recoverability verdict + recovery formula) /
  ``verify_transport_sources`` (Bareinboim-Pearl transport across several
  declared source domains — re-derives the agreement verdict over the
  per-source numbers the block records, so a reported number that some
  transporting domain contradicts, and a withheld one no domain
  contradicts, are both caught) /
  ``verify_acr_decomposition`` (an IV number over an ordered dose — the
  Angrist-Imbens margin table recomputed from the per-instrument-level
  counts and sums alone, so a weight that disagrees with the data, a
  weight vector that fails to sum to one, and a suppressed monotonicity
  refutation are each rejected) /
  ``verify_identification_pattern`` (the graph-level pattern the reader is
  told the answer came from — back door with its adjustment set, front
  door with its mediators and the covariates it needs held, or the ID
  algorithm's general solution. The named sets are re-derived to satisfy
  the criterion the pattern names, by edge deletion plus the verifier's
  own m-separation rather than the producer's path enumeration; and the
  general solution is held to being general, so a back door or a front
  door that was there to be named and was not is rejected)
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
  ``verify_vector_iv_region`` (the Anderson-Rubin confidence REGION over a
  treatment vector: the inverted quadratic A/B/C, the region's shape, its
  centre, the 2SLS point and every coordinate projection re-derived from the
  recorded second moments. The shape is re-classified in the EIGENBASIS of A
  rather than by the producer's case split, and each finite projection
  endpoint is confirmed twice more — against the quadratic itself at the
  completion that minimises it, and, where the region is an ellipsoid,
  against the support function μ_j ± sqrt(r·(A⁻¹)_jj). Holds the theorem
  tying the two shape vocabularies in both directions, so a tampered
  ``shape`` and a tampered ``projections`` each fail on the other. Its
  derivation terminal ``numeric_anderson_rubin_region`` does only metadata +
  structural licensing because the moment matrices don't fit
  derivation-input serialization),
  ``verify_joint_general_id_numeric`` (a joint intervention identified by the
  set-valued ID: both reported numbers are finite differences over the
  treatment box, and the box is recorded, so the contrast is recomputed as
  all-hi minus all-lo and the K-way interaction as the alternating sum over
  all 2^K corner risks — catching a number that is internally consistent but
  does not follow from the corners the same result reports. Holds the box to
  what it claims: probabilities, distinct cells naming every treatment, and
  completeness exactly when an interaction is reported),
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
  ``verify_simex_numeric`` (the same design on a declared NONLINEAR outcome
  model, where that moment identity does not hold — simulation-extrapolation.
  Only the first of its two stages is random, and its output is the second's
  sufficient statistic, so the extrapolant's coefficients, the point at λ=−1,
  τ(−1) and the interval are all re-derived from the recorded simulation
  ladder alone, by normal equations rather than the producer's ``lstsq``, and
  without simulating anything. What cannot be re-derived is said rather than
  implied: the ladder is a seeded Monte Carlo. What CAN still be checked
  about it is — the λ=0 rung is not a simulation at all and must equal the
  reported naive point with zero replicate variance, the grid must start at
  zero and climb, and it must be long enough that the declared family is
  fitting rather than interpolating. Rejects a forged point / coefficient /
  variance, an interval that is not the recorded variance read at the
  recorded level, and a withheld interval whose stated reason is not true of
  the record. Shares the same terminal),
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
  stratum),
  ``verify_assumption_ledger`` (the disclosure surface the report assembler and
  the rendering bridge lead with: re-derives what the ledger owes from the four
  channels that feed it — the estimator's own ``numeric_estimate.assumptions``,
  load-bearing proposal edges, LLM theta priors, audited mechanisms — and
  rejects under-disclosure, a fabricated estimator entry, a line handed to a
  caller who supplied nothing, an unsorted ledger, a summary whose counts do
  not match, or an entry whose severity contradicts its layer — the layer says
  which part of the answer stops being true and the severity grades how badly
  that kills it, so the second follows from the first and is re-derived here
  rather than believed),
  ``verify_cluster_inference`` (the unit of independence: holds the run-level
  ``estimation_context.cluster`` against what the estimator declares it did
  with that column, so an interval computed under a clustered run cannot stay
  silent about it — silence reads as i.i.d. inference the run gave no basis
  for — and a dispatch-written ``bootstrap`` block cannot claim
  cluster-robustness the estimator never corroborated, name a different column
  than the run resolved, or appear with no cluster column resolved at all),
  ``verify_outcome_error`` (the one block that changes no number: a declared
  classical error on a continuous outcome costs precision but not bias, so the
  audit is of the split it reports — every scalar re-derived from the recorded
  Σ_D, Cov(D,Y), Var(Y) and σ²_v — of whether that split was taken on the design
  the estimate actually fitted, and of whether its premises reach the
  estimate's declared assumptions, the non-differential-error premise being the
  entire reason no correction was applied)
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
- Discovery-layer verifier: ``verify_notears_fit`` (2026-08-30 — the first
  audit of a CONTINUOUS search. A local optimum found by L-BFGS-B cannot be
  replayed, so this does not re-run it: the objective and its gradient depend
  on the data only through the Gram matrix, which makes a d×d matrix a
  sufficient statistic for the whole problem. Recomputes the acyclicity
  residual, the objective, the first-order residual, the edges at the declared
  threshold and the varsortability of the graph they make, with a second
  transcription of the matrix exponential as a non-negative power series;
  rejects a fabricated residual, an edge list that is not what the weights
  say, and a scale diagnostic that contradicts its own edge set. Global
  optimality is NOT certified, and the artifact does not claim it)
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
- Bounds-result verifiers — one per implemented BoundsMethod producer:
  * ``verify_manski_tamer_bounds_result`` re-derives the Manski-Tamer
    producer's symbolic expressions independently from program shape +
    the monotonicity declaration in ``program.extensions``.
  * ``verify_manski_natural_bounds_result`` re-derives the
    Phase 12 Manski-natural producer's canonical assumption-free
    expressions; rejects non-empty assumption tuples (Manski natural
    is by definition the no-assumption baseline).
  * ``verify_balke_pearl_iv_bounds_result`` audits the row's facts —
    estimand, the named instrument against what the graph offers, the
    iv1/iv2/iv3 assumption tag set — and holds the lower/upper
    expressions only to naming what they render.
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
    verify_acr_decomposition,
    verify_e_value,
    verify_effect_structural,
    verify_combined_measurement_correction_numeric,
    verify_exposure_measurement_correction_numeric,
    verify_identification_pattern,
    verify_identify,
    verify_iv_overid_numeric,
    verify_joint_general_id_numeric,
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
    verify_transport_sources,
    verify_vector_iv_region,
)
from .bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
    verify_manski_natural_bounds_result,
    verify_manski_tamer_bounds_result,
)
from .assumption_ledger_rules import verify_assumption_ledger
from .cluster_inference_rules import verify_cluster_inference
from .outcome_error_rules import verify_outcome_error
from .fingerprint_rules import verify_fingerprints_agree
from .type_reconciliation_rules import verify_type_reconciliation
from .markov_blanket_rules import verify_markov_blanket
from .notears_rules import verify_notears_fit
from .simex_rules import verify_simex_numeric
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
    "verify_assumption_ledger",
    "verify_causation",
    "verify_causation_numeric",
    "verify_cause",
    "verify_cluster_inference",
    "verify_outcome_error",
    "verify_counterfactual",
    "verify_counterfactual_cell_numeric",
    "verify_counterfactual_conjunction",
    "verify_ctf_conjunction_numeric",
    "verify_dose_response_curve",
    "verify_acr_decomposition",
    "verify_e_value",
    "verify_effect_structural",
    "verify_combined_measurement_correction_numeric",
    "verify_exposure_measurement_correction_numeric",
    "verify_balke_pearl_iv_bounds_result",
    "verify_identification_pattern",
    "verify_identify",
    "verify_longitudinal_numeric",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_markov_blanket",
    "verify_notears_fit",
    "verify_orientation_propagation",
    "verify_orientation_questions",
    "verify_orientation_session",
    "verify_orientation_ledger_export",
    "verify_iv_overid_numeric",
    "verify_joint_general_id_numeric",
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
    "verify_simex_numeric",
    "verify_transport_sources",
    "verify_type_reconciliation",
    "verify_vector_iv_region",
]
