import type { ReactNode } from 'react'

/**
 * Progressive-disclosure primitive: a native <details>/<summary> foldout.
 * Keeps a one-line summary always visible; the body is collapsed by default
 * so machine-artifact detail (formulas, gap technicals, audit trails) stays
 * out of the way until asked for — without deleting any information.
 *
 * ``tone="warn"`` tints it as a caution (trust flags); default is neutral.
 */
export function Foldout({
  summary,
  children,
  defaultOpen = false,
  tone,
  count,
}: {
  summary: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  tone?: 'warn'
  count?: number | string
}) {
  return (
    <details className={`foldout${tone ? ` foldout--${tone}` : ''}`} open={defaultOpen}>
      <summary className="foldout__summary">
        <span className="foldout__chev" aria-hidden>▸</span>
        <span className="foldout__label">{summary}</span>
        {count != null ? <span className="foldout__count">{count}</span> : null}
      </summary>
      <div className="foldout__body">{children}</div>
    </details>
  )
}
