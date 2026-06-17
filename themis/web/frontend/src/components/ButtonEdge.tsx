import { createContext, useContext } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useInternalNode,
  useReactFlow,
  Position,
  type EdgeProps,
  type ConnectionLineComponentProps,
} from '@xyflow/react'
import { getEdgeParams } from '../lib/floatingEdge'

/** Which edge the pointer is currently over (null = none). Lets the delete
 *  button reveal on hover without re-mapping every edge's data on each move. */
export const EdgeHoverContext = createContext<string | null>(null)

/**
 * A floating edge that carries its own delete button.
 *
 * Floating: endpoints are computed from node geometry (getEdgeParams), so the
 * arrow connects border-to-border and reads straight in any direction — a
 * right-to-left cause no longer loops around to a fixed handle.
 *
 * Delete: the React Flow canonical pattern (BaseEdge + EdgeLabelRenderer) puts a
 * "×" at the edge midpoint that reveals on hover/selection and removes exactly
 * that edge via deleteElements (flows through controlled onEdgesChange).
 */
export function ButtonEdge({ id, source, target, markerStart, markerEnd, selected }: EdgeProps) {
  const sourceNode = useInternalNode(source)
  const targetNode = useInternalNode(target)
  const hovered = useContext(EdgeHoverContext)
  const { deleteElements } = useReactFlow()

  if (!sourceNode || !targetNode) return null

  const { sx, sy, tx, ty, sourcePos, targetPos } = getEdgeParams(sourceNode, targetNode)
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition: sourcePos,
    targetX: tx,
    targetY: ty,
    targetPosition: targetPos,
  })
  const show = selected || hovered === id

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerStart={markerStart} markerEnd={markerEnd} />
      {show ? (
        <EdgeLabelRenderer>
          <button
            className="edgedel nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            onClick={(e) => {
              e.stopPropagation()
              deleteElements({ edges: [{ id }] })
            }}
            title="删除这条边"
            aria-label="删除这条边"
          >
            ×
          </button>
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
