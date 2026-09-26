// What a correction changed, read off the two programs.
//
// The reader asked for one change in their own words, and a model carried it
// out on the whole program. What the model actually changed is a fact about
// the two programs, not something to take its word for, so it is computed
// here and shown beside the correction: a change the reader did not ask for
// is theirs to see and to undo.

type Statement = {
  kind?: string
  predicate?: string
  from?: { predicate?: string }
  to?: { predicate?: string }
  left?: { predicate?: string }
  right?: { predicate?: string }
  query?: unknown
}

export interface ReadingChange {
  addedVariables: string[]
  removedVariables: string[]
  addedEdges: string[]
  removedEdges: string[]
  questionChanged: boolean
  // Nothing at all differs, descriptions and annotations included.
  unchanged: boolean
}

function statements(program: Record<string, unknown>): Statement[] {
  const s = (program as { statements?: unknown }).statements
  return Array.isArray(s) ? (s as Statement[]) : []
}

function variables(program: Record<string, unknown>): Set<string> {
  return new Set(statements(program).filter((s) => s.kind === 'variable' && s.predicate).map((s) => s.predicate as string))
}

// A cause edge has a direction and a latent common cause does not, so the
// second is written with its two ends in one order whichever way it came.
function edges(program: Record<string, unknown>): Set<string> {
  const out = new Set<string>()
  for (const s of statements(program)) {
    if (s.kind === 'cause' && s.from?.predicate && s.to?.predicate) out.add(`${s.from.predicate}→${s.to.predicate}`)
    else if (s.kind === 'bidirected' && s.left?.predicate && s.right?.predicate)
      out.add([s.left.predicate, s.right.predicate].sort().join('↔'))
  }
  return out
}

// Two models write the same query with their keys in different orders; the
// question is the same question.
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.keys(value as object).sort().map((k) => [k, canonical((value as Record<string, unknown>)[k])]))
  return value
}

function questions(program: Record<string, unknown>): string {
  return JSON.stringify(statements(program).filter((s) => s.kind === 'query').map((s) => canonical(s.query)))
}

function minus(a: Set<string>, b: Set<string>): string[] {
  return [...a].filter((x) => !b.has(x)).sort()
}

export function changeBetween(before: Record<string, unknown>, after: Record<string, unknown>): ReadingChange {
  const [vb, va, eb, ea] = [variables(before), variables(after), edges(before), edges(after)]
  return {
    addedVariables: minus(va, vb),
    removedVariables: minus(vb, va),
    addedEdges: minus(ea, eb),
    removedEdges: minus(eb, ea),
    questionChanged: questions(before) !== questions(after),
    unchanged: JSON.stringify(canonical(before)) === JSON.stringify(canonical(after)),
  }
}
