import { useState } from 'react'
import { absent, fill, say, type Words, useLang } from '../lib/language'
import type { QueryResult } from '../types'
import { auditResult, errorText, type AuditRow } from '../api'

const SAYS = {
  region: { zh: '独立复核', en: 'Independent recheck' },
  running: { zh: '复核中…', en: 'Rechecking…' },
  again: { zh: '再复核一次', en: 'Recheck again' },
  start: { zh: '独立复核这个答案', en: 'Recheck this answer independently' },
  someFailed: {
    zh: '{n} 项复核没通过 —— 内核照这张图重推，得到的和上面这份对不上。',
    en: '{n} checks did not pass — the kernel re-derived from this graph and did not arrive at what is above.',
  },
  allPassed: {
    zh: '{n} 项独立复核全部通过 —— 内核不看上面的结论，照这张图各自重算了一遍。',
    en: 'All {n} checks passed — the kernel ignored the conclusion above and re-derived each one from this graph.',
  },
} satisfies Record<string, Words>

/**
 * 独立复核 — send the graph and this result back to the kernel, which
 * re-derives the answer without looking at what was claimed.
 *
 * There is no routing here on purpose. Which checks apply to a result is a
 * question about the result, and this surface is the one place least able to
 * answer it: the kernel ships many audits, several of them about a different
 * artifact entirely. The first version of this component picked between two
 * endpoints by hand and so could only ever have offered two.
 */
export function Recheck({ result, program }: { result: QueryResult; program: Record<string, unknown> }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle')
  const [rows, setRows] = useState<AuditRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const lang = useLang()

  async function run() {
    setState('busy')
    setError(null)
    try {
      const { audits } = await auditResult(program, result)
      setRows(audits)
      setState('done')
    } catch (e) {
      setState('idle')
      setError(errorText(e, lang))
    }
  }

  const failed = rows.filter((row) => !row.ok)

  return (
    <section className="recheck" aria-label={fill(SAYS.region, lang)}>
      <button className="btn btn--ghost" onClick={run} disabled={state === 'busy'}>
        {state === 'busy'
          ? fill(SAYS.running, lang)
          : state === 'done'
            ? fill(SAYS.again, lang)
            : fill(SAYS.start, lang)}
      </button>

      {state === 'done' ? (
        <>
          <p className={failed.length ? 'recheck__no' : 'recheck__ok'}>
            {failed.length
              ? fill(SAYS.someFailed, lang, { n: failed.length })
              : fill(SAYS.allPassed, lang, { n: rows.length })}
          </p>
          <ul className="recheck__list">
            {rows.map((row) => (
              <li className="recheck__row" key={row.audit}>
                <span className={row.ok ? 'recheck__mark recheck__mark--ok' : 'recheck__mark recheck__mark--no'}>
                  {row.ok ? '✓' : '✗'}
                </span>
                <span className="recheck__what">{say(row.words, lang, absent('no_word_for_this_token', lang, { token: row.audit }))}</span>
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
