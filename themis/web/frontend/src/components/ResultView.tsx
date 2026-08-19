import { useEffect, useState } from 'react'
import type { QueryResult } from '../types'
import { assume, clarify, getApiKey, render, runProgram, type ClarifyPick } from '../api'
import { framingVariables, framingDefaultsInProgram } from '../lib/verdict'
import type { LlmProposedReview } from '../types'
import { Verdict } from './Verdict'
import { GapReport } from './GapReport'
import { ResultGraph } from './ResultGraph'
import { FramingFill } from './FramingFill'
import { ProposedReview } from './ProposedReview'
import { Foldout } from './Foldout'
import { JsonEditor } from './JsonEditor'
import { Recheck } from './Recheck'

export interface ResultPayload {
  asked: string
  result: QueryResult
  reply?: string
  program?: Record<string, unknown>
  naive?: number | null
}

type Workspace = 'ask' | 'build' | 'estimate'

export function ResultView({
  payload,
  onReset,
  resetLabel = '← 再问一个',
  onSendTo,
}: {
  payload: ResultPayload
  onReset: () => void
  resetLabel?: string
  onSendTo?: (target: Workspace, program: Record<string, unknown>) => void
}) {
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
  const review = (result.extensions?.llm_proposed_review as LlmProposedReview | undefined) ?? undefined
  // The data-scarcity escape hatch: a structurally-identifiable query whose
  // needed distributions have no data. Offer to source AI priors (disclosed).
  const canAssume =
    program != null &&
    result.status === 'needs_investigation' &&
    gaps.some((g) => g.kind === 'missing_distribution')

  async function doAssume() {
    if (!program) return
    setBusy(true)
    setError(null)
    try {
      const env = await assume(program, getApiKey())
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

      {review ? <ProposedReview review={review} /> : null}

      {defaultedVars.length > 0 ? (
        <section className="assume" role="note" aria-label="操作化采用默认">
          <Foldout tone="warn" summary={<span className="assume__title">⚠ 这个答案用的是默认操作化，你没确认过</span>}>
            <p className="assume__body">
              {defaultedVars.map((d) => (
                <span key={d.predicate} className="assume__var">
                  <b className="mono">{d.predicate}</b> 的 {d.fields.join('、')} 是系统按默认补的；
                </span>
              ))}
              也就是说，结论假设了「标准测量、研究随访期、任意可测变化、当前状态为基线」这套定义。<b>如果你心里的口径不同，这个答案未必适用。</b>
              想换成你自己的定义：在下方「查看 / 编辑因果图 JSON」里改这些字段后重跑，或重新提问时把口径说清楚。
            </p>
          </Foldout>
        </section>
      ) : null}

      {/* Primary action when data-scarce: get a number via AI priors. */}
      {canAssume ? (
        <section className="assumecta" aria-label="用 AI 估算">
          <div className="assumecta__text">
            <p className="assumecta__title">数据不够，算不出确切数字?</p>
            <p className="assumecta__sub">
              让 AI 按常识给缺的概率填一组先验，先得到一个点估计——每个假设都会列出来标明「这是估的」，你可以逐条审核或替换。
            </p>
          </div>
          <button className="btn assumecta__go" onClick={doAssume} disabled={busy}>
            {busy ? '估算中…' : '用 AI 常识估一个 →'}
          </button>
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

      {result.data_gap_report ? <GapReport report={result.data_gap_report} /> : null}

      {/* Improve-the-answer actions, grouped near the bottom. */}
      {program && fvars.length > 0 ? <FramingFill vars={fvars} busy={busy} onSubmit={doClarify} /> : null}

      {program && onSendTo ? (
        <div className="handoff">
          <span className="handoff__cap">把这张图带去 →</span>
          {!(result as unknown as Record<string, unknown>).numeric_estimate ? (
            <button className="btn btn--ghost" onClick={() => onSendTo('estimate', program)}>上传数据做数值估计</button>
          ) : null}
          <button className="btn btn--ghost" onClick={() => onSendTo('build', program)}>在画布上重画 / 改结构</button>
        </div>
      ) : null}

      {/* Check-it-yourself surface, folded at the very bottom: an independent
          re-derivation, the program that produced this, and the envelope as
          it came off the kernel. The envelope dump says none of its fields to
          a reader — what this surface still owes is listed in types.ts, and a
          JSON blob discharges nothing on that list. */}
      {program ? <Recheck result={result} program={program} /> : null}
      {program ? <JsonEditor program={program} busy={busy} onRun={doRunJson} /> : null}
      <Foldout summary="查看这份结果的原始信封（JSON）">
        <pre className="rawenv mono">{JSON.stringify(result, null, 2)}</pre>
      </Foldout>

      {error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : null}

      <div className="ask__meta" style={{ marginTop: 'var(--space-xl)' }}>
        <button className="linklike" onClick={onReset}>{resetLabel}</button>
      </div>
    </div>
  )
}
