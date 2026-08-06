import { useState } from 'react'
import type { QueryResult } from '../types'
import { verify, verifyBounds } from '../api'

/**
 * 独立复核 — send the graph and this result back to the kernel, which
 * re-derives the answer without looking at what was claimed.
 *
 * Which of the two endpoints replays this result is settled by what the
 * result carries, not by what the caller hopes: a chain is replayed step by
 * step, a bound is re-derived from the graph. A result carrying neither gets
 * no button at all, because an offer that can only come back refused is
 * worse than no offer — that is what the surface this replaced did, and it
 * spelled the refusal `VerificationError`.
 */
function routeFor(result: QueryResult): ((program: Record<string, unknown>, r: QueryResult) => Promise<{ ok: boolean }>) | null {
  if ((result.derivation?.steps ?? []).length > 0) return verify
  if (result.bounds_result) return verifyBounds
  return null
}

export function Recheck({ result, program }: { result: QueryResult; program: Record<string, unknown> }) {
  const [state, setState] = useState<'idle' | 'busy' | 'ok'>('idle')
  const [refused, setRefused] = useState<string | null>(null)
  const route = routeFor(result)
  if (!route) return null

  async function run() {
    if (!route) return
    setState('busy')
    setRefused(null)
    try {
      await route(program, result)
      setState('ok')
    } catch (e) {
      setState('idle')
      setRefused((e as Error).message)
    }
  }

  return (
    <section className="recheck" aria-label="独立复核">
      <button className="btn btn--ghost" onClick={run} disabled={state === 'busy'}>
        {state === 'busy' ? '复核中…' : '独立复核这个答案'}
      </button>
      {state === 'ok' ? (
        <p className="recheck__ok">✓ 复核通过 —— 内核不看上面的结论，照这张图重新推了一遍，推出来的是同一个答案。</p>
      ) : null}
      {refused ? (
        <p className="recheck__no">
          <b>复核没通过。</b>重推的结果和上面这份对不上,内核给出的理由是:
          <span className="recheck__why mono">{refused}</span>
        </p>
      ) : null}
    </section>
  )
}
