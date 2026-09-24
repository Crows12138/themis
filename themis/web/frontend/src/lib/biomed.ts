// Built-in turnkey scenario for the Estimate workspace: targeted drug ->
// tumor response, with disease severity as a confounder. Mirrors
// Themis_Demo's biomed scenario — the "核心一幕" where the unadjusted
// crude correlation and the backdoor-adjusted estimate visibly differ.

function atom(p: string) {
  return { predicate: p, args: [{ type: 'const', name: 'patient' }] }
}

export const BIOMED_PROGRAM: Record<string, unknown> = {
  version: '0.1',
  domain: { objects: [{ kind: 'object', name: 'patient' }] },
  statements: [
    { kind: 'variable', predicate: 'targeted_drug', domain: [true, false] },
    { kind: 'variable', predicate: 'tumor_response', domain: [true, false] },
    { kind: 'variable', predicate: 'disease_severity', domain: [true, false] },
    { kind: 'cause', from: atom('disease_severity'), to: atom('targeted_drug') },
    { kind: 'cause', from: atom('disease_severity'), to: atom('tumor_response') },
    { kind: 'cause', from: atom('targeted_drug'), to: atom('tumor_response') },
    {
      kind: 'query',
      id: 'q',
      query: {
        kind: 'effect',
        target: { atom: atom('tumor_response'), value: true },
        intervention: { atom: atom('targeted_drug'), value: true },
        given: [],
      },
    },
  ],
}

// Deterministic sample (seeded), so the demo numbers are reproducible.
function mulberry32(seed: number) {
  let a = seed
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function biomedSampleRows(n = 4000): Record<string, unknown>[] {
  const rnd = mulberry32(0)
  const rows: Record<string, unknown>[] = []
  for (let i = 0; i < n; i++) {
    const sev = rnd() < 0.45 ? 1 : 0
    const drug = rnd() < 0.3 + 0.4 * sev ? 1 : 0
    const p = Math.min(0.98, Math.max(0.02, 0.2 + 0.35 * drug - 0.25 * sev))
    const resp = rnd() < p ? 1 : 0
    rows.push({ targeted_drug: !!drug, tumor_response: !!resp, disease_severity: !!sev })
  }
  return rows
}

export function rowsToCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return ''
  const cols = Object.keys(rows[0])
  return [cols.join(','), ...rows.map((r) => cols.map((c) => String(r[c])).join(','))].join('\n')
}

// The crude contrast the adjusted estimate is set beside: mean(Y | treated)
// − mean(Y | untreated), nothing adjusted. It exists only where both halves
// of that sentence do — a treatment every row puts in one of two arms, and
// an outcome every row gives as a number — and is null otherwise, rather
// than a number over some other set of rows. It used to read every outcome
// as true-or-not, so a continuous outcome averaged to 0 in both arms and
// the page set a real estimate beside a crude difference of zero.
const ARM: Record<string, 0 | 1> = { true: 1, '1': 1, false: 0, '0': 0 }

function arm(v: unknown): 0 | 1 | null {
  if (v === true || v === 1) return 1
  if (v === false || v === 0) return 0
  if (typeof v === 'string') return ARM[v.trim().toLowerCase()] ?? null
  return null
}

function amount(v: unknown): number | null {
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v !== 'string' || v.trim() === '') return null
  const word = v.trim().toLowerCase()
  if (word === 'true' || word === 'false') return word === 'true' ? 1 : 0
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export function naiveDiff(rows: Record<string, unknown>[], x: string, y: string): number | null {
  let s1 = 0, n1 = 0, s0 = 0, n0 = 0
  for (const r of rows) {
    const side = arm(r[x])
    const yv = amount(r[y])
    if (side === null || yv === null) return null
    if (side === 1) { s1 += yv; n1++ } else { s0 += yv; n0++ }
  }
  if (n1 === 0 || n0 === 0) return null
  return s1 / n1 - s0 / n0
}

// Pull the effect query's treatment / outcome predicates from a program.
export function queryXY(program: Record<string, unknown> | undefined): { x?: string; y?: string } {
  const stmts = (program?.statements as Record<string, unknown>[] | undefined) ?? []
  for (const s of stmts) {
    if (s.kind === 'query') {
      const q = s.query as Record<string, unknown>
      const iv = q?.intervention as { atom?: { predicate?: string } } | undefined
      const tg = q?.target as { atom?: { predicate?: string } } | undefined
      return { x: iv?.atom?.predicate, y: tg?.atom?.predicate }
    }
  }
  return {}
}
