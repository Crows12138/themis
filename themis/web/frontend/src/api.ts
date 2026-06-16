import type { AskResponse, Envelope, ExampleItem } from './types'

const KEY_STORAGE = 'themis.anthropic.key'

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
  constructor(message: string, opts: { stage?: string; errorType?: string } = {}) {
    super(message)
    this.stage = opts.stage
    this.errorType = opts.errorType
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new KernelError(data.message || `请求失败（${res.status}）`, {
      stage: data.stage,
      errorType: data.error,
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
