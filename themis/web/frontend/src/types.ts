// Kernel envelope shapes — mirror of themis.run output (query_result.schema.json).
//
// This file used to say "only the fields the UI reads are typed; the rest is
// passthrough", which made every omission look deliberate and none of them
// checkable. Three comments below record what that cost, each written after a
// field turned out to be missing and each describing the same mechanism. Every
// top-level field of the envelope is now accounted for at the bottom of this
// file, and a test holds the accounting against the schema.
//
// The same file also says which schema shape each interface below is a copy of,
// which is what lets a second test ask the other question a mirror can get
// wrong: not whether the field is here, but whether it is guaranteed.

export type AnswerTier = 'point' | 'interval' | 'none'

export interface GapProvenance {
  ref_kind: string
  ref_id: string
}

// The two halves of an occasion, as every channel that carries a species'
// sentence declares them.
//
// A species names the sentence and a table holds it; what belongs to THIS
// gap, this route, this refusal is only what goes in the holes — the values
// that read the same in every language, already rendered, and the words
// that do not, as the set and the token. Declared once because a channel
// free to declare its own half of this is a channel that gains a third
// spelling of it.
export interface Occasion {
  said?: Record<string, string>
  // A hole holds a whole statement, or a list of them — which is the same
  // shape one level down, since a statement is a word whose text has holes.
  // Written as the set and the token while that was all a hole could hold,
  // and every place with a sentence inside a sentence rendered the inner
  // one where it was built.
  words?: Record<string, Stated | Stated[]>
}

export interface DataGap extends Occasion {
  kind: string
  severity: 'blocking' | 'important' | 'informational'
  describes: GapSentence[]
  blocks: string
  required_data?: {
    data_type?: string
    // A NAME the caller supplied, or a STATEMENT saying which population
    // — a producer that picked a subset out has a characterisation and no
    // name to carry it, and a slot for a name is where that becomes prose.
    population?: string | Stated
    variables?: string[]
    min_sample_size?: number
    // What that many would buy, when the measurements would have to be
    // taken, and how the design could break SUTVA. Statements rather than
    // text: a number of subjects means nothing without the assumptions
    // that produced it, and those assumptions are this occasion's.
    precision_target?: Stated
    time_window?: Stated
    sutva_concerns?: Stated[]
    confounders_required?: string[]
  }
  alternative_paths?: GapRoute[]
  provenance: GapProvenance[]
}

// One statement a gap is made of, and this occasion's facts for the holes
// in it. A gap carries a LIST of these rather than a paragraph: which
// statements it has is what the occasion knows, and joining them is the
// one part that depends on who is reading.
export interface GapSentence extends Occasion {
  sentence: string
}

// One way past a gap: which route, and this occasion's facts for the holes
// in its sentence. `gapWent` fills the template the kernel supplies.
export interface GapRoute extends Occasion {
  route: string
}

// One statement any producer owed a reader — the shape the two above are
// instances of, with the vocabulary carried instead of fixed by the field.
// It exists because the kernel had built that carrier three times, each
// welded to one channel, so every fourth site holding a few values and
// owing a sentence about them wrote the sentence itself.
export interface Stated extends Occasion {
  vocabulary: string
  token: string
}

export interface DataGapReport {
  gaps: DataGap[]
  answer_tier?: AnswerTier
}

// A partial-identification interval. `estimand` names WHAT the two endpoints
// bracket — this surface used to declare neither it nor the endpoints, so the
// only thing it could say about an interval was the method that produced it.
export interface BoundsContrast {
  kind: string
  reference_value: unknown
  lower_value: number
  upper_value: number
  tightness: string | null
}

export interface BoundsResult {
  method: string
  estimand: string
  lower_expression: string
  upper_expression: string
  assumptions?: string[]
  width_when_uninformative?: boolean
  // What a client must observe to evaluate the expressions, and what is
  // true of this interval that no other field here carries — its width,
  // the size of the response-function partition, which end an assumption
  // moved, or that a sharper method was declined on size. `notes` is a
  // list because a fourth author appends to it.
  data_required?: Stated[]
  notes?: Stated[]
  lower_value?: number | null
  upper_value?: number | null
  // Whether a narrower set is consistent with the same assumptions. Asked
  // per bracketed quantity, not per method: Manski-Tamer bounds the arm
  // sharply and reports no contrast at all, because MTR ties the arms at
  // the unit level and subtracting the intervals is an outer bound (#419).
  tightness: string | null
  // A second interval over a second quantity from the same identified set,
  // not arithmetic on the endpoints above.
  contrast?: BoundsContrast | null
}

