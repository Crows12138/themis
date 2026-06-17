import type { Node, Edge } from '@xyflow/react'
import { MarkerType } from '@xyflow/react'
import dagre from '@dagrejs/dagre'

interface Stmt {
  kind?: string
  predicate?: string
  from?: { predicate?: string }
  to?: { predicate?: string }
  left?: { predicate?: string }
  right?: { predicate?: string }
}

/** Lay a kernel_ast's DAG out left-to-right for a read-only xyflow view. */
export function programToFlow(program: Record<string, unknown> | undefined): { nodes: Node[]; edges: Edge[] } {
  const stmts = (program?.statements as Stmt[] | undefined) ?? []
  const vars: string[] = []
  const causes: { from: string; to: string }[] = []
  const bidir: { a: string; b: string }[] = []
  for (const s of stmts) {
    if (s.kind === 'variable' && s.predicate) vars.push(s.predicate)
    else if (s.kind === 'cause' && s.from?.predicate && s.to?.predicate) causes.push({ from: s.from.predicate, to: s.to.predicate })
    else if (s.kind === 'bidirected' && s.left?.predicate && s.right?.predicate) bidir.push({ a: s.left.predicate, b: s.right.predicate })
  }
  if (vars.length === 0) return { nodes: [], edges: [] }

  // Auto-layout with dagre (left-to-right). Only the directed cause edges drive
  // ranking; bidirected (latent-confounder) links don't impose a direction.
  // dagre reserves space for edges that skip a rank, so a confounder's two
  // arrows don't collapse onto the treatment→outcome line — nodes stagger
  // vertically instead of being strung out in one flat row.
  const dimOf = (v: string) => ({ width: Math.max(96, v.length * 8.5 + 32), height: 34 })
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
      data: { label: v },
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
      data: { kind: 'cause' },
      className: 'rf-edge rf-edge--cause',
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
  nodes: { id: string; data: { label: string } }[],
  edges: { source?: string | null; target?: string | null; data?: { kind?: string } }[],
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

  const labelById = new Map(nodes.map((n) => [n.id, n.data.label.trim()]))
  const origVar = new Map(stmts.filter((s) => s.kind === 'variable').map((s) => [s.predicate, s]))

  const varStmts = nodes.map((n) => {
    const p = n.data.label.trim()
    return origVar.get(p) ?? { kind: 'variable', predicate: p, domain: [true, false] }
  })
  const edgeStmts = edges.map((e) => {
    const a = labelById.get(e.source ?? '') ?? ''
    const b = labelById.get(e.target ?? '') ?? ''
    return e.data?.kind === 'bidirected'
      ? { kind: 'bidirected', left: mkAtom(a), right: mkAtom(b) }
      : { kind: 'cause', from: mkAtom(a), to: mkAtom(b) }
  })
  const other = stmts.filter((s) => !CANON_KINDS.includes(s.kind))
  return { ...base, statements: [...varStmts, ...edgeStmts, ...other] }
}
