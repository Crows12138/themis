import { useState } from 'react'
import { errorText, type KernelError } from '../api'
import { BETWEEN_ITEMS, BETWEEN_STATEMENTS } from '../lib/kernelWords.generated'
import { fill, useLang, type Lang, type Words } from '../lib/language'
import { changeBetween } from '../lib/reading'

const SAYS = {
  region: { zh: '纠正读法', en: 'Correct the reading' },
  lead: {
    zh: '不是你的意思？用一句话说哪里不对。只改你说的地方，改完内核会重新核验。',
    en: 'Not what you meant? Say in one sentence what is off. Only that is changed, and the kernel checks the result again.',
  },
  placeholder: {
    zh: '比如：别加遗传这个因素 / 我只想知道会不会',
    en: 'e.g. leave genetics out / I only want to know whether it does',
  },
  go: { zh: '按这句改 →', en: 'Revise →' },
  going: { zh: '正在按你的话改…', en: 'Revising as you said…' },
  said: { zh: '你的纠正：', en: 'Your correction:' },
  changed: { zh: '这次改了：', en: 'What changed:' },
  addedVariables: { zh: '加了变量 {names}', en: 'added the variables {names}' },
  removedVariables: { zh: '去掉了变量 {names}', en: 'removed the variables {names}' },
  addedEdges: { zh: '加了边 {names}', en: 'added the edges {names}' },
  removedEdges: { zh: '去掉了边 {names}', en: 'removed the edges {names}' },
  questionChanged: { zh: '问题本身（见上面「理解为」）', en: 'the question itself (see "Read as" above)' },
  elsewhere: {
    zh: '图和问题都没有变，改动只在变量的说明或标注里',
    en: 'neither the graph nor the question; the change is in how variables are described or annotated',
  },
  unchanged: { zh: '什么都没有改，程序和之前一样', en: 'nothing; the program is the same as before' },
  back: { zh: '← 退回上一步', en: '← Back to the previous reading' },
  refused: { zh: '但内核算不出改后的图：', en: 'But the kernel could not compute the revised graph:' },
  onCanvas: {
    zh: '改后的图已经放到上面的画布上，下面还是改动前的结果。可以在图上继续改，再点「用改后的图重跑」；或点「还原原图」放弃这次修改。',
    en: 'The revised graph is on the canvas above, and the result below is still the one from before. Go on editing it there and press "Re-run with this graph", or "Restore the original" to drop this revision.',
  },
} satisfies Record<string, Words>

// One correction: what the reader said, and the program before and after it.
export interface Revision {
  said: string
  before: Record<string, unknown>
  after: Record<string, unknown>
}

// What a revision changed, as one sentence's clauses — or the one sentence
// for nothing, or for a change the graph and the question do not show.
function whatChanged(before: Record<string, unknown>, after: Record<string, unknown>, lang: Lang): string {
  const change = changeBetween(before, after)
  const items = fill(BETWEEN_ITEMS, lang)
  const clauses: string[] = []
  for (const key of ['addedVariables', 'removedVariables', 'addedEdges', 'removedEdges'] as const)
    if (change[key].length) clauses.push(fill(SAYS[key], lang, { names: change[key].join(items) }))
  if (change.questionChanged) clauses.push(fill(SAYS.questionChanged, lang))
  return clauses.length
    ? clauses.join(fill(BETWEEN_STATEMENTS, lang))
    : fill(change.unchanged ? SAYS.unchanged : SAYS.elsewhere, lang)
}

/**
 * 纠正读法: the reader says in one sentence where the reading departs from
 * what they meant, and a model revises the program — only there. What it
 * then changed is computed from the two programs and shown with the
 * correction, so a change nobody asked for is visible and one step undoes it.
 */
export function Correction({
  revision,
  program,
  onRevise,
  onRefused,
  onBack,
}: {
  revision?: Revision
  // The program on the screen now, which is what a further correction revises.
  program: Record<string, unknown>
  onRevise?: (said: string, program: Record<string, unknown>) => Promise<void>
  // A revision made as asked and then refused by the kernel: the program
  // the kernel would not run, for the canvas to show.
  onRefused?: (program: Record<string, unknown>) => void
  onBack?: () => void
}) {
  const lang = useLang()
  const [said, setSaid] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The revision the kernel refused, with why — shown as a revision is,
  // since it IS one: the reader's words landed, and the program they
  // landed on was refused. Without this, a refused revision was one red
  // line under the input, the old graph and the old result, and a reader
  // who had just pressed the button saw nothing happen.
  const [refused, setRefused] = useState<(Revision & { why: string }) | null>(null)

  async function submit() {
    const text = said.trim()
    if (!text || busy || !onRevise) return
    setBusy(true)
    setError(null)
    setRefused(null)
    try {
      await onRevise(text, program)
      setSaid('')
    } catch (e) {
      const after = (e as KernelError)?.program
      if (after) {
        setRefused({ said: text, before: program, after, why: errorText(e, lang) })
        onRefused?.(after)
        setSaid('')
      } else setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="correction" aria-label={fill(SAYS.region, lang)}>
      {revision ? (
        <div className="correction__last">
          <p><b>{fill(SAYS.said, lang)}</b> {revision.said}</p>
          <p><b>{fill(SAYS.changed, lang)}</b> {whatChanged(revision.before, revision.after, lang)}</p>
          {onBack ? <button className="linklike" onClick={onBack} disabled={busy}>{fill(SAYS.back, lang)}</button> : null}
        </div>
      ) : null}
      {refused ? (
        <div className="correction__last correction__refused" role="alert">
          <p><b>{fill(SAYS.said, lang)}</b> {refused.said}</p>
          <p><b>{fill(SAYS.changed, lang)}</b> {whatChanged(refused.before, refused.after, lang)}</p>
          <p><b>{fill(SAYS.refused, lang)}</b> {refused.why}</p>
          <p className="correction__hint">{fill(SAYS.onCanvas, lang)}</p>
        </div>
      ) : null}
      {onRevise ? (
        <>
          <p className="correction__lead">{fill(SAYS.lead, lang)}</p>
          <div className="correction__row">
            <input
              className="correction__input"
              value={said}
              placeholder={fill(SAYS.placeholder, lang)}
              onChange={(e) => setSaid(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit() } }}
              disabled={busy}
            />
            <button className="btn" onClick={submit} disabled={busy || !said.trim()}>
              {fill(busy ? SAYS.going : SAYS.go, lang)}
            </button>
          </div>
          {error ? <p className="correction__error" role="alert">{error}</p> : null}
        </>
      ) : null}
    </section>
  )
}
