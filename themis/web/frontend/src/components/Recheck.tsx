import { useState } from 'react'
import { DEFAULT_LANG, say } from '../lib/language'
import type { QueryResult } from '../types'
import { auditResult, type AuditRow } from '../api'

/**
 * 独立复核 — send the graph and this result back to the kernel, which
 * re-derives the answer without looking at what was claimed.
 *
 * There is no routing here on purpose. Which checks apply to a result is a
 * question about the result, and this surface is the one place least able to
 * answer it: the kernel ships thirteen audits, five of them about a different
 * artifact entirely. The first version of this component picked between two
 * endpoints by hand and so could only ever have offered two.
 */
export function Recheck({ result, program }: { result: QueryResult; program: Record<string, unknown> }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle')
  const [rows, setRows] = useState<AuditRow[]>([])
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setState('busy')
    setError(null)
    try {
      const { audits } = await auditResult(program, result)
      setRows(audits)
      setState('done')
    } catch (e) {
      setState('idle')
      setError((e as Error).message)
    }
  }

  const failed = rows.filter((row) => !row.ok)

  return (
    <section className="recheck" aria-label="独立复核">
      <button className="btn btn--ghost" onClick={run} disabled={state === 'busy'}>
        {state === 'busy' ? '复核中…' : state === 'done' ? '再复核一次' : '独立复核这个答案'}
      </button>

      {state === 'done' ? (
        <>
          <p className={failed.length ? 'recheck__no' : 'recheck__ok'}>
            {failed.length
              ? `${failed.length} 项复核没通过 —— 内核照这张图重推，得到的和上面这份对不上。`
              : `${rows.length} 项独立复核全部通过 —— 内核不看上面的结论，照这张图各自重算了一遍。`}
          </p>
          <ul className="recheck__list">
            {rows.map((row) => (
              <li className="recheck__row" key={row.audit}>
                <span className={row.ok ? 'recheck__mark recheck__mark--ok' : 'recheck__mark recheck__mark--no'}>
                  {row.ok ? '✓' : '✗'}
                </span>
                <span className="recheck__what">{say(row.words, DEFAULT_LANG, row.audit)}</span>
                {row.refusal ? <span className="recheck__why mono">{row.refusal}</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {error ? <p className="recheck__no">{error}</p> : null}
    </section>
  )
}
