import { fill, type Lang, type Words } from './lib/language'
import type { AskResponse, Envelope, ExampleItem } from './types'

const KEY_STORAGE = 'themis.anthropic.key'

// The one sentence this module writes itself. Everything else it raises came
// from the server or from the platform, and neither is this file's to word.
const SAYS = {
  requestFailed: { zh: '请求失败（{status}）', en: 'Request failed ({status})' },
  diagnostic: { zh: '诊断信息：{detail}', en: 'Diagnostic: {detail}' },
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
  // The failure with its language still open. `message` stays what `Error`
  // needs it to be — a string — and this is the same failure keyed by
  // language, from whichever side worded it. Which reader gets it is the
  // renderer's question, so `errorText` below is where the two meet.
  words?: Words
  slots?: Record<string, string | number>
  // Not the sentence: the exception's own text, for whoever diagnoses this.
  // It reaches the screen labelled as such rather than in place of the
  // sentence — see themis/web/failure.py, which draws that line server-side.
  diagnostic?: string
  constructor(
    message: string,
    opts: {
      stage?: string
      errorType?: string
      words?: Words
      slots?: Record<string, string | number>
      diagnostic?: string
    } = {},
  ) {
    super(message)
    this.stage = opts.stage
    this.errorType = opts.errorType
    this.words = opts.words
    this.slots = opts.slots
    this.diagnostic = opts.diagnostic
  }
}

// What to show a reader who hit an error.
//
// Two kinds arrive here now, and both carry `words`: a failure this file
// worded and one the server worded. The server used to hand over a finished
// string, which meant its language was decided before anyone knew who was
// reading — the same mistake as an f-string, one layer out. The third kind
// is the platform's; a network stack's wording is not ours to translate.
//
// The diagnostic follows the sentence rather than replacing it, and says
// what it is. A person who hit an internal error can paste it into a bug
// report; a person who hit a refusal has already been told what happened.
export function errorText(e: unknown, lang: Lang): string {
  const err = e as KernelError
  const said = err?.words ? fill(err.words, lang, err.slots ?? {}) : String(err?.message ?? e)
  return err?.diagnostic ? `${said}\n${fill(SAYS.diagnostic, lang, { detail: err.diagnostic })}` : said
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new KernelError(data.diagnostic || `request failed (${res.status})`, {
      stage: data.stage,
      errorType: data.error,
      words: data.words ?? SAYS.requestFailed,
      slots: data.words ? data.slots : { status: res.status },
      diagnostic: data.words ? data.diagnostic : undefined,
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

// The three calls whose answer is PROSE, and the only three that have to
// tell the server who is reading.
//
// Everywhere else this surface asks for an artifact and renders it here,
// so the reader's choice never crosses the wire. A reply written by a
// model has its language the moment it is written, and there is no later
// moment for this side to pick one in — so `lang` is a REQUIRED parameter
// on each of them rather than an optional one with a default. An optional
// one is a default a caller can forget, and forgetting it is exactly the
// defect: every one of these ran in the language the site was written in,
// whoever was reading.

/** 数据不足兜底：让 LLM 给缺的概率分布填 common-knowledge 先验并重跑,
 * 得到一个带披露(extensions.llm_proposed_review)的点估计。需要 LLM 代理/key。 */
export function assume(program: Record<string, unknown>, lang: Lang, apiKey?: string): Promise<MergedEnvelope> {
  return post<MergedEnvelope>('/api/assume', { program, lang, api_key: apiKey || undefined })
}

export function render(program: Record<string, unknown>, nl: string, lang: Lang, apiKey?: string): Promise<{ reply: string }> {
  return post<{ reply: string }>('/api/render', { program, nl, lang, api_key: apiKey || undefined })
}

export function ask(nl: string, lang: Lang, apiKey?: string): Promise<AskResponse> {
  return post<AskResponse>('/api/ask', { nl, lang, api_key: apiKey || undefined })
}

export async function fetchExamples(): Promise<ExampleItem[]> {
  const res = await fetch('/api/examples')
  if (!res.ok) return []
  return res.json()
}
