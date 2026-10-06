import type { Node, Edge } from '@xyflow/react'
import { MarkerType } from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import { DEFAULT_LANG, type Lang } from './language'
import { isIdentifier } from './names'

interface Stmt {
  kind?: string
  predicate?: string
  name?: Record<string, string>
  from?: { predicate?: string }
  to?: { predicate?: string }
  left?: { predicate?: string }
  right?: { predicate?: string }
}

/**
 * A variable on the canvas.
 *
 * `label` is the text on the node: what the reader is shown and, where the
 * node is editable, what they type — any characters, in their own language.
 * It is not the identifier the program is written in. A node that came from a
 * program remembers that (`predicate`), with the names the program gave it by
 * language (`said`) and the text it was last given from them (`shownAs`), so
 * that a text the reader has not touched is still the variable it came from.
 * Which identifier a node is written as is decided when the graph is read
 * back (`written`), not while somebody is typing.
 */
export type VarData = {
  label: string
  predicate?: string
  said?: Record<string, string>
  shownAs?: string
}

// A node as the canvas library hands it over: its data is a bag to the
// library, and is a `VarData` to this file.
type OnCanvas = { id: string; data: Record<string, unknown> }

// How wide a label draws in the node's monospace face: a CJK character takes
// about the width of two Latin ones.
const drawnWidth = (text: string) =>
  [...text].reduce((w, ch) => w + (ch.charCodeAt(0) > 0x2e7f ? 15 : 8.5), 0)

/** Lay a kernel_ast's DAG out left-to-right for a read-only xyflow view. */
export function programToFlow(
  program: Record<string, unknown> | undefined,
  lang: Lang = DEFAULT_LANG,
): { nodes: Node[]; edges: Edge[] } {
  const stmts = (program?.statements as Stmt[] | undefined) ?? []
  const vars: string[] = []
  const saidBy = new Map<string, Record<string, string>>()
  const causes: { from: string; to: string; proposed?: boolean }[] = []
  const bidir: { a: string; b: string }[] = []
  for (const s of stmts) {
    if (s.kind === 'variable' && s.predicate) {
      vars.push(s.predicate)
      if (s.name && typeof s.name === 'object') saidBy.set(s.predicate, s.name)
    }
    else if (s.kind === 'cause' && s.from?.predicate && s.to?.predicate)
      causes.push({ from: s.from.predicate, to: s.to.predicate, proposed: (s as AnyStmt).annotations?.source === 'llm_proposal' })
    else if (s.kind === 'bidirected' && s.left?.predicate && s.right?.predicate) bidir.push({ a: s.left.predicate, b: s.right.predicate })
  }
  if (vars.length === 0) return { nodes: [], edges: [] }

  // Classify every node by its structural role relative to the query (exposure,
  // outcome, confounder, mediator, collider, instrument candidate, other cause).
  const { qx, qy } = parseQuery(program)
  const roleMap = classifyNodes(causes, vars, qx, qy)

  // Auto-layout with dagre (left-to-right). Only the directed cause edges drive
  // ranking; bidirected (latent-confounder) links don't impose a direction.
  // dagre reserves space for edges that skip a rank, so a confounder's two
  // arrows don't collapse onto the treatment→outcome line — nodes stagger
  // vertically instead of being strung out in one flat row.
  const shown = (v: string) => saidBy.get(v)?.[lang]?.trim() || v
  const dimOf = (v: string) => ({ width: Math.max(96, drawnWidth(shown(v)) + 32), height: 34 })
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 48, ranksep: 96, marginx: 12, marginy: 12 })
  for (const v of vars) g.setNode(v, dimOf(v))
  for (const c of causes) if (g.hasNode(c.from) && g.hasNode(c.to)) g.setEdge(c.from, c.to)
  dagre.layout(g)

  const nodes: Node[] = vars.map((v) => {
    const { width, height } = dimOf(v)
    const p = g.node(v) as { x: number; y: number } | undefined // dagre returns the node CENTER
    return {
      id: v,
      position: { x: (p?.x ?? 0) - width / 2, y: (p?.y ?? 0) - height / 2 },
      data: { label: shown(v), predicate: v, said: saidBy.get(v), shownAs: shown(v), role: roleMap.get(v) },
      type: 'plain',
      // Seed a size so edges anchor on the first frame, before React Flow's
      // ResizeObserver measures the node (a cold mount otherwise paints no edges).
      initialWidth: width,
      initialHeight: height,
    }
  })

  const edges: Edge[] = [
    // Colour/weight live in CSS (.rf-edge--*) not inline `style`, so the
    // .selected / :hover states can layer over them without !important.
    // Floating edges (type 'button') compute their endpoints from node
    // geometry, so no source/target handle anchoring is needed.
    ...causes.map((c, i) => ({
      id: `c${i}`,
      source: c.from,
      target: c.to,
      type: 'button',
      data: { kind: 'cause', proposed: !!c.proposed },
      // proposed = an LLM-guessed edge, not data-backed or user-drawn → rendered
      // faint so the user can see which arrows are still just hypotheses.
      className: c.proposed ? 'rf-edge rf-edge--cause rf-edge--proposed' : 'rf-edge rf-edge--cause',
      markerEnd: { type: MarkerType.ArrowClosed, color: '#5a6a6f' },
    })),
    ...bidir.map((b, i) => ({
      id: `b${i}`,
      source: b.a,
      target: b.b,
      type: 'button',
      data: { kind: 'bidirected' },
      className: 'rf-edge rf-edge--bidir',
      markerStart: { type: MarkerType.ArrowClosed, color: '#a23b2c' },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#a23b2c' },
    })),
  ]
  return { nodes, edges }
}