export interface Sensitivity {
  e_value: number | null
  e_value_ci_bound: number | null
  risk_ratio: number | null
  baseline_rate: number | null
  outcome_sd: number | null
  path: 'binary' | 'continuous'
  // The reading, and which of the two E-values above it was read off.
  interpretation_band: 'fragile' | 'moderate' | 'substantial' | 'very_robust' | null
  band_basis: 'ci_bound' | 'point' | null
  // Why there is no E-value, present exactly when `e_value` is null. Its
  // predecessor was a `note` doing two jobs — restating the numbers above
  // when there was one, and being the sole record of the reason when there
  // was not — so this surface could read neither and rendered its own line
  // off `e_value` alone, saying nothing at all where none came out.
  undefined_because?: Stated
}

// The three numbers every quantity in this envelope answers with. Written as
// a fragment because it is composed into a dozen shapes rather than being one
// of them, and required because every one of those shapes requires all three:
// a slot that carries a band carries the whole band.
export interface Band {
  point: number | null
  ci_lower: number | null
  ci_upper: number | null
}

// An estimate answers in whatever shape its estimand has. `point` is null for
// every shape that has no single number to lead with — a dose-response curve,
// a mediation decomposition, a joint contrast, a bounded counterfactual cell.
// Which shape a given estimate carries is declared per method in
// themis/answers.py; a test pins that this file reads all of them.
// PN / PS / PNS, as both containers carry them: numeric_estimate.
// probabilities_of_causation on the data path and extensions.causation on the
// theta path. Same three quantities, same shape, one renderer.
export interface CausationQuantity {
  // Required by BOTH containers, and the ci pair by only one of them: the
  // theta path's quantity forbids a band (`additionalProperties: false` over
  // three keys) because nothing on it produces a sampling distribution.
  lower: number
  upper: number
  point: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  // Which of the two objects the ci pair holds on THIS row: 'sampling' when
  // monotonicity bought a point, 'outer_band' when it did not. Every surface
  // used to work this out from whether `point` was null, separately — which
  // was right and was three records of one fact (#419).
  ci_width_is?: string | null
}
export interface CausationQuantities {
  pn: CausationQuantity
  ps: CausationQuantity
  pns: CausationQuantity
  monotonic: boolean
  interventional_risk_provenance: string
  adjustment?: string[]
  // Null together on the one route that answers without either — the
  // response-function program over an instrument, which is also the only
  // route that fills `instrument`. The KEY is always here and the VALUE is
  // what says there is none; typing the value as always a number is what let
  // the surface hang the whole provenance line off its being there.
  p_y_do_x1: number | null
  p_y_do_x0: number | null
  instrument: string | null
}

export interface ArConfidenceSet {
  kind: string
  ci_level: number
  lower?: number | null
  upper?: number | null
  segments?: { lower?: number | null; upper?: number | null }[]
}

/** What an interval is a quantile OF: how its replicates were drawn, how
 * many turned out to be usable, and what ate the rest.
 *
 * Absent means no bootstrap ran — an analytic or influence-function
 * interval, or none at all. `used` is at least 2 whenever an interval is
 * reported: one draw is not a sampling distribution.
 *
 * `discarded` is keyed by refusal species, the same closed vocabulary as
 * `estimator_failure.failure_type`, plus `unclassified` for a draw lost to
 * something carrying no species. WHICH refusal took a draw is the
 * actionable half: a share lost to `counterfactual_inputs_infeasible` is
 * the fraction of this data that refutes a declared monotonicity, where
 * the same share lost to a thin stratum says something else entirely.
 */
export interface BootstrapDraws {
  kind: 'iid' | 'cluster'
  cluster_column?: string
  requested: number
  used: number
  discarded?: Record<string, number>
}

