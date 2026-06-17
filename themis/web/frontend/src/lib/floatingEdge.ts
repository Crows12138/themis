import { Position, type InternalNode, type Node } from '@xyflow/react'

/**
 * Dynamic edge anchoring. Instead of pinning an edge to fixed source-right /
 * target-left handles (which makes a right-to-left edge loop all the way
 * around), pick — live, from node geometry — the side of each node that faces
 * the other, and anchor at the MIDDLE of that side. The arrow then meets the
 * box square-on at a clean point and reads straight in any direction, with no
 * loop. The dominant axis decides left/right vs top/bottom, so a tall stack
 * connects top-to-bottom and a wide row connects side-to-side.
 */

function box(node: InternalNode) {
  const w = node.measured?.width ?? (node as unknown as Node).width ?? 120
  const h = node.measured?.height ?? (node as unknown as Node).height ?? 36
  const p = node.internals?.positionAbsolute ?? node.position
  return { x: p.x, y: p.y, w, h, cx: p.x + w / 2, cy: p.y + h / 2 }
}

export function getEdgeParams(source: InternalNode, target: InternalNode) {
  const s = box(source)
  const t = box(target)
  const dx = t.cx - s.cx
  const dy = t.cy - s.cy

  if (Math.abs(dx) >= Math.abs(dy)) {
    const right = dx >= 0
    return {
      sx: right ? s.x + s.w : s.x,
      sy: s.cy,
      tx: right ? t.x : t.x + t.w,
      ty: t.cy,
      sourcePos: right ? Position.Right : Position.Left,
      targetPos: right ? Position.Left : Position.Right,
    }
  }
  const down = dy >= 0
  return {
    sx: s.cx,
    sy: down ? s.y + s.h : s.y,
    tx: t.cx,
    ty: down ? t.y : t.y + t.h,
    sourcePos: down ? Position.Bottom : Position.Top,
    targetPos: down ? Position.Top : Position.Bottom,
  }
}