/**
 * What a graph on the canvas says, as one comparable string: its variables
 * and its edges, by name, in no particular order. Where a node sits is not
 * part of it, so dragging one changes nothing here.
 *
 * Whether a cause edge is still the model's proposal IS part of it: deleting
 * a proposed edge and drawing it again makes it the reader's own, which
 * re-runs to a different ledger.
 */
export function graphShape(
  nodes: OnCanvas[],
  edges: { source?: string | null; target?: string | null; data?: { kind?: string; proposed?: boolean } }[],
): string {
  // By identifier, not by the text on the node: a variable shown under its
  // name in one language and another is the same variable, and the kernel
  // was told the identifier either way.
  const as = written(nodes, DEFAULT_LANG)
  const label = new Map(nodes.map((n) => [n.id, as.get(n.id)?.predicate ?? '']))
  const name = (id?: string | null) => label.get(id ?? '') ?? ''
  const said = edges.map((e) => {
    const a = name(e.source), b = name(e.target)
    if (e.data?.kind === 'bidirected') return ['bidirected', ...[a, b].sort()].join('\u0000')
    return [e.data?.proposed ? 'proposed' : 'cause', a, b].join('\u0000')
  })
  return JSON.stringify([[...label.values()].sort(), said.sort()])
}

/**
 * Which identifier each variable on the canvas is written as, and the names
 * it carries, read off the text on its node.
 *
 * The text is the reader's; the identifier is the program's. They coincide
 * when the reader typed something that is an identifier, which is what the
 * canvas used to require of everybody by turning every other character into
 * an underscore as it was typed. Otherwise:
 *
 *   - a node that came from a program and whose text nobody changed is the
 *     variable it came from, names and all;
 *   - one whose text was changed to an identifier is renamed to it, as it
 *     always was;
 *   - one whose text was changed to anything else keeps its identifier and
 *     takes the text as its name in the reader's language;
 *   - a new node with a text that is not an identifier is given one (`v1`,
 *     `v2`, … past any in use) and takes the text as its name.
 *
 * Decided here, when the graph is read, and not while somebody types: an
 * input method composes a Chinese word out of Latin letters, and a rule run
 * per keystroke would mint an identifier from the half-typed pinyin.
 */
export function written(
  nodes: OnCanvas[],
  lang: Lang,
): Map<string, { predicate: string; name?: Record<string, string> }> {
  const out = new Map<string, { predicate: string; name?: Record<string, string> }>()
  const taken = new Set<string>()
  const unnamed: { id: string; text: string }[] = []
  for (const n of nodes) {
    const d = n.data as VarData
    const text = String(d.label ?? '').trim()
    let as: { predicate: string; name?: Record<string, string> }
    if (d.predicate && (text === '' || text === (d.shownAs ?? d.predicate))) as = { predicate: d.predicate, name: d.said }
    else if (text === '' || isIdentifier(text)) as = { predicate: text }
    else if (d.predicate) as = { predicate: d.predicate, name: { ...d.said, [lang]: text } }
    else { unnamed.push({ id: n.id, text }); continue }
    out.set(n.id, as)
    taken.add(as.predicate)
  }
  let k = 0
  for (const u of unnamed) {
    let predicate: string
    do { predicate = `v${++k}` } while (taken.has(predicate))
    taken.add(predicate)
    out.set(u.id, { predicate, name: { [lang]: u.text } })
  }
  return out
}

type AnyStmt = Record<string, any>
const CANON_KINDS = ['variable', 'cause', 'bidirected']

