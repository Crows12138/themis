import { useEffect, useState } from 'react'
import type { QueryResult } from '../types'
import { clarify, getApiKey, render, runProgram, type ClarifyPick } from '../api'
import { framingVariables } from '../lib/verdict'
import { Verdict } from './Verdict'
import { GapReport } from './GapReport'
import { DagView } from './DagView'
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

      {program ? <DagView program={program} /> : null}

      <Verdict result={result} naive={naive} />

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
