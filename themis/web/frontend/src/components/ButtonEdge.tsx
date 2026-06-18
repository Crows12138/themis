import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useInternalNode,
  useReactFlow,
  useStore,
  Position,
  type EdgeProps,
  type ConnectionLineComponentProps,
} from '@xyflow/react'
import { getEdgeParams } from '../lib/floatingEdge'

/**
 * A floating edge that carries its own delete button.
 *
 * Floating: endpoints are computed from node geometry (getEdgeParams), so the
 * arrow connects border-to-border and reads straight in any direction — a
 * right-to-left cause no longer loops around to a fixed handle.
 *
 * Actions: click the edge to select it (deliberate — not a casual hover), which
 * reveals inline controls at its midpoint: "×" deletes it; "✓" (proposed edges
 * only) certifies it as a USER ASSERTION — clears the llm_proposal mark so the
 * unverified-proposal gap stops firing. The ✓ is intentionally the *only*
 * promotion you can click: vouching by domain knowledge is a click, but
 * "data-backed" can't be clicked into existence — it's earned by a separate
 * data-checking query, not asserted here.
 */
export function ButtonEdge({ id, source, target, markerStart, markerEnd, selected, data }: EdgeProps) {
  const sourceNode = useInternalNode(source)
  const targetNode = useInternalNode(target)
  const { deleteElements, setEdges } = useReactFlow()
  // How many edges connect this same pair, and where this one ranks — so
  // parallel edges (e.g. a cause X→Y alongside a confounder X↔Y) bow apart
  // instead of stacking on the exact same border-to-border line.
  const parallel = useStore((s) => {
    let n = 0
    let idx = 0
    for (const e of s.edges) {
      const same = (e.source === source && e.target === target) || (e.source === target && e.target === source)
      if (!same) continue
      if (e.id === id) idx = n
      n++
    }
    return { n, idx }
  })

  if (!sourceNode || !targetNode) return null

  const { sx, sy, tx, ty, sourcePos, targetPos } = getEdgeParams(sourceNode, targetNode)
  let edgePath: string
  let labelX: number
  let labelY: number
  if (parallel.n > 1) {
    // Bow each parallel edge to its own side of the straight line. A canonical
    // perpendicular (signed by the sorted node pair) keeps siblings in one frame
    // so they fan out symmetrically regardless of each edge's source/target order.
    const off = (parallel.idx - (parallel.n - 1) / 2) * 26
    let px = -(ty - sy)
    let py = tx - sx
    const len = Math.hypot(px, py) || 1
    px /= len
    py /= len
    if ((source ?? '') > (target ?? '')) { px = -px; py = -py }
    const cx = (sx + tx) / 2 + px * off
    const cy = (sy + ty) / 2 + py * off
    edgePath = `M ${sx},${sy} Q ${cx},${cy} ${tx},${ty}`
    labelX = (sx + 2 * cx + tx) / 4
    labelY = (sy + 2 * cy + ty) / 4
  } else {
    ;[edgePath, labelX, labelY] = getBezierPath({
      sourceX: sx,
      sourceY: sy,
      sourcePosition: sourcePos,
      targetX: tx,
      targetY: ty,
      targetPosition: targetPos,
    })
  }
  const show = selected
  const proposed = !!(data as { proposed?: boolean } | undefined)?.proposed

  // Certify = promote an llm_proposal edge to a plain user-asserted edge:
  // drop the proposed mark + faint styling, deselect. On the next run the edge
  // carries no llm_proposal annotation, so the unverified-proposal gap clears.
  const certify = () =>
    setEdges((es) =>
      es.map((e) =>
        e.id === id
          ? { ...e, selected: false, data: { ...(e.data ?? {}), proposed: false }, className: 'rf-edge rf-edge--cause' }
          : e,
      ),
    )

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerStart={markerStart} markerEnd={markerEnd} />
      {show ? (
        // Selected edge: inline ✓ (certify, proposed only) + × (delete), grouped.
        <EdgeLabelRenderer>
          <div
            className="edgeacts nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {proposed ? (
              <button
                className="edgeok"
                onClick={(e) => { e.stopPropagation(); certify() }}
                title="确认这条边（用户断言）—— 清除“未验证”标记；数据支撑是另一个验证功能"
                aria-label="确认这条边（用户断言）"
              >
                ✓
              </button>
            ) : null}
            <button
              className="edgedel"
              onClick={(e) => { e.stopPropagation(); deleteElements({ edges: [{ id }] }) }}
              title="删除这条边"
              aria-label="删除这条边"
            >
              ×
            </button>
          </div>
        </EdgeLabelRenderer>
      ) : proposed ? (
        // An unverified LLM-proposed edge wears a "?" until you click it (then
        // ✓ certify / × delete take over) — a clear mark, vs an edge you drew.
        <EdgeLabelRenderer>
          <span
            className="edgeq nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            title="AI 提议的假设，未验证 —— 点这条边可确认（用户断言）或删除"
          >
            ?
          </span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}

/** The connection line shown while dragging a new edge — floating too, so it
 *  previews where the finished edge will actually attach. */
export function FloatingConnectionLine({ toX, toY, fromNode }: ConnectionLineComponentProps) {
  if (!fromNode) return null
  const target = {
    id: '__cl__',
    measured: { width: 1, height: 1 },
    internals: { positionAbsolute: { x: toX, y: toY } },
    position: { x: toX, y: toY },
  } as unknown as Parameters<typeof getEdgeParams>[1]
  const { sx, sy } = getEdgeParams(fromNode, target)
  const [edgePath] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    targetX: toX,
    targetY: toY,
  })
  return (
    <g>
      <path className="rf-edge--cause" fill="none" stroke="#5a6a6f" strokeWidth={1.6} d={edgePath} />
      <circle cx={toX} cy={toY} r={3} fill="var(--surface-raise)" stroke="#5a6a6f" strokeWidth={1.6} />
    </g>
  )
}