export interface NumericEstimate {
  point?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  ci_level: number
  method: string
  adjustment?: string[]
  sample_size: number
  bootstrap?: BootstrapDraws
  // This surface built its line from the three numbers while a fourth field
  // beside them restated the same three as a sentence. Both surfaces had
  // reached that verdict independently and neither had acted on it; the
  // sentence is gone, and this is now the only way the line is made.
  precision_budget?: {
    current_ci_half_width?: number
    n_to_halve_ci?: number
    relative_width?: number
  }
  sensitivity_analysis?: Sensitivity
  // Three producers, one shape. Only the heteroskedasticity-robust set can
  // come out in more than two pieces, so only it carries `segments`; the
  // other two state the endpoints and let `kind` say which sides are open.
  anderson_rubin_confidence_set?: ArConfidenceSet
  stratified_anderson_rubin_confidence_set?: ArConfidenceSet
  robust_anderson_rubin_confidence_set?: ArConfidenceSet
  over_identification?: {
    sargan_p_value?: number
    hansen_p_value?: number
  }
  // Overlap counted rather than fitted: the cells the adjustment set cuts the
  // sample into, and how many of them held both arms. Absent where there are
  // no enumerable cells, which is why absence carries no verdict.
  stratum_support?: StratumSupport
  fitted_overlap?: FittedRange
  outcome_saturation?: FittedRange
  propensity_summary?: {
    raw_min?: number
    raw_max?: number
    n_trimmed?: number
    floor?: number
    model?: string
  }
  ovb_sensitivity?: {
    robustness_value_q?: number
    robustness_value_qa?: number
    alpha?: number
  }
  // ``x`` is a sampled dose for a continuous treatment and a declared exposure
  // state for a misclassified polytomous one, so it is not always a number:
  // dose bands can be named rather than measured. The one place a band is
  // spelled out rather than composed: a curve point has no `point` — the
  // number it carries is `effect` — and `& Band` claimed one that no envelope
  // has ever had.
  dose_response_curve?: {
    x: number | string | boolean
    effect: number
    ci_lower: number | null
    ci_upper: number | null
  }[]
  reference_point?: number | string | boolean | null
  // The direct effect at each level the mediator is held at — the shape a
  // controlled direct effect has, since the estimand is indexed by that
  // level. Present where the natural effects were not identifiable and this
  // one was; there is no `point` beside it, because choosing a level is a
  // policy decision and not a default.
  controlled_direct_effect?: {
    levels: ({ mediator_level: number } & Band)[]
    levels_observed: boolean
    varies_with_level: boolean
  }
  // Present exactly where `point` is absent: the channel would not invert,
  // so what came back tests whether the effect is zero rather than sizing it.
  no_effect_test?: {
    statistic?: number
    degrees_of_freedom?: number
    p_value?: number
    coefficients?: number[]
  }
  decomposition?: {
    te?: Band; nde?: Band; nie?: Band; proportion_mediated?: Band
  }
  joint_effect?: Band & {
    treated?: Record<string, unknown>; control?: Record<string, unknown>
  }
  interaction?: Band & { order?: number; scale?: string }
  // Exactly one of the two stands: the number, or why there is none. The
  // species decides which fact comes with it — the corners the box came up
  // short on, or the cap the order ran past.
  interaction_unavailable?: {
    kind?: string
    order?: number
    unsupported_cells?: Record<string, unknown>[]
    cap?: number
  }
  // Two solvers fill `lower`/`upper`, so the licence that says which one ran
  // travels with them; `instrument` is non-null only on the one that bounds
  // the cell over an instrument's response-type polytope.
  counterfactual_cell?: {
    lower?: number | null
    upper?: number | null
    // `point` is non-null exactly when the set collapsed — the consistency
    // identity, the ETT case with no factual outcome, or a declared
    // monotonicity — and the ci pair is then around IT rather than around
    // the set, which is what `ci_width_is` says (#419). All four were on the
    // envelope and stated only by the report: this surface printed the
    // identified interval and nothing about the resampling its own route
    // description promises.
    point?: number | null
    ci_lower?: number | null
    ci_upper?: number | null
    ci_width_is?: string | null
    monotonicity?: string | null
    adjustment?: string[]
    interventional_risk_provenance?: string
    instrument?: string | null
    // Which cell. The interval means a different thing for each assignment
    // of the four, and the surface used to state it as "反事实格".
    observed_x?: boolean
    counterfactual_x?: boolean
    target_y?: boolean
    factual_y?: boolean | null
    p_y_do_x_cf?: number | null
    // Of the resamples that answered, the share whose feasible set was
    // empty under the declared monotonicity. Null where the question does
    // not arise; a zero would tell every reader about an assumption their
    // data never touched. Carried rather than derived from
    // `numeric_estimate.bootstrap` because this cell is also a display
    // copy in `extensions`, where there is no estimate beside it.
    monotonicity_refuted_share?: number | null
  }
  // Three estimands, not one. `point` is non-null on each exactly when
  // monotonicity was assumed, and `ci_width_is` says which of the two objects
  // the ci pair holds rather than leaving this comment to be the record of it
  // (#419). numeric_estimate.point mirrors pn — which is why reading only
  // `point` printed the necessity headline with none of the three names on it.
  probabilities_of_causation?: CausationQuantities
  // How the NUMBER was computed, as opposed to how the estimand was
  // identified. Each of these is exclusive to one estimator and every one of
  // them used to reach no reader on either surface, because the section that
  // asks "怎么算出来的" is bound to the `extensions` map and these live here.
  stratified_wald?: StratifiedWald
  recovered_ate?: RecoveredAte
  selection_recovery_numeric?: SelectionRecovery
  measurement_correction?: MeasurementCorrection
  regression_calibration?: RegressionCalibration
  differential_error?: DifferentialError
  simex?: Simex
  longitudinal_gformula?: LongitudinalRoute & { n_sim?: number }
  longitudinal_ipw_msm?: LongitudinalRoute & {
    stabilized?: boolean
    msm_coefficients?: number[]
    weight_mean?: number
    weight_max?: number
  }
  four_way_decomposition?: FourWayDifference
  four_way_ratio?: FourWayRatio
  four_way_unavailable?: { reason?: Stated }
  // The ACR margin table's own draws, and the ratio split's own — each a
  // second loop over a second quantity, so each keeps its own count. A
  // resample with a dead first stage carries no margin weights and still
  // carries a Wald ratio.
  acr_decomposition?: Record<string, unknown> & { bootstrap?: BootstrapDraws }
}

