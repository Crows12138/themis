import type { QueryResult } from '../types'
import { Verdict } from './Verdict'
import { GapReport } from './GapReport'

export interface ResultPayload {
  asked: string
  result: QueryResult
  reply?: string
}

export function ResultView({ payload, onReset, resetLabel = '← 再问一个' }: { payload: ResultPayload; onReset: () => void; resetLabel?: string }) {
  const { asked, result, reply } = payload
  return (
    <div className="result">
      {asked ? (
        <p className="askedline">
          <b>问:</b> {asked}
        </p>
      ) : null}
      <Verdict result={result} />
      {reply ? (
        <section className="reply">
          <div className="reply__head">
            <h3>回答</h3>
            <span className="reply__rule" />
          </div>
          <p className="reply__body">{reply}</p>
        </section>
      ) : null}
      {result.data_gap_report ? <GapReport report={result.data_gap_report} /> : null}
      <div className="ask__meta" style={{ marginTop: 'var(--space-2xl)' }}>
        <button className="linklike" onClick={onReset}>
          {resetLabel}
        </button>
      </div>
    </div>
  )
}
