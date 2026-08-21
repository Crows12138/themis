import { fill, type Lang, type Words } from './lib/language'
import type { AskResponse, Envelope, ExampleItem } from './types'

const KEY_STORAGE = 'themis.anthropic.key'

// The one sentence this module writes itself. Everything else it raises came
// from the server or from the platform, and neither is this file's to word.
const SAYS = {
  requestFailed: { zh: '请求失败（{status}）', en: 'Request failed ({status})' },
} satisfies Record<string, Words>

export function getApiKey(): string {
  return localStorage.getItem(KEY_STORAGE) ?? ''
}
export function setApiKey(key: string): void {
  if (key) localStorage.setItem(KEY_STORAGE, key)
  else localStorage.removeItem(KEY_STORAGE)
}

export class KernelError extends Error {
  stage?: string
  errorType?: string
  // Set when this file is the one that worded the failure. `message` stays
  // what `Error` needs it to be — a string, in whatever language its author
  // wrote — and `words` is the same failure with the language still open.
  // Which reader gets it is the renderer's question, so `errorText` below is
  // where the two meet, not here.
  words?: Words
  slots?: Record<string, string | number>
  constructor(
    message: string,
    opts: {
      stage?: string
      errorType?: string
      words?: Words
      slots?: Record<string, string | number>
    } = {},
  ) {
    super(message)
    this.stage = opts.stage
    this.errorType = opts.errorType
    this.words = opts.words
    this.slots = opts.slots
  }
}

// What to show a reader who hit an error.
//
// Three kinds arrive here and only one of them is ours: a failure this file
// worded (say it in the reader's language), one the server worded (hand it
// on — the server answers for its own language), and one the platform threw
// (hand that on too; a network stack's wording is not ours to translate).
export function errorText(e: unknown, lang: Lang): string {
  const err = e as KernelError
  return err?.words ? fill(err.words, lang, err.slots ?? {}) : String(err?.message ?? e)
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new KernelError(data.message || `request failed (${res.status})`, {
      stage: data.stage,
      errorType: data.error,
      words: data.message ? undefined : SAYS.requestFailed,
      slots: { status: res.status },
    })
  }
  return data as T
}

export function runProgram(program: Record<string, unknown>): Promise<Envelope> {
  return post<Envelope>('/api/run', { program })
}

export function estimate(program: Record<string, unknown>, rows: Record<string, unknown>[]): Promise<Envelope> {
  return post<Envelope>('/api/estimate', { program, rows })
}

export interface AuditRow {
  audit: string
  // Every language the build has, not the one this page wants: a row is
  // an artifact rather than a rendering, and one that had already chosen
  // would make two readers of one audit need two runs.
  words: Words
  ok: boolean
  refusal: string | null
}

/**
 * 独立复核 — hand the graph and one result back to the kernel and let it
 * re-derive from scratch, by every check that applies.
 *
 * Which checks apply is not asked here. There are thirteen; five are audits
 * of a different artifact altogether and reject a query_result with the same
 * exception they use for a failed audit, so a caller picking by hand is a
 * caller who can report "did not pass" for a check that was never about this
 * answer. themis.audits decides, and what comes back already carries the
 * sentence to show.
 */
export function auditResult(program: Record<string, unknown>, result: unknown): Promise<{ audits: AuditRow[] }> {
  return post<{ audits: AuditRow[] }>('/api/audit', { program, result })
}

export interface ClarifyPick {
  predicate: string
  fields: Record<string, string>
}

export interface MergedEnvelope extends Envelope {
  merged_program?: Record<string, unknown>
}

export function clarify(program: Record<string, unknown>, picks: ClarifyPick[]): Promise<MergedEnvelope> {
  return post<MergedEnvelope>('/api/clarify', { program, picks })
}

/** 数据不足兜底：让 LLM 给缺的概率分布填 common-knowledge 先验并重跑,
 * 得到一个带披露(extensions.llm_proposed_review)的点估计。需要 LLM 代理/key。 */
export function assume(program: Record<string, unknown>, apiKey?: string): Promise<MergedEnvelope> {
  return post<MergedEnvelope>('/api/assume', { program, api_key: apiKey || undefined })
}

export function render(program: Record<string, unknown>, nl: string, apiKey?: string): Promise<{ reply: string }> {
  return post<{ reply: string }>('/api/render', { program, nl, api_key: apiKey || undefined })
}

export function ask(nl: string, apiKey?: string): Promise<AskResponse> {
  return post<AskResponse>('/api/ask', { nl, api_key: apiKey || undefined })
}

export async function fetchExamples(): Promise<ExampleItem[]> {
  const res = await fetch('/api/examples')
  if (!res.ok) return []
  return res.json()
}