export interface StratifiedWald {
  conditioning_order: string[]
  outcome_shift: number
  treatment_shift: number
  strata: {
    values?: (string | number | boolean)[]
    weight?: number
    n_obs?: number
    n_instrument_high?: number
    n_instrument_low?: number
    outcome_shift?: number
    treatment_shift?: number
  }[]
}

export interface RecoveredAte {
  point: number
  // The number listwise deletion would have given. The difference between it
  // and `point` is the entire argument for running the recovery.
  naive_listwise_ate: number | null
  adjustment: string[]
  n_total: number
  n_complete_case: number
  n_conditional_rows: number
  n_marginal_rows: number
  n_strata: number
  missing_columns: string[]
}

export interface SelectionRecovery {
  reference_sample_size: number
  z_plus: string[]
  z_minus: string[]
  selected_values?: Record<string, unknown>
  mu_treated: number
  mu_control: number
}

export interface MeasurementCorrection {
  side?: string
  naive_point: number | null
  det?: number
  det_exposure?: number
  det_outcome?: number
  det_joint?: number
  out_of_simplex?: boolean
  differential: boolean
  /** One column, or the list of columns whose values together select the
   * matrix (a rate varying by arm AND by stratum). */
  differential_by?: string | string[]
  /**
   * The validation study's own count table for a matrix, present exactly
   * where the caller declared the channel as a tally rather than as a
   * matrix — which is the claim that the bootstrap redrew it every round
   * and the interval carries that study's uncertainty too.
   */
  validation_counts?: number[][]
  exposure_validation_counts?: number[][]
  outcome_validation_counts?: number[][]
  confusion_matrices?: {
    arm?: number
    outcome?: unknown
    level?: unknown
    matrix?: number[][]
    det?: number
    validation_counts?: number[][]
  }[]
}

export interface RegressionCalibration {
  naive_point: number
  reliability: number
  error_variances: Record<string, number>
  exposure: string
  design_vars: string[]
}

/**
 * The same correction with the non-differential premise withdrawn. It carries
 * `outcome_tracking_covariance` because that term has no counterpart above:
 * the observed covariance is un-inflated by it BEFORE the variance is
 * un-inflated by the error variance, so `reliability` alone no longer
 * reproduces the answer from `naive_point`.
 */
export interface DifferentialError {
  naive_point: number
  exposure: string
  differential_by: string
  differential_coefficient: number
  error_variance: number
  nondifferential_variance: number
  outcome_tracking_covariance: number
  exposure_variance: number
  reliability: number
  design_vars: string[]
}

/**
 * The other channel, where the error is IN the outcome and tracks the
 * exposure. Shorter than its sibling by exactly the fields that do not exist
 * there: the error is not in a regressor, so nothing is attenuated, there is
 * no reliability ratio, and the whole correction is naive_point − δ.
 */
export interface DifferentialOutcomeError {
  naive_point: number
  outcome: string
  differential_by: string
  differential_coefficient: number
  error_variance: number
  nondifferential_variance: number
  exposure_tracking_variance: number
  exposure_variance: number
  validation_df?: number
  tracking_standard_error?: number
  design_vars: string[]
}

/**
 * The simulation ladder is what travels, because it is the second stage's
 * sufficient statistic: everything downstream of it is re-derived from it.
 */
export interface Simex {
  naive_point: number
  outcome_model: 'linear' | 'logistic'
  extrapolant: 'linear' | 'quadratic' | 'rational'
  error_variance: number
  exposure: string
  n_replicates: number
  random_state: number
  grid: {
    lambda: number
    theta: number
    replicate_variance?: number
    variance_mean?: number
    replicates?: number
  }[]
  coefficients: number[]
  variance_coefficients: number[]
  extrapolated_variance: number | null
  // The degrees of freedom of the study that measured σ²_u (SIMEX), and the share
  // of what that study makes plausible at which the fitted curve cannot be
  // read. Present, the interval is the mixture over λ* = −df/χ²_df rather
  // than the point ± z√τ(−1); null is the claim that σ²_u is exact.
  validation_df: number | null
  unreadable_share: number | null
  no_interval_because: string | null
  cluster: string | null
  form?: string
}

export interface LongitudinalRoute {
  treatments: string[]
  confounders_by_time: string[][]
  outcome: string
  strategy_treated: number
  strategy_control: number
  e_y_treated: number
  e_y_control: number
}

export interface FourWayDifference {
  cde: Band; intref: Band; intmed: Band; pie: Band; te: Band
  prop_mediated: Band; prop_interaction: Band
  additive_interaction?: number
}