/**
 * Re-serialize an edited graph back into a kernel_ast. Only the variable set
 * and the cause / bidirected edges are taken from the graph — the original
 * query, domain, variable framing fields, and atom arg-shapes are preserved
 * so an edit (delete an edge, add a confounder) re-runs the *same* question
 * on the *same* operationalization, just with a different structure.
 */
export function graphToProgram(
  base: Record<string, unknown>,
  nodes: OnCanvas[],
  edges: { source?: string | null; target?: string | null; data?: { kind?: string; proposed?: boolean } }[],
  lang: Lang = DEFAULT_LANG,
): Record<string, unknown> {
  const stmts = ((base?.statements as AnyStmt[]) ?? [])
  // Harvest a canonical atom per predicate from the base so re-emitted edges
  // keep the exact arg shape the kernel saw originally.
  const atomFor = new Map<string, AnyStmt>()
  const harvest = (a?: AnyStmt) => { if (a && a.predicate && !atomFor.has(a.predicate)) atomFor.set(a.predicate, a) }
  for (const s of stmts) {
    harvest(s.from); harvest(s.to); harvest(s.left); harvest(s.right)
    const q = s.query as AnyStmt | undefined
    if (q) {
      harvest(q.target); harvest(q.intervention?.atom); harvest(q.observed)
      harvest(q.counterfactual_target); harvest(q.counterfactual_intervention)
      for (const g of (q.given ?? [])) harvest(g?.atom ?? g)
    }
  }
  const objs = (base as AnyStmt)?.domain?.objects as AnyStmt[] | undefined
  const firstObj = objs?.[0]?.name ?? 'me'
  const mkAtom = (pred: string): AnyStmt =>
    atomFor.get(pred) ?? { predicate: pred, args: [{ type: 'const', name: firstObj }] }

  const as = written(nodes, lang)
  const labelById = new Map(nodes.map((n) => [n.id, as.get(n.id)?.predicate ?? '']))
  const origVar = new Map(stmts.filter((s) => s.kind === 'variable').map((s) => [s.predicate, s]))

  const varStmts = nodes.map((n) => {
    const { predicate: p, name } = as.get(n.id) ?? { predicate: '' }
    const { name: _was, ...decl } = (origVar.get(p) ?? { kind: 'variable', predicate: p, domain: [true, false] }) as AnyStmt
    return name && Object.keys(name).length ? { ...decl, name } : decl
  })
  const edgeStmts = edges.map((e) => {
    const a = labelById.get(e.source ?? '') ?? ''
    const b = labelById.get(e.target ?? '') ?? ''
    if (e.data?.kind === 'bidirected') return { kind: 'bidirected', left: mkAtom(a), right: mkAtom(b) }
    // Keep the llm_proposal mark so an unverified edge stays flagged through a
    // re-run; only an edge the user actually drew (no mark) reads as confirmed.
    return { kind: 'cause', from: mkAtom(a), to: mkAtom(b), ...(e.data?.proposed ? { annotations: { source: 'llm_proposal' } } : {}) }
  })
  const other = stmts.filter((s) => !CANON_KINDS.includes(s.kind))
  return { ...base, statements: [...varStmts, ...edgeStmts, ...other] }
}

/** Directed reachability over CAUSE edges only (bidirected ↔ links impose no
 *  direction). Used to stop a drawn edge from closing a cycle — a causal DAG
 *  can't have A→B and B→A. */
export function reaches(
  edges: { source?: string | null; target?: string | null; data?: { kind?: string } }[],
  start: string,
  goal: string,
): boolean {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if ((e.data?.kind ?? 'cause') !== 'cause' || !e.source || !e.target) continue
    ;(adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target)
  }
  const seen = new Set<string>()
  const stack = [start]
  while (stack.length) {
    const n = stack.pop() as string
    if (n === goal) return true
    if (seen.has(n)) continue
    seen.add(n)
    for (const m of adj.get(n) ?? []) stack.push(m)
  }
  return false
}

export type NodeRole = 'exposure' | 'outcome' | 'confounder' | 'mediator' | 'collider' | 'instrument' | 'causeY'

/**
 * Classify every variable by its textbook structural role relative to the query
 * (x = exposure, y = outcome), over the directed cause graph:
 *   mediator   — on a directed x→…→y path   (descendant of x ∧ ancestor of y)
 *   confounder — back-door common cause      (ancestor of x ∧ reaches y NOT through x)
 *   collider   — two arrowheads meet         (in-degree ≥ 2)
 *   instrument — upstream of x, reaches y only via x (ancestor of x, not a back-door) — a CANDIDATE
 *   causeY     — other cause of y            (ancestor of y, unrelated to x)
 * The confounder/instrument split is the whole subtlety: BOTH are ancestors of x
 * that reach y, but a confounder reaches y by a path avoiding x (the back-door
 * that biases the estimate) while an instrument reaches y ONLY through x. So we
 * test "reaches y without passing through x", not plain "ancestor of y".
 * These structural roles are node-intrinsic facts. Whether a confounder must be
 * adjusted, or an instrument is *valid*, is a derived/assumption-laden question,
 * not encoded here.
 */
