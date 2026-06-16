// Render a kernel formula node (identification formula) to a readable
// string — ported from Themis_Demo.fmt_formula.

interface AtomLike {
  atom?: { predicate?: string; value?: unknown }
  predicate?: string
  value?: unknown
}

function atomStr(a: AtomLike): string {
  const inner = a.atom ?? a
  const pred = inner.predicate ?? '?'
  const val = a.value ?? inner.value
  if (val === true) return pred
  if (val === false) return `¬${pred}`
  if (val && typeof val === 'object' && (val as { kind?: string }).kind === 'var_ref') return `${pred}=z`
  if (val === undefined || val === null) return pred
  return `${pred}=${String(val)}`
}

export function fmtFormula(node: unknown): string {
  if (!node || typeof node !== 'object') return String(node ?? '')
  const n = node as Record<string, unknown>
  switch (n.kind) {
    case 'probability_ref': {
      const tgt = atomStr(n.target as AtomLike)
      const given = (n.given as AtomLike[] | undefined) ?? []
      return given.length ? `P(${tgt} | ${given.map(atomStr).join(', ')})` : `P(${tgt})`
    }
    case 'sum': {
      const over = (n.over as { predicate?: string } | undefined)?.predicate ?? 'z'
      return `Σ_${over} [ ${fmtFormula(n.body)} ]`
    }
    case 'product':
      return ((n.terms as unknown[]) ?? []).map(fmtFormula).join(' · ')
    case 'fraction':
      return `( ${fmtFormula(n.numerator)} ) / ( ${fmtFormula(n.denominator)} )`
    default:
      return (n.kind as string) ?? '?'
  }
}
