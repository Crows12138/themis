"""Numerical estimation layer (Phase 7 / 8.1 / 8.2 / 14).

Public contract: pandas DataFrame in, point estimate / CI / sensitivity
/ DAG-skeleton out. The kernel's existing JSON-in / JSON-out
identification layer is not disturbed — data flows through a separate
Python API (``themis.estimate``) so JSON callers that only need
identification keep the v1.0 kernel surface verbatim.

Landed scope:

- Phase 7.1-7.4 — ATE estimators: ``estimate_backdoor_ate`` /
  ``estimate_frontdoor_ate`` / ``estimate_iv_ate`` /
  ``estimate_mediation`` returning ``BackdoorEstimate`` /
  ``FrontdoorEstimate`` / ``IVEstimate`` / ``MediationEstimate``
- ``anderson_rubin_confidence_set`` returning
  ``ARConfidenceSet``: the Anderson-Rubin (1949) weak-identification-robust
  confidence set for the single-instrument IV coefficient, always attached
  to ``IVEstimate``. Valid regardless of first-stage strength — unlike the
  bootstrap CI — and honestly returns an unbounded set when the data cannot
  bound the effect. ``anderson_rubin_overid_set`` returning
  ``OverIDARConfidenceSet`` is its multi-instrument (q ≥ 2) counterpart,
  attached to ``OverIDIVEstimate``: still one quadratic inequality (the
  q-dimensional projection only changes the coefficients), with critical value
  ``q·F(q, m)``. ``robust_anderson_rubin_overid_set`` returning
  ``RobustARConfidenceSet`` is the heteroskedasticity-robust (Stock-Wright S /
  Kleibergen) version, valid under weak identification AND heteroskedasticity /
  clustering at once: it inverts ``AR_r(β0) = n·ḡ'Ŝ(β0)⁻¹ḡ ~ χ²(q)`` with the
  β0-dependent robust weight, via exact polynomial root-finding (the set can be
  bounded / disconnected / whole-line / empty / a union of pieces).
  ``stratified_anderson_rubin_set`` returning ``StratifiedARSet`` is the same
  inversion on the STRATIFIED Wald's own moment, attached to ``IVEstimate``
  wherever that estimator ran. The three sets above all residualise on
  ``[1, W]`` — the additive projection that gives 2SLS its weighting — so
  their point is the linear IV coefficient and they belong to a different
  estimand; this one is a pure function of the stratum table, so its point
  IS the stratified Wald's, and its variance is arm-specific rather than
  pooled.
- Over-identified IV — ``estimate_iv_overid`` (returning ``OverIDIVEstimate``
  with a ``SarganTest``): multi-instrument 2SLS (q ≥ 2 instruments valid under
  a shared conditioning set) plus the Sargan (1958) over-identification test,
  whose small p-value REFUTES the instruments' joint validity — the linear /
  continuous analogue of the Balke-Pearl instrumental inequalities. The point,
  the Sargan J, and the joint first-stage F are closed forms of the recorded
  residualised second moments, so the verifier re-derives them (with its own
  independent transcription) without the raw data.
- Measurement-error correction — ``estimate_measurement_correction`` (returning
  ``MeasurementCorrectionEstimate``): de-attenuates a MISCLASSIFIED discrete
  outcome by inverting a validated confusion matrix per back-door stratum
  (``p_true = M⁻¹ p_obs``; Rogan-Gladen 1978 for the binary case). Under
  non-differential misclassification a single matrix applies everywhere; under
  DIFFERENTIAL misclassification (``differential=True``) a distinct matrix per
  exposure arm (detection bias) is inverted within each arm. The corrected point,
  the naive (attenuated) point, and each det(M) are closed forms of the recorded
  matrix / matrices + per-stratum value-count vectors, so the verifier re-inverts
  them independently without the raw data.
- Exposure measurement-error correction —
  ``estimate_exposure_measurement_correction`` (returning
  ``ExposureMeasurementCorrectionEstimate``): the same de-attenuation for a
  MISCLASSIFIED BINARY EXPOSURE via the matrix method (Barron 1977, Greenland
  1988, Marshall 1990) — invert M on the exposure margin of the (X, Y) joint per
  back-door stratum, recover the true joint, then standardise the recovered true
  exposure. Under DIFFERENTIAL misclassification (``differential=True``) the axis
  is named by ``differential_by``: by the outcome (recall bias, the default — a
  distinct matrix per outcome level inverts that outcome's column) or by a
  back-door COVARIATE (the rate varies by e.g. site — a distinct M_z per covariate
  level inverts every column in that stratum). The recovered exposure marginal is
  itself an inversion (no naive/det shortcut), so the verifier re-derives the point
  from the recorded matrix / matrices + per-stratum 2xk joint tables. Deferred:
  multi-level exposure, and a matrix jointly differential in the outcome AND a
  covariate.
- Combined measurement-error correction —
  ``estimate_combined_measurement_correction`` (returning
  ``CombinedMeasurementCorrectionEstimate``): both channels misclassified at
  once. Correcting one and shipping the point leaves the other's bias in the
  number, so the two inversions are composed on the SAME per-stratum 2xk joint,
  ``P_true = M_x⁻¹ P_obs (M_y⁻¹)ᵀ``. That factorisation needs a premise neither
  single-channel correction makes — the two error mechanisms are independent
  given the truth, ``X ⊥ Y | (X*, Y*, Z)`` — which is named in the assumption
  list on its own. Deferred, structurally rather than budgetarily: a DIFFERENTIAL
  matrix on either channel, since the level selecting one matrix is the quantity
  the other channel mismeasures and the observed table is then not a two-sided
  product.
- Continuous mismeasurement — ``estimate_regression_calibration`` (returning
  ``RegressionCalibrationEstimate``): the CONTINUOUS counterpart of the confusion-
  matrix method — de-attenuates one or more continuously-mismeasured design
  columns under classical additive error (``W = V + U``, known error variance
  σ²_u) by the regression-calibration moment correction
  ``β_true = (Σ_obs − E)⁻¹ Σ_obs b_naive``, ``E = diag(σ²_u at the mismeasured
  columns)`` (Carroll et al. 2006; Rosner-Willett-Spiegelman 1989). The
  mismeasured column may be the EXPOSURE (regression dilution → attenuation) and/
  or a back-door COVARIATE (imperfect adjustment → residual confounding, a bias
  in either direction) — ``error_variance`` accepts a scalar (exposure) or a
  ``{name: σ²_u}`` dict. The corrected slope, the naive (biased) slope, and each
  reliability ``λ_v = 1 − σ²_uv/Var(V|rest)`` (the continuous analogue of det(M))
  are closed forms of the recorded design covariance + error variances, so the
  verifier re-derives them without the raw data. Deferred: Berkson /
  differential error.
- The same mismeasured EXPOSURE where the wanted coefficient lives in a
  NONLINEAR outcome model — ``estimate_simex`` (returning ``SimexEstimate``).
  That moment correction is an identity about a linear Y, so on a logistic one
  it does not compute a rougher version of the same number; it computes a
  different one, and only the caller can say which they meant. Cook & Stefanski
  (1994) in two stages: simulate the measurement getting WORSE along a declared
  λ ladder, then extrapolate the declared family back to λ = −1, where the error
  variance would be zero. Only the first stage is random, and its output is the
  second's sufficient statistic — one ``SimexGridPoint`` per rung, carrying
  everything the extrapolation needs from it and nothing that would have to be
  recomputed to check it — so the ladder travels on the envelope and
  ``verify_simex_numeric`` re-derives the coefficients, the point, τ(−1) and the
  interval from it without simulating anything. The interval is Stefanski &
  Cook's (1995) τ(λ) = σ̄²(λ) − s²(λ) extrapolated the same way, so no bootstrap
  wraps the procedure. Declared: one mismeasured exposure (perturbing two needs
  their error covariance), and an interval that covers sampling variability but
  not the extrapolant's approximation error — which is a bias, and no variance
  contains a bias.
- Continuous mismeasurement of the OUTCOME — ``assess_outcome_error`` (returning
  ``OutcomeErrorAssessment``): the third role, and the only one that costs no
  bias. A classical additive error on a continuous outcome (``Y = Y* + V``,
  ``E[V|D] = 0``) leaves every conditional mean unchanged, so no estimand here
  moves and there is nothing to de-attenuate — the ordinary number stands. What
  the known σ²_v buys is the price: ``Var(Y|D) = Var(Y*|D) + σ²_v`` splits the
  residual variance into signal and measurement noise, and
  ``sqrt(Var(Y|D)/Var(Y*|D))`` is the factor by which the noise widens every
  least-squares interval on that design — the uncertainty more subjects cannot
  buy back. It composes with the exposure-side correction rather than displacing
  it. Refuses a discrete outcome (that is misclassification, which DOES attenuate
  and IS correctable) and a σ²_v that does not fit under the observed residual
  variance (which refutes the very independence premise the point rests on).
  WHICH design is ``OutcomeErrorDesign``, a closed vocabulary of three, because
  every difference between the routes is a fact about the design: which residual
  absorbs the noise (the back-door and front-door projections, or the STRUCTURAL
  residual around the supplied β̂ on the instrumental-variable route), which
  variable the premise is about (the design, or the INSTRUMENTS — one premise
  each, since an over-identified system assumes them separately), and whether the
  reported factor is the cost or a CEILING on it (the front-door influence
  function splits the variance across terms and only one carries the outcome
  residual, so there the same arithmetic overstates). The half of this that can
  refuse — ``check_outcome_error_declaration`` — is separate because its answer
  can stop a query and so must be settled before any estimator runs, while the
  price cannot be taken until there is an answer to price.
- Doubly-robust ATE — ``estimate_ipw_ate`` (returning ``IPWEstimate``),
  ``estimate_aipw_ate`` (returning ``AIPWEstimate``), and
  ``estimate_tmle_ate`` (returning ``TMLEEstimate``), opt-in via
  ``options.ate_estimator`` on the backdoor path. IPW weights by the
  propensity (single-robust on the treatment model); AIPW is the
  augmented / doubly-robust estimator — consistent if EITHER the outcome
  regression OR the propensity model is correct (Robins-Rotnitzky-Zhao
  1994; Bang & Robins 2005); TMLE is the targeted-substitution
  doubly-robust estimator (van der Laan & Rose 2011) — asymptotically
  equivalent to AIPW but a bounded plug-in that respects [0,1] and is
  steadier near positivity violations. All three carry an analytic
  influence-function CI (cluster-robust when a cluster column is set) and
  disclose the positivity / overlap picture via ``PropensitySummary``
  (raw propensity range + how many units were Winsorized).
- Phase 7.5 — Controlled Direct Effect at fixed M=m*:
  ``estimate_cde`` returning ``CDEEstimate``. Plug-in g-formula
  on a sklearn outcome model; complements the Imai NDE/NIE path
  with the policy-relevant "what if we forced M to this level?"
  contrast (VanderWeele 2015 ch.2.3.3).
- Joint interventions — ``estimate_joint_effect`` returning
  ``JointEffectEstimate``: the joint g-formula contrast
  E[Y|do(A=a,B=b)] − E[Y|do(A=a',B=b')] over a SET of binary treatments
  plus the additive-scale treatment×treatment interaction
  (Hernán & Robins 2020 ch.13; VanderWeele 2015 ch.14). Identified via
  the generalized (treatment-set) back-door criterion.
- Phase 7.5+ — Multi-mediator chain CDE:
  ``estimate_cde_chain`` returning ``CDEChainEstimate``. Extends the
  single-M CDE above to N mediators X→M_1→...→M_n→Y, fixing
  each M_i at a chosen reference (VanderWeele 2015 ch.5).
- Ratio-scale four-way decomposition — ``estimate_four_way_ratio``
  returning ``FourWayRatioEstimate``, over the oracles
  ``four_way_ratio_decomposition`` (binary mediator, §3.4) and
  ``four_way_ratio_decomposition_continuous`` (continuous mediator, §3.3),
  both returning ``FourWayRatioComponents``. VanderWeele's CDE / INTref /
  INTmed / PIE split on the EXCESS RELATIVE RISK scale for a binary outcome
  (VanderWeele 2014, eAppendix §3.4/§3.3). Unlike the difference-scale
  ``four_way_decomposition`` (a pure computation over standardized cell
  means), the ratio-scale components are non-collapsible functions of the
  logistic outcome coefficients; the mediator model is logistic (binary
  mediator) or linear-with-residual-variance (continuous mediator). Surfaced
  in the kernel mediation dispatch as a ``four_way_ratio`` block when the
  outcome is binary.
- Phase 9 §T9.2 — transport-numeric ATE via post-
  stratification (Cole & Stuart 2010 §3): ``estimate_transport``
  returning ``TransportEstimate``. Source data + target marginal
  P(Z) → reweighted ATE in target population. Supports one OR more
  adjustment variables (joint post-stratification over the Z set);
  multi-source transport and IPSW (Westreich 2017) follow in §T9.3+.
- Phase 7.L — g-methods for TIME-VARYING treatments:
  ``estimate_longitudinal_gformula`` returning
  ``LongitudinalGFormulaEstimate``. The parametric (Monte-Carlo)
  g-formula / g-computation (Hernán & Robins, *What If*, ch.21):
  fits the covariate-transition models L_k | history and the outcome
  model Y | full history, simulates forward under always-treat vs
  never-treat strategies, and contrasts E[Y_{ā=1}] − E[Y_{ā=0}].
  This is the estimator for time-varying confounding that is itself
  affected by past treatment — the structure where ordinary
  regression adjustment is biased. Binary treatment, K time points,
  percentile-bootstrap CI.
  An INDEPENDENT route to the same estimand —
  ``estimate_longitudinal_ipw_msm`` returning
  ``LongitudinalIPWMSMEstimate`` — fits the TREATMENT process instead of
  the covariate/outcome models: per-time propensity models supply IP-of-
  treatment weights (stabilized by default), then a weighted marginal
  structural mean model E[Y_{ā}] = β0 + Σ_k β_k·a_k gives the strategy
  contrast (Robins 2000; Hernán & Robins ch.12/17). Misspecified in a
  different way than the g-formula, so agreement between the two is strong
  evidence the estimate is right.
- Phase 8.1 — discovery: ``discover_graph`` (PC / FCI / GES / GRaSP /
  LiNGAM via causal-learn, one ``AlgorithmSpec`` registry entry each)
  returning ``DiscoveryResult`` + ``discovery_to_kernel_ast`` adapter.
  ``algorithm="auto"`` runs a deterministic diagnostics-driven selector
  (``DataDiagnostics``); ``n_bootstrap>0`` attaches per-edge stability
  scores
- Orientation propagation — ``propagate_orientations`` (returning
  ``OrientationResult``; ``orientation_to_dict`` for the verifier;
  ``OrientationError`` on ill-formed input): the algorithm-agnostic Meek (1995)
  closure over a CPDAG under external direction constraints (a temporal order,
  a domain fact, a human/LLM answer). Applies rules R1-R3 to a fixpoint on the
  FIXED skeleton — no re-run of the discovery algorithm — and does two things a
  re-run does not: it FLAGS (rather than silently applies) a constraint that
  contradicts a data-established collider, and it records per-edge provenance
  tracing each propagated orientation back to the root constraints it rests on.
  CPDAG scope (causal sufficiency), where R1-R4 are applied to a fixpoint;
  parity-checked against causal-learn's reference Meek in the test suite
- Orientation question compiler — ``compile_orientation_questions`` (returning
  ``QuestionSet`` of ``OrientationQuestion``; ``question_set_to_dict`` for the
  verifier): Phase 2 of interactive equivalence-class resolution. Turns a Phase 1
  ``OrientationResult`` into the ranked set of questions to put to the human /
  LLM next — conflicts to adjudicate first, then one leverage-ranked question per
  still-undetermined edge, where leverage is the best-case Meek cascade an answer
  triggers (measured with the Phase 1 propagation engine). Audited by
  ``verify_orientation_questions``
- Orientation resolution session — ``start_orientation_session`` /
  ``ingest_orientation_answers`` (returning ``OrientationSession`` of
  ``OrientationAnswer``; ``OrientationSessionError`` on ill-formed input;
  ``next_questions`` for the askable subset; ``session_to_dict`` for the
  verifier): Phase 3 of interactive equivalence-class resolution — the loop.
  Event-sourced: it stores the input CPDAG + the ordered answers and replays the
  Phase 1 closure, re-compiling the Phase 2 questions over what remains. An
  answer makes one claim about a pair — a direction (a constraint), an adjacency
  polarity (``"present"`` / ``"absent"``, feeding the CI-side / drop-edge conflict
  detection, surfaced not applied), or nothing (``direction=None`` and
  ``adjacency=None``) → the edge is *deferred* (unknown escape, never re-asked);
  a later answer for a pair replaces an earlier one, latest-wins across all three
  kinds (per-turn adjacency answers override the start-time asserted-set base);
  each applied directional answer is recorded with its source and the edges it
  entailed. ``status`` is ``resolved`` / ``open`` / ``blocked``. Audited by
  ``verify_orientation_session``
- Orientation ledger export — ``orientation_ledger_export``: bridges a resolved
  session into the query-side assumption ledger. Maps each oriented edge to the
  ``source`` string the ``data_gap_report`` machinery recognises, with the
  ``llm_proposal`` taint propagated through the Meek closure (an edge forced from
  an LLM-proposed answer is disclosed ``llm_proposal`` too), and emits
  source-annotated ``cause_statements`` so the resolved graph, dropped into a
  program, fires ``UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH`` unchanged. Audited by
  ``verify_orientation_ledger_export``
- Phase 8.2 — sensitivity: ``e_value_for_risk_ratio`` /
  ``e_value_from_ate_binary`` / ``e_value_from_ate_continuous``
  (Chinn 2000 SMD→RR) returning ``EValueResult``
  (VanderWeele 2017); auto-attached to ATE estimates (binary OR
  continuous outcome) by the dispatcher
- Omitted-variable-bias sensitivity — ``estimate_ovb_sensitivity``
  returning ``OVBSensitivity`` (with per-covariate ``OVBBenchmark``
  bounds), the regression-scale complement to the E-value (Cinelli &
  Hazlett 2020): the robustness value + partial R² + confounder-strength
  bounds for a linear-regression treatment effect. Auto-attached to
  ``backdoor_linear`` estimates; a closed form of the fit's t-value and
  dof, so the verifier re-derives it exactly.
- Phase 14 — dose-response curves via ``themis.estimate(...)`` with
  ``dose_response_*`` method options (LinearDML / CausalForestDML /
  DRLearner, opt-in)
- Phase 9 §S9.2 numeric end — recover the back-door ATE from data that
  itself has missing values: ``estimate_recovered_ate`` returning
  ``RecoveredATEEstimate``. Applies the Mohan-Pearl-Tian ordered-
  factorization recovery — the conditional E[Y|X,Z] from rows with {Y,X,Z}
  observed, the covariate marginal P(Z) from rows with {Z} observed — so
  under MAR the estimate is unbiased where naive listwise deletion is
  biased (that naive number is reported for contrast). Reached through
  ``themis.estimate`` when the program declares a missingness_indicator;
  it honours the identification verdict, refusing to produce a number when
  the estimand is not recoverable. Unlike the other estimators it does NOT
  route model columns through the NaN-forbidding data contract.
- General-ID (c-factor) plug-in — ``estimate_general_id_ate`` returning
  ``GeneralIdEstimate``. Evaluates a point-identified Tian-Shpitser
  c-factor estimand (a nested sum/product/ratio of observational
  conditionals) on discrete data by the non-parametric plug-in, reusing
  the kernel's own ``estimate_formula`` walker. This is the numeric end of
  the general ID algorithm: effects identified ONLY through the
  c-component factorisation — not by back-door / front-door / IV — such as
  Pearl's napkin. Reached through ``themis.estimate`` as the final
  identification fallback, tried BEFORE the IV escalation because the
  c-factor estimand is assumption-free (an IV point needs monotonicity /
  homogeneity). Refuses on a positivity violation (empty stratum) rather
  than fabricating a value.

- Partial-identification numeric end — ``evaluate_manski_natural_bounds`` /
  ``evaluate_manski_tamer_bounds`` / ``evaluate_balke_pearl_bounds``
  returning ``NumericBounds``. Turns the SYMBOLIC bounds layer
  (``output/bounds.py``) into actual numbers on data. All three bound the
  same quantity — the single interventional arm ``P(Y=y|do(X=x))`` the query
  named: Manski (1990) natural and Manski (1997) MTR by closed form,
  Balke-Pearl SHARP by the response-function LINEAR PROGRAM over the
  ``|X|^|Z|·|Y|^|X|`` canonical types (cross-checked in tests against the
  published binary closed form and the Vitamin-A worked example
  −0.1946/0.0054, which the ``contrast`` field still reports). Reached
  through ``themis.estimate``, which fills ``lower_value`` / ``upper_value``
  / a bootstrap outer-band CI into the ``bounds_results`` the kernel already
  attached — always the SAME method the kernel named. Refuses (leaving the
  symbolic interval intact) on a positivity failure, a response-function
  partition beyond the LP's declared size, or a table the instrument
  refutes (the instrumental inequality).

The data contract (``DataContract`` / ``DataContractError``) is shared
by all estimators — same DataFrame validation, same SHA-256 hash
threaded into derivation provenance.
"""
from .aipw import (
    AIPWEstimate,
    IPWEstimate,
    PropensitySummary,
    estimate_aipw_ate,
    estimate_ipw_ate,
)
from .backdoor import BackdoorEstimate, estimate_backdoor_ate
from .bounds_numeric import (
    NumericBounds,
    evaluate_balke_pearl_bounds,
    evaluate_manski_natural_bounds,
    evaluate_manski_tamer_bounds,
)
from .contract import DataContract, DataContractError
from .frontdoor import FrontdoorEstimate, estimate_frontdoor_ate
from .general_id import GeneralIdEstimate, estimate_general_id_ate
from .four_way import (
    FourWayRatioComponents,
    four_way_ratio_decomposition,
    four_way_ratio_decomposition_continuous,
)
from .four_way_ratio import (
    FourWayRatioEstimate,
    estimate_four_way_ratio,
)
from .discovery import (
    DataDiagnostics,
    DiscoveryResult,
    discover_graph,
    discovery_to_kernel_ast,
)
from .orientation import (
    OrientationError,
    OrientationResult,
    orientation_to_dict,
    propagate_orientations,
)
from .orientation_questions import (
    OrientationQuestion,
    QuestionSet,
    compile_orientation_questions,
    question_set_to_dict,
)
from .orientation_session import (
    OrientationAnswer,
    OrientationSession,
    OrientationSessionError,
    ingest_orientation_answers,
    next_questions,
    session_to_dict,
    start_orientation_session,
)
from .orientation_ledger import orientation_ledger_export
from .iv import (
    ARConfidenceSet,
    IVEstimate,
    OverIDARConfidenceSet,
    OverIDIVEstimate,
    RobustARConfidenceSet,
    SarganTest,
    StratifiedARSet,
    anderson_rubin_confidence_set,
    anderson_rubin_overid_set,
    estimate_iv_ate,
    estimate_iv_overid,
    robust_anderson_rubin_overid_set,
    stratified_anderson_rubin_set,
)
from .joint import JointEffectEstimate, estimate_joint_effect
from .measurement import (
    CombinedMeasurementCorrectionEstimate,
    ExposureMeasurementCorrectionEstimate,
    MeasurementCorrectionEstimate,
    estimate_combined_measurement_correction,
    estimate_exposure_measurement_correction,
    estimate_measurement_correction,
)
from .longitudinal import (
    LongitudinalGFormulaEstimate,
    LongitudinalIPWMSMEstimate,
    estimate_longitudinal_gformula,
    estimate_longitudinal_ipw_msm,
)
from .mediation import (
    CDEChainEstimate,
    CDEEstimate,
    MediationEstimate,
    estimate_cde,
    estimate_cde_chain,
    estimate_mediation,
)
from .missing_recovery import (
    RecoveredATEEstimate,
    estimate_recovered_ate,
)
from .outcome_error import (
    OutcomeErrorAssessment,
    OutcomeErrorDesign,
    assess_outcome_error,
)
from .regression_calibration import (
    RegressionCalibrationEstimate,
    estimate_regression_calibration,
)
from .simex import (
    SimexEstimate,
    SimexGridPoint,
    estimate_simex,
)
from .sensitivity import (
    EValueResult,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
    e_value_from_ate_continuous,
)
from .sensitivity_ovb import (
    OVBBenchmark,
    OVBSensitivity,
    estimate_ovb_sensitivity,
)
from .tmle import TMLEEstimate, estimate_tmle_ate
from .transport import TransportEstimate, estimate_transport

