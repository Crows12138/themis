// Kernel envelope shapes — mirror of themis.run output (query_result.schema.json).
// Only the fields the UI reads are typed; the rest is passthrough.

export type AnswerTier = 'point' | 'interval' | 'none'

export interface GapProvenance {
  ref_kind: string
  ref_id: string
}

export interface DataGap {
  kind: string
  severity: 'blocking' | 'important' | 'informational'
  description: string
  blocks: string
  if_provided?: string
  required_data?: {
    data_type?: string
    population?: string
    variables?: string[]
    min_sample_size?: number
  }
  alternative_paths?: string[]
  provenance?: GapProvenance[]
}

export interface DataGapReport {
  summary: string
  gaps: DataGap[]
  actionable_next_steps?: string[]
  answer_tier?: AnswerTier
}

export interface BoundsResult {
  method: string
  lower_expression: string
  upper_expression: string
  assumptions?: string[]
  width_when_uninformative?: boolean
  notes?: string
}

export interface Sensitivity {
  e_value?: number
  e_value_ci_bound?: number
  risk_ratio?: number
  baseline_rate?: number
  outcome_sd?: number | null
  path?: 'binary' | 'continuous'
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
export interface NumericEstimate {
  point?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  ci_level?: number
  method?: string
  adjustment?: string[]
  sample_size?: number
  sensitivity_analysis?: Sensitivity
  dose_response_curve?: ({ x?: number; effect?: number } & Band)[]
  reference_point?: number | null
  decomposition?: {
    te?: Band; nde?: Band; nie?: Band; proportion_mediated?: Band
  }
  joint_effect?: Band & {
    treated?: Record<string, unknown>; control?: Record<string, unknown>
  }
  interaction?: Band & { order?: number; scale?: string }
  counterfactual_cell?: { lower?: number | null; upper?: number | null }
  probabilities_of_causation?: {
    pn?: { lower?: number | null; upper?: number | null }
    ps?: { lower?: number | null; upper?: number | null }
    pns?: { lower?: number | null; upper?: number | null }
  }
}

export interface LedgerEntry {
  claim: string
  layer?: string
  severity?: string
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

export interface QueryResult {
  status: string
  query_kind: string
  query_id?: string
  explanation?: string
  structural_result?: StructuralResult
  formula?: unknown
  data_gap_report?: DataGapReport
  bounds_result?: BoundsResult
  numeric_estimate?: NumericEstimate
  // Structural-layer point value (themis.run / apply_patch_and_run). Distinct
  // from numeric_estimate (themis.estimate, data-backed) — this is the number
  // a plug-in identification formula yields once θ is supplied (incl. via AI
  // priors). Shown in the verdict when no data-backed estimate is present.
  numeric_result?: { value: number }
  estimator_failure?: { estimator?: string; failure_type?: string; reason?: string }
  investigation_requests?: unknown[]
  extensions?: {
    assumption_ledger?: AssumptionLedger
    llm_proposed_review?: LlmProposedReview
  } & Record<string, unknown>
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