export interface FourWayRatio {
  mediator_scale: string
  err_cde: Band; err_intref: Band; err_intmed: Band; err_pie: Band
  total_err: Band; total_rr: Band
  prop_mediated: Band; prop_interaction: Band; prop_eliminated: Band
}

export interface LedgerEntry {
  // The statements this line is made of. A list because one of the three
  // channels that write it contributes however many its occasion had — an
  // unverified edge's line is the gap's own description, which used to be
  // joined into a paragraph in the kernel.
  claim: Stated[]
  layer: string
  severity: string
  // Who put this assumption on the list. Leaving it out of this type is how
  // the one field that tells a reader whom to argue with — an LLM proposed
  // this edge, a discovery algorithm learned it, you declared this
  // measurement model — never left the envelope on this surface, while the
  // report printed it beside every claim.
  provenance: string
  testable?: boolean
  // What a check made on THIS run concluded, absent when none was made.
  // `testable` above says only that somebody COULD check it, so without this
  // a premise this run tested and watched the data refuse read exactly like
  // one nobody has ever looked at.
  checked?: LedgerCheck
}
export interface LedgerCheck {
  verdict: string
  by: string
}
export interface AssumptionLedger {
  assumptions?: LedgerEntry[]
}

// Overlap counted rather than fitted: the cells the adjustment set cuts the
// sample into, and how many of them held both arms. Absent where there are no
// enumerable cells, which is why absence carries no verdict — and it is the
// evidence a ledger line's positivity verdict is read off, on both sides.
export interface StratumSupport {
  cells: number
  supported: number
  extrapolated_share: number
}

// What a diagnostic that answers by FITTING a model found. One shape, two
// landings — the overlap fit of P(X|Z) and the saturation fit of P(Y|X,Z) —
// because the arithmetic is the same and the band is what tells them apart.
// `threshold` travels with the finding rather than being restated by every
// reader, so the gap, the report and the ledger's verdict cannot end up on
// different sides of one frame.
export interface FittedRange {
  p_min: number
  p_max: number
  share_outside: number
  band_lower: number
  band_upper: number
  threshold: number
}

export interface StructuralResult {
  value: boolean
  supporting_paths?: string[][]
}

// extensions.llm_proposed_review — the audit surface for everything the LLM
// proposed (graph edges + θ priors) rather than measured. Present iff at
// least one such element exists; the disclosure the user must see.
export interface ProposedEdge {
  from: string
  to: string
  source: string
}
export interface ProposedProbability {
  key: string
  value: number
  reason: string
  population?: string
}
// The two lists and nothing else. There was a `summary: string` here, a
// sentence the kernel stopped writing when a count stored beside the thing
// counted turned out to be a second record of it — no producer has filled the
// key since, nothing here reads it, and a required field nobody sends is the
// dangerous half of this file's claim: `undefined` typed as a string.
export interface LlmProposedReview {
  edges: ProposedEdge[]
  probabilities: ProposedProbability[]
}

// One step of the machine-verifiable chain, and the chain itself. `rule`
// names what the step did, out of a closed set the kernel declares once and
// this surface mirrors; `inputs`/`output` are what the verifier re-runs and
// are not read here. Every answered result carries a chain whatever route it
// took — 570 of 1627 envelopes in one suite run, across ten query kinds —
// which is what makes it the only complete answer to the question the
// 「怎么算出来的」 foldout asks. Undeclared here, the foldout named that
// question and never once answered it with the chain.
export interface DerivationStep {
  rule: string
  step_id?: string | null
  // Only the one input this surface reads. A step's sentence comes from its
  // rule, and a rule can carry more than one route; the licence is where the
  // route is recorded.
  inputs: { interventional_risk_provenance?: string }
}
export interface Derivation {
  steps: DerivationStep[]
}

