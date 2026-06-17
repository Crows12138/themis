import { Position, type InternalNode, type Node } from '@xyflow/react'

/**
 * Floating-edge geometry — the React Flow canonical utils
 * (https://reactflow.dev/examples/edges/floating-edges). An edge connects to
 * the point on each node's border facing the other node, so an arrow reads
 * straight in ANY direction (right-to-left, diagonal, …) instead of looping
 * back around to a fixed handle.
 */

function dims(node: InternalNode): { w: number; h: number } {
  return {
    w: node.measured?.width ?? (node as unknown as Node).width ?? 120,
    h: node.measured?.height ?? (node as unknown as Node).height ?? 36,
  }
}

function absPos(node: InternalNode): { x: number; y: number } {
  return node.internals?.positionAbsolute ?? node.position
}

// The point on `intersectionNode`'s border on the line toward `targetNode`.
function getNodeIntersection(intersectionNode: InternalNode, targetNode: InternalNode) {
  const { w: iw, h: ih } = dims(intersectionNode)
  const iPos = absPos(intersectionNode)
  const tPos = absPos(targetNode)
  const { w: tw, h: th } = dims(targetNode)

  const w = iw / 2
  const h = ih / 2
  const x2 = iPos.x + w
  const y2 = iPos.y + h
  const x1 = tPos.x + tw / 2
  const y1 = tPos.y + th / 2

  const xx1 = (x1 - x2) / (2 * w) - (y1 - y2) / (2 * h)
  const yy1 = (x1 - x2) / (2 * w) + (y1 - y2) / (2 * h)
  const a = 1 / (Math.abs(xx1) + Math.abs(yy1) || 1)
  const xx3 = a * xx1
  const yy3 = a * yy1
  return { x: w * (xx3 + yy3) + x2, y: h * (-xx3 + yy3) + y2 }
}

// Which side of `node` the intersection point sits on.
function getEdgePosition(node: InternalNode, p: { x: number; y: number }): Position {
  const n = absPos(node)
  const { w, h } = dims(node)
  const nx = Math.round(n.x)
  const ny = Math.round(n.y)
  const px = Math.round(p.x)
  const py = Math.round(p.y)
  if (px <= nx + 1) return Position.Left
  if (px >= nx + w - 1) return Position.Right
  if (py <= ny + 1) return Position.Top
  if (py >= ny + h - 1) return Position.Bottom
  return Position.Top
}

export function getEdgeParams(source: InternalNode, target: InternalNode) {
  const sp = getNodeIntersection(source, target)
  const tp = getNodeIntersection(target, source)
  return {
    sx: sp.x,
    sy: sp.y,
    tx: tp.x,
    ty: tp.y,
    sourcePos: getEdgePosition(source, sp),
    targetPos: getEdgePosition(target, tp),
  }
}
