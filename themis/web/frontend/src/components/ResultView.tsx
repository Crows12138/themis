import { useEffect, useMemo, useState } from 'react'
import type { QueryResult } from '../types'
import { assume, clarify, errorText, getApiKey, questionOf, render, runProgram, supply, type ClarifyPick, type MergedEnvelope, type SupplyAnswer } from '../api'
import { fill, useLang, type Words } from '../lib/language'
import { named, nameOf, namesOf, showNames } from '../lib/names'
import { useOffers } from '../lib/offers'
import { saveResult, whenSaved } from '../lib/saved'
import { framingVariables, framingDefaultsInProgram, framingFieldLabel } from '../lib/verdict'
import type { LlmProposedReview } from '../types'
import { Verdict } from './Verdict'
import { GapReport } from './GapReport'
import { ResultGraph } from './ResultGraph'
import { FramingFill } from './FramingFill'
import { ProposedReview } from './ProposedReview'
import { SupplyNumbers } from './SupplyNumbers'
import { Foldout } from './Foldout'
import { JsonEditor } from './JsonEditor'
import { Recheck } from './Recheck'
import { Correction, type Revision } from './Correction'

export interface ResultPayload {
  asked: string
  result: QueryResult
  reply?: string
  program?: Record<string, unknown>
  naive?: number | null
  // The correction this result came from, and the program before and after
  // it. Both ends are kept because the graph can be edited afterwards, and
  // what the correction changed is a fact about these two.
  revision?: Revision
  // When this result was saved, if it was opened from a file rather than
  // made on this page (lib/saved.ts).
  savedAt?: string
}

export type Workspace = 'ask' | 'build' | 'estimate'

const SAYS = {
  askAnother: { zh: '← 再问一个', en: '← Ask another' },
  noResult: { zh: '这个程序没有返回结果。', en: 'That program came back with nothing.' },
  asked: { zh: '问：', en: 'Asked:' },
  // What the kernel was asked, under what the reader said. The two differ
  // whenever a model read the sentence, and the reader is the only one who
  // can say whether the reading is theirs.
  readAs: { zh: '理解为：', en: 'Read as:' },
  defaultedRegion: { zh: '操作化采用默认', en: 'Operationalisation left at its defaults' },
  defaultedTitle: { zh: '⚠ 这个答案用的是默认操作化，你没确认过', en: '⚠ This answer used default operationalisations that you never confirmed' },
  // The list separator is part of the sentence, not part of the data: the two
  // languages do not punctuate a list the same way.
  listSep: { zh: '、', en: ', ' },
  defaultedVar: { zh: ' 的 {fields} 用的是标准操作化；', en: ": its {fields} were left at the standard operationalisation; " },
  // What "the standard one" comes to is a question about each field, and this
  // sentence used to answer it by naming the four values the server wrote in
  // ("标准测量、研究随访期…"). Those values are gone — a blank field is now
  // recorded as answered rather than filled — so what is left to say is the
  // thing that was always the point: nobody named these.
  defaultedMeans: {
    zh: '也就是说，这几项的口径不是你定的，是按标准做法当成默认。',
    en: 'Which is to say nobody named what those come to; the conclusion takes the standard reading of each.',
  },
  defaultedWarn: { zh: '如果你心里的口径不同，这个答案未必适用。', en: 'If you had something else in mind, this answer may not apply to it.' },
  defaultedHow: {
    zh: '想换成你自己的定义：在下方「查看 / 编辑因果图 JSON」里改这些字段后重跑，或重新提问时把口径说清楚。',
    en: 'To use your own definitions: edit those fields in the graph JSON below and re-run, or state them when you ask again.',
  },
  assumeRegion: { zh: '用 AI 估算', en: 'Estimate with AI priors' },
  assumeTitle: { zh: '数据不够，算不出确切数字？', en: 'Not enough data for an exact number?' },
  assumeSub: {
    zh: '让 AI 按常识给缺的概率填一组先验，先得到一个点估计——每个假设都会列出来标明「这是估的」，你可以逐条审核或替换。',
    en: 'Let the AI supply common-sense priors for the missing probabilities and get a point estimate — every one is listed and marked as a guess, so you can review or replace them one by one.',
  },
  assuming: { zh: '估算中…', en: 'Estimating…' },
  assumeGo: { zh: '用 AI 常识估一个 →', en: 'Estimate with AI priors →' },
  answer: { zh: '回答', en: 'Answer' },
  rendering: { zh: '解读中…', en: 'Putting it in words…' },
  renderGo: { zh: '用大白话解读这份判决', en: 'Read this verdict back in plain language' },
  handoff: { zh: '把这张图带去 →', en: 'Take this graph to →' },
  toEstimate: { zh: '上传数据做数值估计', en: 'Upload data and estimate' },
  toBuild: { zh: '在画布上重画 / 改结构', en: 'Redraw it / change the structure' },
  rawEnvelope: { zh: '查看这份结果的原始信封（JSON）', en: 'See the raw envelope for this result (JSON)' },
  save: { zh: '保存这个结果（下载文件）', en: 'Save this result (download a file)' },
  graphEdited: {
    zh: '因果图已改动，下面还是改动前的结果。点图上方的「用改后的图重跑」更新，或点「还原原图」撤销改动。',
    en: 'The graph has been edited, and what is below is still the result for the graph as it was. Re-run with the edited graph to update it, or restore the original to undo the edit.',
  },
  savedAt: {
    zh: '这是 {when} 保存的结果，从文件打开，没有重新计算。',
    en: 'Saved on {when} and opened from a file; nothing here was computed again.',
  },
} satisfies Record<string, Words>