export interface QueryResult {
  status: string
  query_kind: string
  structural_result?: StructuralResult
  formula?: unknown
  derivation?: Derivation
  data_gap_report?: DataGapReport
  // A SET. Every method whose assumptions the program supports bounds the
  // same estimand; which interval rests on what is the only thing that
  // makes several of them readable side by side.
  bounds_results?: BoundsResult[]
  numeric_estimate?: NumericEstimate
  // Structural-layer answer (themis.run / apply_patch_and_run). Distinct from
  // numeric_estimate (themis.estimate, data-backed) — this is what a plug-in
  // identification formula yields once θ is supplied (incl. via AI priors).
  // Shown in the verdict when no data-backed estimate is present.
  //
  // `value` is null exactly when the estimand is bounded rather than pinned,
  // and `interval` is then the answer. Declaring only `value` here is how a
  // bounded counterfactual reached the browser as an empty answer slot while
  // its interval sat in the same object.
  numeric_result?: { value?: number | null; interval?: { low: number; high: number } }
  // `kind` is which of the five answers to "what now" this refusal gives —
  // the only part of a refusal that tells the reader what to do about it.
  // The species names WHY no number came out (a developer's handle) and
  // carries the sentence's TEMPLATE, which this build holds in
  // `REFUSAL_SAYS`. Leaving `kind` out of this type is how 47 refusals
  // across five genuinely different instructions — go get different data,
  // change one input, the graph settles it, Themis has not built this —
  // arrived here as one line reading `拒绝 · <english id>`.
  //
  // There is no `reason`. It was a finished sentence until #411, which
  // meant the kernel picked the language while refusing, with no reader in
  // front of it. What arrives instead are the sentence's holes: `said` for
  // the ones that read the same in every language (a count, a column, a
  // sampled list — symbols, rendered once by the one implementation of
  // that rule), and `words` for the ones that do not, as the closed set
  // and the member. `refusalSaid` puts them together here, where the
  // reader's language is known.
  //
  // `remedies` is `kind` at the other grain: `kind` answers "what now" per
  // species, this answers it per occasion. The two are not one field
  // because the same species is raised by estimators whose way out differs,
  // so no per-species answer can carry it. Token plus the occasion's own
  // name, both in no language; the sentence is made here.
  estimator_failure?: {
    estimator?: string
    failure_type?: string
    kind?: string
    said?: Record<string, string>
    words?: Record<string, { vocabulary?: string; token?: string }>
    remedies?: { remedy?: string; subject?: string }[]
  }
  // What a declared measurement error on the outcome costs this query. It
  // prices the interval: `se_inflation` is how much wider every interval on
  // this design is than it would be if the outcome were measured cleanly,
  // and that part is what more subjects cannot buy back. Which is why the
  // report prints it beside the precision hint rather than anywhere else:
  // the hint says how many more subjects halve the interval, and saying only
  // that sends the reader to buy the wrong thing.
  //
  // `design_kind` is which residual the factor was taken around, and it is
  // not decoration: on two of the three designs the factor IS the cost, and
  // on the front door it is a ceiling on it — that is read off the design
  // name because a field claiming it would be a second record of the same
  // fact. Whether the POINT survives the error depends on the design too.
  outcome_error?: {
    outcome?: string
    design_kind?: string
    se_inflation?: number
    noise_share?: number
    // And what the study that measured the variance does to that factor.
    // A null upper endpoint beside a present lower one is the statement
    // that the widening has no ceiling the study can supply.
    validation_df?: number | null
    se_inflation_lower?: number | null
    se_inflation_upper?: number | null
    inflation_refuted_share?: number | null
  }
  // The exposure channel's other structure, and no `design_kind` beside it:
  // this block is defined on the back door alone, because the identity that
  // saves the point is about a conditional mean of Y given the recorded
  // exposure and that is what a back-door answer is.
  berkson_error?: {
    exposure?: string
    se_inflation?: number
    noise_share?: number
    // And what the study that measured the variance does to that factor.
    // A null upper endpoint beside a present lower one is the statement
    // that the widening has no ceiling the study can supply.
    validation_df?: number | null
    se_inflation_lower?: number | null
    se_inflation_upper?: number | null
    inflation_refuted_share?: number | null
  }
  // The data contract behind the estimate. Its `sample_size` and the
  // estimate's agreed on all 528 envelopes carrying both, so the reader is
  // shown one number, not two; what is only here is the contract's own
  // warnings and the fact that data was read at all on the 55 envelopes that
  // recorded a contract and got no estimate.
  estimation_context?: {
    sample_size?: number
    // Statements rather than sentences. Typed `string[]` until #489, and a
    // string field made every branch in the kernel the author of its own
    // wording — six of them, five in Chinese and one in English, four of
    // those sharing an if/elif chain with the English one.
    data_contract_warnings?: Stated[]
    cluster?: string
  }
  extensions?: {
    assumption_ledger?: AssumptionLedger
    llm_proposed_review?: LlmProposedReview
  } & Record<string, unknown>
}

// --- the rest of the envelope ------------------------------------------------
//
// The interface above is a claim about what this surface uses, and until these
// three lists existed it could not be told apart from a claim about what the
// envelope has. `blocks.py` asks every block how it reaches a reader and holds
// each answer to a surface; it stops at `extensions` because it was drawn
// around the parts whose names are string literals, where a typo is silence —
// a boundary about SPELLING, kept after the register grew a question about
// REACHING. So the twenty-one typed fields were never asked, and four of them
// went missing here one at a time, each fixed by hand and each leaving a
// comment above describing the mechanism that would take the next one.
//
// A test parses these and the schema and holds them to partitioning it. The
// three answers are different claims and are kept apart on purpose: only the
// last one says work remains, and only it is capped.

