// Render a kernel formula node (identification formula) to a readable
// string. Mirrors themis/output/formula_text.py — the browser cannot
// import that table, so the two are held together by a test that reads
// this file for the node kinds the grammar declares.
//
// Two things this used to get wrong, both found by reading the schema
// rather than this file: a `constant` node fell to the default and
// rendered as the word "constant", and every bound value printed as the
// letter `z` while the sum's subscript came from the atom — so one
// formula named one variable two ways, and nested sums collapsed
// distinct bindings into one letter.

interface AtomLike {
  atom?: { predicate?: string; value?: unknown }
  predicate?: string
  value?: unknown
}

type Env = { bound: Record<string, string>; pinned: Set<string> }

function predOf(a: AtomLike | undefined): string {
  const inner = a?.atom ?? a
  return inner?.predicate ?? '?'
}

// A formula names variables, not instances: every atom in one expression
// carries the same arguments, so printing them distinguishes nothing.
function atomStr(a: AtomLike | undefined, env: Env): string {
  const pred = predOf(a)
  if (!a || !('value' in a)) return pred
  const val = a.value
  if (val === true) return pred
  if (val === false) return `¬${pred}`
  if (val && typeof val === 'object' && (val as { kind?: string }).kind === 'var_ref') {
    // The sum that bound this name ranges over this very atom, so the
    // atom IS the variable: P(z), never P(z=z). The symbol may be primed.
    return env.bound[(val as { name: string }).name] ?? pred
  }
  if (val === undefined || val === null) return pred
  return `${pred}=${String(val)}`
}

// Predicates the formula holds at a value somewhere. A front-door
// estimand sums over the treatment while the treatment is also held at
// the intervened value, and the two occurrences sit in different
// subtrees — so a sum cannot tell by reading its own body.
function pinnedPredicates(node: unknown, out: Set<string> = new Set()): Set<string> {
  if (!node || typeof node !== 'object') return out
  const n = node as Record<string, unknown>
  if (n.kind === 'probability_ref') {
    const atoms = [n.target as AtomLike, ...((n.given as AtomLike[]) ?? [])]
    for (const a of atoms) {
      if (!a || !('value' in a)) continue
      const v = a.value
      if (v && typeof v === 'object' && (v as { kind?: string }).kind === 'var_ref') continue
      out.add(predOf(a))
    }
    return out
  }
  for (const key of ['body', 'numerator', 'denominator']) pinnedPredicates(n[key], out)
  for (const t of (n.terms as unknown[]) ?? []) pinnedPredicates(t, out)
  return out
}

function render(node: unknown, env: Env): string {
  if (!node || typeof node !== 'object') return String(node ?? '')
  const n = node as Record<string, unknown>
  switch (n.kind) {
    case 'constant':
      return String(n.value)
    case 'probability_ref': {
      const tgt = atomStr(n.target as AtomLike, env)
      const given = ((n.given as AtomLike[] | undefined) ?? []).map((g) => atomStr(g, env))
      return given.length ? `P(${tgt} | ${given.join(', ')})` : `P(${tgt})`
    }
    case 'sum': {
      const over = predOf(n.over as AtomLike)
      const name = (n.bind as { name?: string } | undefined)?.name
      const symbol = env.pinned.has(over) ? `${over}'` : over
      const inner: Env = { bound: { ...env.bound }, pinned: env.pinned }
      if (name) inner.bound[name] = symbol
      return `Σ_${symbol} [ ${render(n.body, inner)} ]`
    }
    case 'product':
      return ((n.terms as unknown[]) ?? []).map((t) => render(t, env)).join(' · ')
    case 'fraction':
      return `( ${render(n.numerator, env)} ) / ( ${render(n.denominator, env)} )`
    default:
      return (n.kind as string) ?? '?'
  }
}

export function fmtFormula(node: unknown): string {
  return render(node, { bound: {}, pinned: pinnedPredicates(node) })
}
