import { useState, type CSSProperties } from 'react'

/** Long kernel gap text is shown clamped with a quiet expand toggle —
 * progressive disclosure so a wall of boilerplate doesn't bury the
 * verdict. Short text passes through untouched. */
export function Clamp({ text, lines = 3, threshold = 150 }: { text: string; lines?: number; threshold?: number }) {
  const [open, setOpen] = useState(false)
  if (!text || text.length <= threshold) return <span>{text}</span>
  return (
    <span className="clamp">
      <span className={open ? undefined : 'clamp__text'} style={open ? undefined : ({ ['--lines']: lines } as CSSProperties)}>
        {text}
      </span>{' '}
      <button className="clamp__toggle" onClick={() => setOpen((o) => !o)}>
        {open ? '收起' : '展开'}
      </button>
    </span>
  )
}