// Said here by another field, named because a name can be checked: the carrier
// has to be a field this surface both declares and reads.
export const CARRIED_BY: Record<string, string> = {
  // Inputs the kernel's own gap report is computed from, so what reaches the
  // reader is the curated form rather than the raw list.
  missing_information: 'data_gap_report',
  framing_notes: 'data_gap_report',
  investigation_requests: 'data_gap_report',
  // `explanation` was the row above this one, and it is gone rather than
  // moved: 4569 of 4857 ⚠ lines in one suite run were a gap description
  // copied verbatim, 45 more were an estimator's wording of a gap of its
  // own, and 246 contradicted the envelope they rode on. A field with no
  // statement of its own is a rendering, and a rendering that ships inside
  // the envelope is one written before anyone knew who would read it.
  // One writer, and it appends a data-contract warning in the same unbranched
  // call: which estimator was asked for, which one ran, and why, in a sentence
  // this surface prints line by line. The block states nothing that sentence
  // leaves out, so a second rendering would say the same thing twice.
  estimator_fallback: 'estimation_context',
}

// Who a field addresses, where it is not the person reading the answer.
//
// The list is hand-written because nothing generates it: the browser keeps
// this distinction and the kernel does not, so there is no readable source
// to derive it from. The VALUE is derivable from nothing either, and it was
// a sentence per field — which made four unrelated notes out of one fact
// with three values. The comment over the table had already named the set
// ("they address the caller or an auditor") while the type held prose.
//
// Naming the audience is also what a new field has to answer. A reason can
// be written for anything; picking one of three is a claim that can be
// wrong, and being wrong is what makes it worth stating.
export type Audience = 'the_caller' | 'an_auditor' | 'whoever_runs_it'
export const NOT_FOR_A_READER: Record<string, Audience> = {
  // The handle a caller joins an answer back to its question with. The
  // Python report prints it in an audit footnote; this surface has none.
  query_id: 'the_caller',
  // A synthesised score over the whole result — not a statistical
  // confidence interval — and its provenance slot by slot. The main
  // report does not print either one.
  confidence: 'an_auditor',
  confidence_sources: 'an_auditor',
  // Which optional backend is absent and how to install it.
  estimator_dependency_missing: 'whoever_runs_it',
}

// Nothing here says these, and something should. Capped by a test: this list
// can shrink and cannot grow.
export const NOT_YET_SAID_HERE: Record<string, string> = {}

