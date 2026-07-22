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

export interface NumericEstimate {
  point: number
  ci_lower?: number | null
  ci_upper?: number | null
  ci_level?: number
  method?: string
  adjustment?: string[]
  sample_size?: number
  sensitivity_analysis?: Sensitivity
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
