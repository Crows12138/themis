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
- iter 212 — ``anderson_rubin_confidence_set`` returning
  ``ARConfidenceSet``: the Anderson-Rubin (1949) weak-identification-robust
  confidence set for the single-instrument IV coefficient, always attached
  to ``IVEstimate``. Valid regardless of first-stage strength — unlike the
  bootstrap CI — and honestly returns an unbounded set when the data cannot
  bound the effect. iter 240 — ``anderson_rubin_overid_set`` returning
  ``OverIDARConfidenceSet`` is its multi-instrument (q ≥ 2) counterpart,
  attached to ``OverIDIVEstimate``: still one quadratic inequality (the
  q-dimensional projection only changes the coefficients), with critical value
  ``q·F(q, m)``. iter 246 — ``robust_anderson_rubin_overid_set`` returning
  ``RobustARConfidenceSet`` is the heteroskedasticity-robust (Stock-Wright S /
  Kleibergen) version, valid under weak identification AND heteroskedasticity /
  clustering at once: it inverts ``AR_r(β0) = n·ḡ'Ŝ(β0)⁻¹ḡ ~ χ²(q)`` with the
  β0-dependent robust weight, via exact polynomial root-finding (the set can be
  bounded / disconnected / whole-line / empty / a union of pieces).
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
  multi-level exposure, combined (exposure AND outcome) correction, and a matrix
  jointly differential in the outcome AND a covariate.
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
  verifier re-derives them without the raw data. Deferred: Berkson / differential
  error, a mismeasured outcome, a nonlinear outcome (SIMEX).
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
- Phase 7.5 (iter 125) — Controlled Direct Effect at fixed M=m*:
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
- Phase 7.5+ (iter 134) — Multi-mediator chain CDE:
  ``estimate_cde_chain`` returning ``CDEChainEstimate``. Extends the
  iter 125 single-M CDE to N mediators X→M_1→...→M_n→Y, fixing
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
- Phase 9 §T9.2 (iter 128) — transport-numeric ATE via post-
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
- Phase 8.2 — sensitivity: ``e_value_for_risk_ratio`` /
  ``e_value_from_ate_binary`` / ``e_value_from_ate_continuous``
  (iter 124, Chinn 2000 SMD→RR) returning ``EValueResult``
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
  ``evaluate_manski_tamer_bounds`` / ``evaluate_balke_pearl_ace_bounds``
  returning ``NumericBounds``. Turns the SYMBOLIC bounds layer
  (``output/bounds.py``) into actual numbers on data: Manski (1990) natural
  and Manski (1997) MTR bounds on a single interventional arm
  ``P(Y=y|do(X=x))``, and Balke-Pearl (1997) SHARP bounds on the ACE for a
  binary instrument — the latter by the response-function LINEAR PROGRAM over
  the 16 canonical response types (cross-checked in tests against the
  published closed form and the Vitamin-A worked example −0.1946/0.0054).
  Reached through ``themis.estimate``, which fills ``lower_value`` /
  ``upper_value`` / a bootstrap outer-band CI into the ``bounds_result`` the
  kernel already attached — always the SAME method the kernel named. Refuses
  (leaving the symbolic interval intact) on a non-binary variable, a
  positivity failure, or a table the instrument refutes (the Balke-Pearl
  instrumental inequalities).

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
    evaluate_balke_pearl_ace_bounds,
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
from .iv import (
    ARConfidenceSet,
    IVEstimate,
    OverIDARConfidenceSet,
    OverIDIVEstimate,
    RobustARConfidenceSet,
    SarganTest,
    anderson_rubin_confidence_set,
    anderson_rubin_overid_set,
    estimate_iv_ate,
    estimate_iv_overid,
    robust_anderson_rubin_overid_set,
)
from .joint import JointEffectEstimate, estimate_joint_effect
from .measurement import (
    ExposureMeasurementCorrectionEstimate,
    MeasurementCorrectionEstimate,
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
from .regression_calibration import (
    RegressionCalibrationEstimate,
    estimate_regression_calibration,
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
    "estimate_iv_overid",
    "EValueResult",
    "FourWayRatioComponents",
    "FourWayRatioEstimate",
    "FrontdoorEstimate",
    "GeneralIdEstimate",
    "IPWEstimate",
    "IVEstimate",
    "JointEffectEstimate",
    "ExposureMeasurementCorrectionEstimate",
    "MeasurementCorrectionEstimate",
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
    "OVBBenchmark",
    "OVBSensitivity",
    "PropensitySummary",
    "RecoveredATEEstimate",
    "RegressionCalibrationEstimate",
    "TMLEEstimate",
    "TransportEstimate",
    "anderson_rubin_confidence_set",
    "anderson_rubin_overid_set",
    "robust_anderson_rubin_overid_set",
    "discover_graph",
    "discovery_to_kernel_ast",
    "e_value_for_risk_ratio",
    "e_value_from_ate_binary",
    "e_value_from_ate_continuous",
    "estimate_aipw_ate",
    "estimate_backdoor_ate",
    "evaluate_balke_pearl_ace_bounds",
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
    "estimate_regression_calibration",
    "estimate_tmle_ate",
    "estimate_transport",
]
