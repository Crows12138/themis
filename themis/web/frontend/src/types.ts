// Kernel envelope shapes — mirror of themis.run output (query_result.schema.json).
//
// This file used to say "only the fields the UI reads are typed; the rest is
// passthrough", which made every omission look deliberate and none of them
// checkable. Three comments below record what that cost, each written after a
// field turned out to be missing and each describing the same mechanism. Every
// top-level field of the envelope is now accounted for at the bottom of this
// file, and a test holds the accounting against the schema.

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
  words?: Record<string, { vocabulary: string; token: string }>
}

export interface DataGap extends Occasion {
  kind: string
  severity: 'blocking' | 'important' | 'informational'
  describes: GapSentence[]
  blocks: string
  required_data?: {
    data_type?: string
    population?: string
    variables?: string[]
    min_sample_size?: number
  }
  alternative_paths?: GapRoute[]
  provenance?: GapProvenance[]
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

export interface DataGapReport {
  gaps: DataGap[]
  answer_tier?: AnswerTier
}

// A partial-identification interval. `estimand` names WHAT the two endpoints
// bracket — this surface used to declare neither it nor the endpoints, so the
// only thing it could say about an interval was the method that produced it.
export interface BoundsContrast {
  kind: string
  reference_value?: unknown
  lower_value: number
  upper_value: number
  tightness?: string | null
}

export interface BoundsResult {
  method: string
  estimand: string
  lower_expression: string
  upper_expression: string
  assumptions?: string[]
  width_when_uninformative?: boolean
  notes?: string
  lower_value?: number | null
  upper_value?: number | null
  // Whether a narrower set is consistent with the same assumptions. Asked
  // per bracketed quantity, not per method: Manski-Tamer bounds the arm
  // sharply and reports no contrast at all, because MTR ties the arms at
  // the unit level and subtracting the intervals is an outer bound (#419).
  tightness?: string | null
  // A second interval over a second quantity from the same identified set,
  // not arithmetic on the endpoints above.
  contrast?: BoundsContrast | null
}

export interface Sensitivity {
  e_value?: number
  e_value_ci_bound?: number
  risk_ratio?: number
  baseline_rate?: number
  outcome_sd?: number | null
  path?: 'binary' | 'continuous'
  // The reading, and which of the two E-values above it was read off.
  interpretation_band?: 'fragile' | 'moderate' | 'substantial' | 'very_robust' | null
  band_basis?: 'ci_bound' | 'point' | null
  note?: string
}

export interface Band {
  point?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
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
  lower?: number | null
  upper?: number | null
  point?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  // Which of the two objects the ci pair holds on THIS row: 'sampling' when
  // monotonicity bought a point, 'outer_band' when it did not. Every surface
  // used to work this out from whether `point` was null, separately — which
  // was right and was three records of one fact (#419).
  ci_width_is?: string | null
}
export interface CausationQuantities {
  pn?: CausationQuantity
  ps?: CausationQuantity
  pns?: CausationQuantity
  monotonic?: boolean
  interventional_risk_provenance?: string
  adjustment?: string[]
  // Null together on the one route that answers without either — the
  // response-function program over an instrument, which is also the only
  // route that fills `instrument`. Typing them as always-present is what let
  // the surface hang the whole provenance line off their being there.
  p_y_do_x1?: number | null
  p_y_do_x0?: number | null
  instrument?: string | null
}

export interface ArConfidenceSet {
  kind?: string
  ci_level?: number
  lower?: number | null
  upper?: number | null
  segments?: { lower?: number | null; upper?: number | null }[]
}

export interface NumericEstimate {
  point?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  ci_level?: number
  method?: string
  adjustment?: string[]
  sample_size?: number
  // Three numbers and an English sentence restating them. The sentence has
  // one reader, which prints it raw; this surface builds its own line from
  // the numbers rather than copying a string assembled for someone else.
  precision_budget?: {
    current_ci_half_width?: number
    n_to_halve_ci?: number
    relative_width?: number
    hint?: string
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
  dose_response_curve?: ({ x?: number; effect?: number } & Band)[]
  reference_point?: number | null
  decomposition?: {
    te?: Band; nde?: Band; nie?: Band; proportion_mediated?: Band
  }
  joint_effect?: Band & {
    treated?: Record<string, unknown>; control?: Record<string, unknown>
  }
  interaction?: Band & { order?: number; scale?: string }
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
    // How many resamples the declared monotonicity left with no feasible
    // solution, against how many it did not. Their ratio is the closest
    // thing to a test of an assumption usually called untestable.
    bootstrap_draws_used?: number
    bootstrap_draws_infeasible?: number
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
  longitudinal_gformula?: LongitudinalRoute & { n_sim?: number }
  longitudinal_ipw_msm?: LongitudinalRoute & {
    stabilized?: boolean
    msm_coefficients?: number[]
    weight_mean?: number
    weight_max?: number
  }
  four_way_decomposition?: FourWayDifference
  four_way_ratio?: FourWayRatio
  four_way_unavailable?: { reason?: string }
}

export interface StratifiedWald {
  conditioning_order?: string[]
  outcome_shift?: number
  treatment_shift?: number
  strata?: {
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
  point?: number
  // The number listwise deletion would have given. The difference between it
  // and `point` is the entire argument for running the recovery.
  naive_listwise_ate?: number | null
  adjustment?: string[]
  n_total?: number
  n_complete_case?: number
  n_conditional_rows?: number
  n_marginal_rows?: number
  n_strata?: number
  missing_columns?: string[]
  n_bootstrap?: number
}

export interface SelectionRecovery {
  reference_sample_size?: number
  z_plus?: string[]
  z_minus?: string[]
  selected_values?: Record<string, unknown>
  mu_treated?: number
  mu_control?: number
}

export interface MeasurementCorrection {
  side?: string
  naive_point?: number
  det?: number
  det_exposure?: number
  det_outcome?: number
  det_joint?: number
  out_of_simplex?: boolean
  differential?: boolean
  differential_by?: string
}

export interface RegressionCalibration {
  naive_point?: number
  reliability?: number
  error_variances?: Record<string, number>
  exposure?: string
  design_vars?: string[]
}

export interface LongitudinalRoute {
  treatments?: string[]
  confounders_by_time?: string[][]
  outcome?: string
  strategy_treated?: number
  strategy_control?: number
  e_y_treated?: number
  e_y_control?: number
  n_bootstrap?: number
}

export interface FourWayDifference {
  cde?: Band; intref?: Band; intmed?: Band; pie?: Band; te?: Band
  prop_mediated?: Band; prop_interaction?: Band
  additive_interaction?: number
}

export interface FourWayRatio {
  mediator_scale?: string
  err_cde?: Band; err_intref?: Band; err_intmed?: Band; err_pie?: Band
  total_err?: Band; total_rr?: Band
  prop_mediated?: Band; prop_interaction?: Band; prop_eliminated?: Band
}

export interface LedgerEntry {
  claim: string
  layer?: string
  severity?: string
  // Who put this assumption on the list. Leaving it out of this type is how
  // the one field that tells a reader whom to argue with — an LLM proposed
  // this edge, a discovery algorithm learned it, you declared this
  // measurement model — never left the envelope on this surface, while the
  // report printed it beside every claim.
  provenance?: string
  testable?: boolean
}
export interface AssumptionLedger {
  assumptions?: LedgerEntry[]
  summary?: string
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
export interface LlmProposedReview {
  edges: ProposedEdge[]
  probabilities: ProposedProbability[]
  summary: string
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
  rule?: string
  step_id?: string | null
  // Only the one input this surface reads. A step's sentence comes from its
  // rule, and a rule can carry more than one route; the licence is where the
  // route is recorded.
  inputs?: { interventional_risk_provenance?: string }
}
export interface Derivation {
  steps?: DerivationStep[]
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
  }
  // The data contract behind the estimate. Its `sample_size` and the
  // estimate's agreed on all 528 envelopes carrying both, so the reader is
  // shown one number, not two; what is only here is the contract's own
  // warnings and the fact that data was read at all on the 55 envelopes that
  // recorded a contract and got no estimate.
  estimation_context?: {
    sample_size?: number
    data_contract_warnings?: string[]
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
// has to be a field this surface both declares and reads. All three are inputs
// the kernel's own gap report is computed from, so what reaches the reader is
// the curated form rather than the raw list.
export const CARRIED_BY: Record<string, string> = {
  missing_information: 'data_gap_report',
  framing_notes: 'data_gap_report',
  investigation_requests: 'data_gap_report',
  // 4569 of 4857 ⚠ lines in one suite run were a gap description copied
  // verbatim, and the gap list this surface renders states every one of
  // them. That was measured, not assumed: the entry here used to read "this
  // surface covers part of it, never reconciled line by line", and the 288
  // lines that were not copies split into 45 an estimator wrote next to a
  // gap of its own and 246 that contradicted the envelope they were on.
  explanation: 'data_gap_report',
}

// Nothing here says these, and nothing should: they address the caller or an
// auditor, not the person reading the answer.
export const NOT_FOR_A_READER: Record<string, string> = {
  query_id: '调用方用来把答案对回问题的句柄，报告印在审计脚注里，本面没有审计脚注',
  confidence: '整份结果的合成分数（不是统计置信区间）；主报告也不印它',
  confidence_sources: '合成分数逐槽位的来路，给审计用',
  estimator_dependency_missing: '可选后端没装的安装提示，是给运维的话',
}

// Nothing here says these, and something should. Capped by a test: this list
// can shrink and cannot grow.
export const NOT_YET_SAID_HERE: Record<string, string> = {}

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