// --- which shape each interface is a copy of ---------------------------------
//
// The three lists above settle WHICH FIELDS the envelope's top level has. They
// say nothing about the rest of the file, and nothing about the other half of
// what a type claims: which of the fields are GUARANTEED. A hand-written mirror
// loses a `required` silently — the field is still there, still the right type,
// and merely optional, so the compiler asks for a check the envelope can never
// fail and the browser writes a reader a line for a case that does not exist.
// The dangerous direction is the other one: a field required here and optional
// there is `undefined` wearing the type of a value.
//
// Measured before this table existed: 115 fields the schema guarantees were
// optional here, and one — `LlmProposedReview.summary` — was required here and
// absent from the schema, from every producer, and from every reader.
//
// Nothing derives this table, for the same reason `NOT_FOR_A_READER` is
// hand-written: an interface and a `$def` are related by somebody's intent and
// by nothing readable. Matching on the name reaches 7 of 40 and gets one of
// those wrong, which is coverage's shape without coverage. So each interface
// names the schema shape it copies, as a JSON Pointer — the schema's own
// spelling for a place in itself, with a file in front of it when the shape
// lives in another one.
//
// An interface may name SEVERAL shapes, because several producers may fill it:
// the same three probabilities of causation come off the theta path and the
// data path, and a band is composed into a dozen slots. What that costs is
// exact — a field is guaranteed only where every named shape requires it, so
// naming a second shape can only ever weaken a promise, never invent one.
export const MIRRORS: Record<string, string[]> = {
  ArConfidenceSet: [
    '#/properties/numeric_estimate/properties/anderson_rubin_confidence_set',
    '#/properties/numeric_estimate/properties/stratified_anderson_rubin_confidence_set',
    '#/properties/numeric_estimate/properties/robust_anderson_rubin_confidence_set',
  ],
  AssumptionLedger: ['#/properties/extensions/properties/assumption_ledger'],
  // Every slot this fragment is composed into. Listed rather than reduced to
  // the two `$defs` that share its shape: what a fragment promises is decided
  // where it lands, and the two defs are only two of the landings.
  Band: [
    '#/$defs/componentEstimate',
    '#/$defs/ratioComponentEstimate',
    '#/properties/numeric_estimate/properties/decomposition/properties/te',
    '#/properties/numeric_estimate/properties/decomposition/properties/nde',
    '#/properties/numeric_estimate/properties/decomposition/properties/nie',
    '#/properties/numeric_estimate/properties/decomposition/properties/proportion_mediated',
    '#/properties/numeric_estimate/properties/joint_effect',
    '#/properties/numeric_estimate/properties/interaction',
    '#/properties/numeric_estimate/properties/controlled_direct_effect/properties/levels/items',
  ],
  BootstrapDraws: ['#/$defs/bootstrapDraws'],
  BoundsContrast: ['#/$defs/boundsResult/properties/contrast'],
  BoundsResult: ['#/$defs/boundsResult'],
  CausationQuantities: [
    '#/properties/numeric_estimate/properties/probabilities_of_causation',
    '#/properties/extensions/properties/causation',
  ],
  // The theta path's quantity forbids a band and the data path's requires one,
  // so the ci pair is guaranteed by neither — which is the whole reason both
  // are named here rather than the one that happens to share the name.
  CausationQuantity: ['#/$defs/causationQuantity', '#/$defs/causationEstimate'],
  DataGap: ['#/$defs/dataGap'],
  DataGapReport: ['#/$defs/dataGapReport'],
  Derivation: ['derivation.schema.json#'],
  DerivationStep: ['derivation.schema.json#/$defs/step'],
  DifferentialError: ['#/properties/numeric_estimate/properties/differential_error'],
  DifferentialOutcomeError: [
    '#/properties/numeric_estimate/properties/differential_outcome_error',
  ],
  FourWayDifference: ['#/properties/numeric_estimate/properties/four_way_decomposition'],
  FourWayRatio: ['#/properties/numeric_estimate/properties/four_way_ratio'],
  // Both landings, listed rather than reduced to the one `$defs` they share:
  // what a fragment promises is decided where it lands.
  FittedRange: [
    '#/properties/numeric_estimate/properties/fitted_overlap',
    '#/properties/numeric_estimate/properties/outcome_saturation',
  ],
  GapProvenance: ['#/$defs/dataGap/properties/provenance/items'],
  GapRoute: ['#/$defs/gapRoute'],
  GapSentence: ['#/$defs/gapSentence'],
  LedgerCheck: [
    '#/properties/extensions/properties/assumption_ledger/properties/assumptions/items/properties/checked',
  ],
  LedgerEntry: [
    '#/properties/extensions/properties/assumption_ledger/properties/assumptions/items',
  ],
  LlmProposedReview: ['#/properties/extensions/properties/llm_proposed_review'],
  LongitudinalRoute: [
    '#/properties/numeric_estimate/properties/longitudinal_gformula',
    '#/properties/numeric_estimate/properties/longitudinal_ipw_msm',
  ],
  MeasurementCorrection: ['#/properties/numeric_estimate/properties/measurement_correction'],
  NumericEstimate: ['#/properties/numeric_estimate'],
  // The two halves of an occasion are the two optional halves of a statement.
  Occasion: ['statement.schema.json#/$defs/statement'],
  ProposedEdge: [
    '#/properties/extensions/properties/llm_proposed_review/properties/edges/items',
  ],
  ProposedProbability: [
    '#/properties/extensions/properties/llm_proposed_review/properties/probabilities/items',
  ],
  QueryResult: ['#'],
  RecoveredAte: ['#/properties/numeric_estimate/properties/recovered_ate'],
  RegressionCalibration: ['#/properties/numeric_estimate/properties/regression_calibration'],
  SelectionRecovery: ['#/properties/numeric_estimate/properties/selection_recovery_numeric'],
  Sensitivity: ['#/properties/numeric_estimate/properties/sensitivity_analysis'],
  Simex: ['#/properties/numeric_estimate/properties/simex'],
  Stated: ['statement.schema.json#/$defs/statement'],
  StratifiedWald: ['#/properties/numeric_estimate/properties/stratified_wald'],
  StratumSupport: ['#/properties/numeric_estimate/properties/stratum_support'],
  StructuralResult: ['#/properties/structural_result'],
}

// The shapes this file declares that are not the kernel's. They are what the
// browser's own door hands back, and no schema in the kernel describes them.
//
// This is the one way out of the table above, so it is held to a claim it can
// fail: nothing that mirrors a schema shape may reach one of these. A nested
// shape filed here to dodge the check would be named by the interface that
// carries it, and that is what the test looks for.
export const NOT_THE_ENVELOPE: Record<string, string> = {
  ApiError: 'what /api hands back when a stage of the pipeline raised',
  AskResponse: 'the natural-language door: what was asked, what it compiled to, what came out',
  Envelope: 'the kernel is asked a program and answers a list; this is that list',
  ExampleItem: 'one of the worked programs the page offers to run',
}

export interface Envelope {
  results: QueryResult[]
  program?: unknown
}

export interface ExampleItem {
  name: string
  nl_input?: string | null
  program: Record<string, unknown>
}

export interface AskResponse {
  nl: string
  kernel_ast: Record<string, unknown>
  envelope: Envelope
  reply: string
}

export interface ApiError {
  error?: string
  message?: string
  stage?: string
}
