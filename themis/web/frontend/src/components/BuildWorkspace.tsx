import { useState } from 'react'
import { errorText, runProgram } from '../api'
import { fill, useLang, type Words } from '../lib/language'
import { DagBuilder } from './DagBuilder'
import { ResultView, type ResultPayload } from './ResultView'

const SAYS = {
  asked: { zh: '因果图 · {kind} 查询', en: 'Causal graph · {kind} query' },
  back: { zh: '← 回到画布', en: '← Back to the canvas' },
  submit: { zh: '交给内核 →', en: 'Hand it to the kernel →' },
  title: { zh: '画出你的因果图', en: 'Draw your causal graph' },
  // Two emphasised phrases, so five parts. Each language decides for itself
  // what sits between them; a `<b>` inside one string would decide it once.
  ledeHead: {
    zh: '加变量、拉线连成因果关系，选一个干预和结果，交给内核判断——能不能识别、还缺什么。',
    en: 'Add variables, draw the arrows that mean "causes", pick one intervention and one outcome, and hand it to the kernel: can this be identified, and what is missing. ',
  },
  solidLead: { zh: '实线带箭头', en: 'A solid arrow' },
  solidTail: { zh: '是因果，', en: ' is a causal edge; ' },
  dashedLead: { zh: '虚线双箭头', en: 'a dashed double-headed arrow' },
  dashedTail: { zh: '是潜在共因（未观测混杂）。', en: ' is a latent common cause (unmeasured confounding).' },
} satisfies Record<string, Words>

export function BuildWorkspace({
  initialProgram,
  onSendTo,
}: {
  initialProgram?: Record<string, unknown>
  onSendTo?: (target: 'ask' | 'build' | 'estimate', program: Record<string, unknown>) => void
} = {}) {
  const [busy, setBusy] = useState(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const lang = useLang()

  async function run(program: Record<string, unknown>) {
    setBusy(true)
    setError(null)
    try {
      const env = await runProgram(program)
      const r = env.results?.[0]
      const q = (program.statements as { query?: { kind?: string } }[] | undefined)?.find((s) => s.query)?.query
      if (r) setPayload({ asked: fill(SAYS.asked, lang, { kind: q?.kind ?? 'effect' }), result: r, program })
    } catch (e) {
      setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  if (payload) return <ResultView payload={payload} onSendTo={onSendTo} onReset={() => setPayload(null)} resetLabel={fill(SAYS.back, lang)} />

  return (
    <DagBuilder
      submitLabel={fill(SAYS.submit, lang)}
      onSubmit={run}
      busy={busy}
      initialProgram={initialProgram}
      intro={
        <div className="build__intro">
          <h2 className="build__title">{fill(SAYS.title, lang)}</h2>
          <p className="build__lede">
            {fill(SAYS.ledeHead, lang)}
            <b>{fill(SAYS.solidLead, lang)}</b>
            {fill(SAYS.solidTail, lang)}
            <b>{fill(SAYS.dashedLead, lang)}</b>
            {fill(SAYS.dashedTail, lang)}
          </p>
        </div>
      }
      banner={error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : undefined}
    />
  )
}