__all__ = [
    "AIPWEstimate",
    "BackdoorEstimate",
    "CDEChainEstimate",
    "CDEEstimate",
    "DataContract",
    "DataContractError",
    "DataDiagnostics",
    "DiscoveryResult",
    "ARConfidenceSet",
    "OverIDARConfidenceSet",
    "OverIDIVEstimate",
    "RobustARConfidenceSet",
    "SarganTest",
    "StratifiedARSet",
    "estimate_iv_overid",
    "EValueResult",
    "FourWayRatioComponents",
    "FourWayRatioEstimate",
    "FrontdoorEstimate",
    "GeneralIdEstimate",
    "IPWEstimate",
    "IVEstimate",
    "JointEffectEstimate",
    "CombinedMeasurementCorrectionEstimate",
    "ExposureMeasurementCorrectionEstimate",
    "MeasurementCorrectionEstimate",
    "estimate_combined_measurement_correction",
    "estimate_exposure_measurement_correction",
    "estimate_measurement_correction",
    "LongitudinalGFormulaEstimate",
    "LongitudinalIPWMSMEstimate",
    "MediationEstimate",
    "NumericBounds",
    "OrientationError",
    "OrientationResult",
    "OrientationQuestion",
    "QuestionSet",
    "compile_orientation_questions",
    "question_set_to_dict",
    "OrientationAnswer",
    "OrientationSession",
    "OrientationSessionError",
    "ingest_orientation_answers",
    "next_questions",
    "session_to_dict",
    "start_orientation_session",
    "orientation_ledger_export",
    "OVBBenchmark",
    "OVBSensitivity",
    "OutcomeErrorAssessment",
    "OutcomeErrorDesign",
    "PropensitySummary",
    "RecoveredATEEstimate",
    "RegressionCalibrationEstimate",
    "SimexEstimate",
    "SimexGridPoint",
    "TMLEEstimate",
    "TransportEstimate",
    "anderson_rubin_confidence_set",
    "anderson_rubin_overid_set",
    "robust_anderson_rubin_overid_set",
    "stratified_anderson_rubin_set",
    "discover_graph",
    "discovery_to_kernel_ast",
    "e_value_for_risk_ratio",
    "e_value_from_ate_binary",
    "e_value_from_ate_continuous",
    "estimate_aipw_ate",
    "estimate_backdoor_ate",
    "evaluate_balke_pearl_bounds",
    "evaluate_manski_natural_bounds",
    "evaluate_manski_tamer_bounds",
    "estimate_cde",
    "estimate_cde_chain",
    "estimate_four_way_ratio",
    "estimate_frontdoor_ate",
    "estimate_general_id_ate",
    "estimate_ipw_ate",
    "four_way_ratio_decomposition",
    "estimate_iv_ate",
    "estimate_joint_effect",
    "four_way_ratio_decomposition_continuous",
    "orientation_to_dict",
    "propagate_orientations",
    "estimate_longitudinal_gformula",
    "estimate_longitudinal_ipw_msm",
    "estimate_mediation",
    "estimate_ovb_sensitivity",
    "estimate_recovered_ate",
    "assess_outcome_error",
    "estimate_regression_calibration",
    "estimate_simex",
    "estimate_tmle_ate",
    "estimate_transport",
]