export function ResultView({
  workspace,
  payload,
  onReset,
  resetLabel,
  onSendTo,
  onRevise,
  onBack,
}: {
  // Where this view is shown, which a saved copy records so that opening it
  // puts it back there.
  workspace: Workspace
  payload: ResultPayload
  onReset: () => void
  resetLabel?: string
  onSendTo?: (target: Workspace, program: Record<string, unknown>) => void
  // Offered where the question was a sentence and a model is behind this
  // deployment: the reading can then be corrected in a sentence too.
  onRevise?: (said: string, program: Record<string, unknown>) => Promise<void>
  onBack?: () => void
}) {
  const lang = useLang()
  const offers = useOffers()
  const [result, setResult] = useState<QueryResult>(payload.result)
  const [program, setProgram] = useState<Record<string, unknown> | undefined>(payload.program)
  const [reply, setReply] = useState<string | undefined>(payload.reply)
  const [naive, setNaive] = useState<number | null | undefined>(payload.naive)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState<Words | null>(null)
  // Whether the graph on the canvas has moved on from the one this result
  // was computed from (ResultGraph says).
  const [graphEdited, setGraphEdited] = useState(false)

  // The names this program gives its variables are in force for everything
  // drawn below, from this render on (names.ts): said here rather than in an
  // effect, because the sentences below are filled while this renders.
  const names = useMemo(() => namesOf(program, lang), [program, lang])
  showNames(names, lang)
  useEffect(() => () => showNames(null), [])

  // The reading follows the result on the screen: a re-run with an edited
  // graph, a clarification or priors can each change which question is
  // answered, and a line left over from the last one would say otherwise.
  useEffect(() => {
    if (!program) { setQuestion(null); return }
    let current = true
    setQuestion(null)
    questionOf(program, result).then(
      ({ words }) => { if (current) setQuestion(words) },
      (e) => { if (current) setError(errorText(e, lang)) },
    )
    return () => { current = false }
  }, [program, result])

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
  // The data-scarcity case: a structurally-identifiable query whose needed
  // distributions have no data. The reader can type in numbers they have,
  // which needs no model, or have AI priors sourced (disclosed).
  const shortOfNumbers =
    program != null &&
    result.status === 'needs_investigation' &&
    gaps.some((g) => g.kind === 'missing_distribution')
  // Both this and the reply below are the two places in the product that
  // need a model outside the Ask workspace, which is why hiding that tab
  // is not the whole of turning a model off. What they offer is a step
  // this deployment can take; a deployment with no model cannot take it.
  const canAssume = offers?.llm === true && shortOfNumbers

  // Each way of filling a gap comes back as the merged program run again,
  // and the page moves on to it the same way.
  async function merge(fetch: (program: Record<string, unknown>) => Promise<MergedEnvelope>) {
    if (!program) return
    setBusy(true)
    setError(null)
    try {
      const env = await fetch(program)
      const r = env.results?.[0]
      if (r) {
        setResult(r)
        setProgram((env.merged_program as Record<string, unknown>) ?? program)
        setReply(undefined)
        setNaive(undefined)
      }
    } catch (e) {
      setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  const doAssume = () => merge((p) => assume(p, lang, getApiKey()))
  const doClarify = (picks: ClarifyPick[]) => merge((p) => clarify(p, picks))
  const doSupply = (answers: SupplyAnswer[], source: string) => merge((p) => supply(p, answers, source))

  const [rendering, setRendering] = useState(false)
  async function doRender() {
    if (!program || rendering) return
    setRendering(true)
    setError(null)
    try {
      const { reply: txt } = await render(program, result, payload.asked, lang,
        getApiKey())
      setReply(txt)
    } catch (e) {
      setError(errorText(e, lang))
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
      } else setError(fill(SAYS.noResult, lang))
    } catch (e) {
      setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="result">
      {/* Only while the saved result is the one on the screen: a re-run
          from it is today's, and the line would then say otherwise. */}
      {payload.savedAt && result === payload.result ? (
        <p className="savedline">{fill(SAYS.savedAt, lang, { when: whenSaved(payload.savedAt) })}</p>
      ) : null}
      {payload.asked ? (
        <p className="askedline">
          <b>{fill(SAYS.asked, lang)}</b> {payload.asked}
        </p>
      ) : null}
      {question ? (
        <p className="askedline">
          <b>{fill(SAYS.readAs, lang)}</b> {named(fill(question, lang))}
        </p>
      ) : null}
      {program && (onRevise || payload.revision) ? (
        <Correction revision={payload.revision} program={program} onRevise={onRevise} onBack={onBack} />
      ) : null}

      {program ? <ResultGraph program={program} original={payload.program ?? program} busy={busy} onRerun={doRunJson} onEdited={setGraphEdited} /> : null}

      {/* Between an edit to the graph and its re-run, everything below is
          about the graph as it was. It is said, dimmed, and not operable:
          each action down there runs the program the result came from and
          would replace the edited graph with it. */}
      {graphEdited ? (
        <p className="staleline" role="status">{fill(SAYS.graphEdited, lang)}</p>
      ) : null}
      <div className={graphEdited ? 'result__rest result__rest--stale' : 'result__rest'} inert={graphEdited}>
      <Verdict result={result} naive={naive} />

      {review ? <ProposedReview review={review} models={result.extensions?.probability_models?.models} /> : null}

      {defaultedVars.length > 0 ? (
        <section className="assume" role="note" aria-label={fill(SAYS.defaultedRegion, lang)}>
          <Foldout tone="warn" summary={<span className="assume__title">{fill(SAYS.defaultedTitle, lang)}</span>}>
            <p className="assume__body">
              {defaultedVars.map((d) => (
                <span key={d.predicate} className="assume__var">
                  <b className="mono">{nameOf(d.predicate)}</b>
                  {fill(SAYS.defaultedVar, lang, {
                    fields: d.fields
                      .map((f) => framingFieldLabel(f, lang))
                      .join(fill(SAYS.listSep, lang)),
                  })}
                </span>
              ))}
              {fill(SAYS.defaultedMeans, lang)}
              <b>{fill(SAYS.defaultedWarn, lang)}</b>
              {fill(SAYS.defaultedHow, lang)}
            </p>
          </Foldout>
        </section>
      ) : null}

      {/* Primary action when data-scarce: get a number via AI priors. */}
      {canAssume ? (
        <section className="assumecta" aria-label={fill(SAYS.assumeRegion, lang)}>
          <div className="assumecta__text">
            <p className="assumecta__title">{fill(SAYS.assumeTitle, lang)}</p>
            <p className="assumecta__sub">{fill(SAYS.assumeSub, lang)}</p>
          </div>
          <button className="btn assumecta__go" onClick={doAssume} disabled={busy}>
            {fill(busy ? SAYS.assuming : SAYS.assumeGo, lang)}
          </button>
        </section>
      ) : null}
      {program && shortOfNumbers ? <SupplyNumbers program={program} busy={busy} onSubmit={doSupply} /> : null}

      {reply ? (
        <section className="reply">
          <div className="reply__head">
            <h3>{fill(SAYS.answer, lang)}</h3>
            <span className="reply__rule" />
          </div>
          <p className="reply__body">{named(reply)}</p>
        </section>
      ) : program && offers?.llm ? (
        <div className="renderrow">
          <button className="btn btn--ghost" onClick={doRender} disabled={rendering}>
            {fill(rendering ? SAYS.rendering : SAYS.renderGo, lang)}
          </button>
        </div>
      ) : null}

      {result.data_gap_report ? <GapReport report={result.data_gap_report} /> : null}

      {/* Improve-the-answer actions, grouped near the bottom. */}
      {program && fvars.length > 0 ? <FramingFill vars={fvars} busy={busy} onSubmit={doClarify} /> : null}

      {program && onSendTo ? (
        <div className="handoff">
          <span className="handoff__cap">{fill(SAYS.handoff, lang)}</span>
          {!(result as unknown as Record<string, unknown>).numeric_estimate ? (
            <button className="btn btn--ghost" onClick={() => onSendTo('estimate', program)}>{fill(SAYS.toEstimate, lang)}</button>
          ) : null}
          <button className="btn btn--ghost" onClick={() => onSendTo('build', program)}>{fill(SAYS.toBuild, lang)}</button>
        </div>
      ) : null}

      {/* Check-it-yourself surface, folded at the very bottom: an independent
          re-derivation, the program that produced this, and the envelope as
          it came off the kernel. The envelope dump says none of its fields to
          a reader — what this surface still owes is listed in types.ts, and a
          JSON blob discharges nothing on that list. */}
      {program ? <Recheck result={result} program={program} /> : null}
      {program ? <JsonEditor program={program} busy={busy} onRun={doRunJson} /> : null}
      <Foldout summary={fill(SAYS.rawEnvelope, lang)}>
        <pre className="rawenv mono">{JSON.stringify(result, null, 2)}</pre>
      </Foldout>
      </div>

      {error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : null}

      <div className="ask__meta" style={{ marginTop: 'var(--space-xl)' }}>
        <button className="linklike" onClick={onReset}>{resetLabel ?? fill(SAYS.askAnother, lang)}</button>
        {/* What is on the screen now, re-runs and all, not what first arrived. */}
        <button
          className="linklike"
          onClick={() => saveResult(workspace, { asked: payload.asked, result, program, reply, naive, revision: payload.revision })}
        >
          {fill(SAYS.save, lang)}
        </button>
      </div>
    </div>
  )
}
