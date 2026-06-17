import { useEffect, useState } from 'react'
import type { QueryResult } from '../types'
import { clarify, getApiKey, render, runProgram, type ClarifyPick } from '../api'
import { framingVariables, framingDefaultsInProgram } from '../lib/verdict'
import { Verdict } from './Verdict'
import { GapReport } from './GapReport'
import { ResultGraph } from './ResultGraph'
import { FramingFill } from './FramingFill'
import { JsonEditor } from './JsonEditor'

export interface ResultPayload {
  asked: string
  result: QueryResult
  reply?: string
  program?: Record<string, unknown>
  naive?: number | null
}

export function ResultView({ payload, onReset, resetLabel = '← 再问一个' }: { payload: ResultPayload; onReset: () => void; resetLabel?: string }) {
  const [result, setResult] = useState<QueryResult>(payload.result)
  const [program, setProgram] = useState<Record<string, unknown> | undefined>(payload.program)
  const [reply, setReply] = useState<string | undefined>(payload.reply)
  const [naive, setNaive] = useState<number | null | undefined>(payload.naive)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setResult(payload.result)
    setProgram(payload.program)
    setReply(payload.reply)
    setNaive(payload.naive)
    setError(null)
  }, [payload])

  const gaps = result.data_gap_report?.gaps ?? []
  const fvars = program ? framingVariables(gaps) : []
  const defaultedVars = program ? framingDefaultsInProgram(program) : []

  async function doClarify(picks: ClarifyPick[]) {
    if (!program) return
    setBusy(true)
    setError(null)
    try {
      const env = await clarify(program, picks)
      const r = env.results?.[0]
      if (r) {
        setResult(r)
        setProgram((env.merged_program as Record<string, unknown>) ?? program)
        setReply(undefined)
        setNaive(undefined)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const [rendering, setRendering] = useState(false)
  async function doRender() {
    if (!program || rendering) return
    setRendering(true)
    setError(null)
    try {
      const { reply: txt } = await render(program, payload.asked, getApiKey())
      setReply(txt)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRendering(false)
    }
  }

  async function doRunJson(prog: Record<string, unknown>) {
    setBusy(true)
    setError(null)
    try {
      const env = await runProgram(prog)
      const r = env.results?.[0]
      if (r) {
        setResult(r)
        setProgram(prog)
        setReply(undefined)
        setNaive(undefined)
      } else setError('这个程序没有返回结果。')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="result">
      {payload.asked ? (
        <p className="askedline">
          <b>问:</b> {payload.asked}
        </p>
      ) : null}

      {program ? <ResultGraph program={program} original={payload.program ?? program} busy={busy} onRerun={doRunJson} /> : null}

      <Verdict result={result} naive={naive} />

      {defaultedVars.length > 0 ? (
        <section className="assume" role="note" aria-label="操作化采用默认">
          <p className="assume__title">⚠ 这个答案用的是默认操作化，你没确认过</p>
          <p className="assume__body">
            {defaultedVars.map((d) => (
              <span key={d.predicate} className="assume__var">
                <b className="mono">{d.predicate}</b> 的 {d.fields.join('、')} 是系统按默认补的；
              </span>
            ))}
            也就是说，结论假设了「标准测量、研究随访期、任意可测变化、当前状态为基线」这套定义。<b>如果你心里的口径不同，这个答案未必适用。</b>
            想换成你自己的定义：在下方「查看 / 编辑因果图 JSON」里改这些字段后重跑，或重新提问时把口径说清楚。
          </p>
        </section>
      ) : null}

      {reply ? (
        <section className="reply">
          <div className="reply__head">
            <h3>回答</h3>
            <span className="reply__rule" />
          </div>
          <p className="reply__body">{reply}</p>
        </section>
      ) : program ? (
        <div className="renderrow">
          <button className="btn btn--ghost" onClick={doRender} disabled={rendering}>
            {rendering ? '解读中…' : '用大白话解读这份判决'}
          </button>
        </div>
      ) : null}

      {program && fvars.length > 0 ? <FramingFill vars={fvars} busy={busy} onSubmit={doClarify} /> : null}

      {result.data_gap_report ? <GapReport report={result.data_gap_report} /> : null}

      {program ? <JsonEditor program={program} busy={busy} onRun={doRunJson} /> : null}

      {error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : null}

      <div className="ask__meta" style={{ marginTop: 'var(--space-2xl)' }}>
        <button className="linklike" onClick={onReset}>{resetLabel}</button>
      </div>
    </div>
  )
}
