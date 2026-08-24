import { useState, type CSSProperties } from 'react'
import { fill, useLang, type Words } from '../lib/language'

const SAYS = {
  open: { zh: '展开', en: 'Show all' },
  shut: { zh: '收起', en: 'Show less' },
} satisfies Record<string, Words>

/** Long kernel gap text is shown clamped with a quiet expand toggle —
 * progressive disclosure so a wall of boilerplate doesn't bury the
 * verdict. Short text passes through untouched. */
export function Clamp({ text, lines = 3, threshold = 150 }: { text: string; lines?: number; threshold?: number }) {
  const [open, setOpen] = useState(false)
  const lang = useLang()
  if (!text || text.length <= threshold) return <span>{text}</span>
  return (
    <span className="clamp">
      <span className={open ? undefined : 'clamp__text'} style={open ? undefined : ({ ['--lines']: lines } as CSSProperties)}>
        {text}
      </span>{' '}
      <button className="clamp__toggle" onClick={() => setOpen((o) => !o)}>
        {fill(open ? SAYS.shut : SAYS.open, lang)}
      </button>
    </span>
  )
}