export function classifyNodes(
  causes: { from: string; to: string }[],
  vars: string[],
  x: string,
  y: string,
): Map<string, NodeRole> {
  const out = new Map<string, NodeRole>()
  if (!x || !y) return out
  const succ = new Map<string, string[]>()
  const pred = new Map<string, string[]>()
  for (const c of causes) {
    ;(succ.get(c.from) ?? succ.set(c.from, []).get(c.from)!).push(c.to)
    ;(pred.get(c.to) ?? pred.set(c.to, []).get(c.to)!).push(c.from)
  }
  const reach = (start: string, adj: Map<string, string[]>) => {
    const seen = new Set<string>()
    const st = [...(adj.get(start) ?? [])]
    while (st.length) {
      const n = st.pop() as string
      if (seen.has(n)) continue
      seen.add(n)
      for (const m of adj.get(n) ?? []) st.push(m)
    }
    return seen
  }
  const descX = reach(x, succ)
  const ancX = reach(x, pred)
  const ancY = reach(y, pred)
  // Nodes that reach y by a directed path that does NOT pass through x: a
  // backward walk from y over predecessors that never traverses x. This is what
  // separates a back-door confounder from an instrument (whose only route to y
  // is through x, so it drops out here).
  const ancYnotX = (() => {
    const seen = new Set<string>()
    const st = (pred.get(y) ?? []).filter((n) => n !== x)
    while (st.length) {
      const n = st.pop() as string
      if (seen.has(n) || n === x) continue
      seen.add(n)
      for (const m of pred.get(n) ?? []) if (m !== x) st.push(m)
    }
    return seen
  })()
  for (const v of vars) {
    if (v === x) { out.set(v, 'exposure'); continue }
    if (v === y) { out.set(v, 'outcome'); continue }
    const inDeg = (pred.get(v) ?? []).length
    if (descX.has(v) && ancY.has(v)) out.set(v, 'mediator')
    else if (ancX.has(v) && ancYnotX.has(v)) out.set(v, 'confounder')
    else if (inDeg >= 2) out.set(v, 'collider')
    else if (ancX.has(v)) out.set(v, 'instrument')
    else if (ancY.has(v)) out.set(v, 'causeY')
  }
  return out
}

const atomPred = (a: AnyStmt | undefined): string =>
  (a?.atom?.predicate ?? a?.predicate ?? '') as string

/** Pull the (intervention, target, kind) out of a program's query statement,
 *  tolerating the effect / identify / counterfactual shapes. */
export function parseQuery(program: Record<string, unknown> | undefined): {
  qx: string
  qy: string
  qkind: 'effect' | 'identify' | 'counterfactual'
} {
  const stmts = (program?.statements as AnyStmt[] | undefined) ?? []
  const q = stmts.find((s) => s.kind === 'query' && s.query)?.query as AnyStmt | undefined
  if (!q) return { qx: '', qy: '', qkind: 'effect' }
  const qkind = q.kind === 'identify' || q.kind === 'counterfactual' ? q.kind : 'effect'
  if (qkind === 'counterfactual') {
    return { qx: atomPred(q.counterfactual_intervention) || atomPred(q.observed), qy: atomPred(q.counterfactual_target), qkind }
  }
  return { qx: atomPred(q.intervention), qy: atomPred(q.target), qkind }
}

/** Hydrate a hand-editable builder (nodes / edges / query) from a kernel_ast,
 *  so a result's graph can be carried into the Build / Estimate canvas instead
 *  of redrawn. Positions come from the same dagre layout as the read-only view. */
export function programToBuilder(program: Record<string, unknown> | undefined): {
  nodes: { id: string; label: string; position: { x: number; y: number } }[]
  edges: { source: string; target: string; kind: 'cause' | 'bidirected' }[]
  qx: string
  qy: string
  qkind: 'effect' | 'identify' | 'counterfactual'
} {
  const { nodes, edges } = programToFlow(program)
  const q = parseQuery(program)
  return {
    nodes: nodes.map((n) => ({ id: n.id, label: (n.data as { label: string }).label, position: n.position })),
    edges: edges.map((e) => ({
      source: e.source as string,
      target: e.target as string,
      kind: (e.data as { kind?: string })?.kind === 'bidirected' ? 'bidirected' : 'cause',
    })),
    qx: q.qx,
    qy: q.qy,
    qkind: q.qkind,
  }
}
