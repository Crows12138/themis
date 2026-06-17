import { createContext, useContext } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type EdgeProps,
} from '@xyflow/react'

/** Which edge the pointer is currently over (null = none). Lets the delete
 *  button reveal on hover without re-mapping every edge's data on each move. */
export const EdgeHoverContext = createContext<string | null>(null)

/**
 * An edge that carries its own delete button — the React Flow canonical pattern
 * (BaseEdge for the path + EdgeLabelRenderer for an overlay control at the edge
 * midpoint). The "×" reveals on hover or when the edge is selected and removes
 * exactly that edge via deleteElements (which flows through the controlled
 * onEdgesChange, so the canvas state stays the single source of truth).
 */
export function ButtonEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerStart,
  markerEnd,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })
  const { deleteElements } = useReactFlow()
  const hovered = useContext(EdgeHoverContext)
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
