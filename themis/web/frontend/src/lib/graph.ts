import type { Node, Edge } from '@xyflow/react'
import { MarkerType } from '@xyflow/react'

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

  // layered x by longest-path depth from sources; y by order within layer.
  const depth = new Map<string, number>(vars.map((v) => [v, 0]))
  for (let pass = 0; pass < vars.length; pass++) {
    let changed = false
    for (const c of causes) {
      const d = (depth.get(c.from) ?? 0) + 1
      if (d > (depth.get(c.to) ?? 0)) {
        depth.set(c.to, d)
        changed = true
      }
    }
    if (!changed) break
  }
  const perLayer = new Map<number, number>()
  const nodes: Node[] = vars.map((v) => {
    const d = depth.get(v) ?? 0
    const row = perLayer.get(d) ?? 0
    perLayer.set(d, row + 1)
    return {
      id: v,
      position: { x: d * 210, y: row * 96 },
      data: { label: v },
      type: 'plain',
      draggable: true,
    }
  })

  const edges: Edge[] = [
    ...causes.map((c, i) => ({
      id: `c${i}`,
      source: c.from,
      target: c.to,
      style: { stroke: '#5a6a6f', strokeWidth: 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#5a6a6f' },
    })),
    ...bidir.map((b, i) => ({
      id: `b${i}`,
      source: b.a,
      target: b.b,
      style: { stroke: '#a23b2c', strokeWidth: 1.6, strokeDasharray: '5 4' },
      markerStart: { type: MarkerType.ArrowClosed, color: '#a23b2c' },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#a23b2c' },
    })),
  ]
  return { nodes, edges }
}
