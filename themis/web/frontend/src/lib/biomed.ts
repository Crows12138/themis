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

// Naive crude correlation: mean(Y | X=1) - mean(Y | X=0).
export function naiveDiff(rows: Record<string, unknown>[], x: string, y: string): number | null {
  let s1 = 0, n1 = 0, s0 = 0, n0 = 0
  const truthy = (v: unknown) => v === true || v === 1 || v === '1' || v === 'true' || v === 'True'
  for (const r of rows) {
    const yv = truthy(r[y]) ? 1 : 0
    if (truthy(r[x])) { s1 += yv; n1++ } else { s0 += yv; n0++ }
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
