// What a reader calls a variable, in place of the identifier it is written in.
//
// A program's predicates are identifiers: ASCII, one token each, the thing
// every formula, key and data column is written in. That is what the page
// used to show a reader — `quantitative_ability` on the graph and in every
// sentence about it, to somebody who asked in Chinese. A variable declaration
// can carry what the reader would call it (`name`, keyed by language), and
// this is where the page reads it.
//
// The identifier is not replaced in the program, the envelope, or anything
// sent back to the kernel. It is replaced where a string is SHOWN, token by
// token: an identifier is one token, so `P(y=True | do(x=True))`, `x → y` and
// `x@t-1` all read the same way without this file knowing their grammar.
//
// The names in force are ambient rather than passed. The page says a
// sentence by filling a template with what the kernel wrote, through one
// `fill` and some sixty functions above it, none of which knows which
// program is on the screen; `lang` reaches them as an argument because every
// one of them chooses words by it, and none of them chooses anything by the
// program. So the view that holds the program says whose names are in force
// while it is on the screen, and `fill` reads them.
import type { Lang } from './language'

type Named = ReadonlyMap<string, string>

const NOBODY: Named = new Map()
let inForce: Named = NOBODY

// An identifier as the program schema admits one. What it matches inside a
// longer string is every maximal run of identifier characters, so a predicate
// is replaced only where it stands whole.
const IDENTIFIER = /[A-Za-z_][A-Za-z0-9_]*/g
const WHOLE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/

export function isIdentifier(text: string): boolean {
  return WHOLE_IDENTIFIER.test(text)
}

type Declaration = { kind?: string; predicate?: unknown; name?: unknown }

// The names a program gives its variables in one language. A variable with
// no name in that language is absent, and is shown as its identifier: a name
// in another language is not a stand-in, for the reason nothing else on the
// page falls back across languages.
export function namesOf(program: Record<string, unknown> | undefined, lang: Lang): Map<string, string> {
  const out = new Map<string, string>()
  const statements = (program as { statements?: unknown } | undefined)?.statements
  if (!Array.isArray(statements)) return out
  for (const s of statements as Declaration[]) {
    if (s?.kind !== 'variable' || typeof s.predicate !== 'string') continue
    const said = (s.name as Record<string, unknown> | undefined)?.[lang]
    if (typeof said === 'string' && said.trim()) out.set(s.predicate, said.trim())
  }
  return out
}

// Whose names are in force from here on. Called by the view holding the
// program as it renders, so everything it renders below reads the same ones.
export function showNames(names: Named | null): void {
  inForce = names ?? NOBODY
}

// A string as a reader is shown it: each identifier that is a variable with
// a name, said by that name. Everything else is left exactly as it was.
export function named(text: string, names: Named = inForce): string {
  if (names.size === 0) return text
  return text.replace(IDENTIFIER, (token) => names.get(token) ?? token)
}

// One variable, as a reader is shown it.
export function nameOf(predicate: string, names: Named = inForce): string {
  return names.get(predicate) ?? predicate
}

// Data rows keyed the way the program writes its variables.
//
// A reader who is shown a variable as 数学能力 heads the column 数学能力,
// and the kernel reads a column by the identifier. So a column headed by a
// variable's name, in any language the program names it in, is that
// variable's column — unless the rows already have a column under the
// identifier itself, which is then the one meant, or two variables share the
// name, which then says nothing about which.
export function rowsAsWritten<T extends Record<string, unknown>>(
  rows: T[],
  program: Record<string, unknown> | undefined,
): Record<string, unknown>[] {
  const statements = (program as { statements?: unknown } | undefined)?.statements
  if (!Array.isArray(statements) || rows.length === 0) return rows
  const headed = new Set(Object.keys(rows[0]))
  const claims = new Map<string, Set<string>>()
  for (const s of statements as Declaration[]) {
    if (s?.kind !== 'variable' || typeof s.predicate !== 'string') continue
    if (headed.has(s.predicate) || !s.name || typeof s.name !== 'object') continue
    for (const said of Object.values(s.name as Record<string, unknown>)) {
      if (typeof said !== 'string' || !headed.has(said.trim())) continue
      const by = claims.get(said.trim()) ?? new Set<string>()
      by.add(s.predicate)
      claims.set(said.trim(), by)
    }
  }
  const as = new Map<string, string>()
  for (const [column, by] of claims) if (by.size === 1) as.set(column, [...by][0])
  if (as.size === 0) return rows
  return rows.map((row) => Object.fromEntries(Object.entries(row).map(([k, v]) => [as.get(k) ?? k, v])))
}
