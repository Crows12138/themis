import type { LlmProposedReview } from '../types'
import { fill, useLang, type Words } from '../lib/language'
import { Foldout } from './Foldout'

const SAYS = {
  region: { zh: 'AI 提议的假设', en: 'Assumptions the AI proposed' },
  badge: { zh: 'AI 估算', en: 'AI estimate' },
  title: { zh: '这个答案里有 AI 假设的部分 —— 请审核后再用', en: 'Part of this answer rests on AI assumptions — review them before you use it' },
  someNumbers: { zh: '{n} 个估的数值', en: '{n} estimated numbers' },
  someEdges: { zh: '{n} 条 AI 提议的边', en: '{n} AI-proposed edges' },
  seeWhich: { zh: '看是哪些 · {what}', en: 'See which · {what}' },
  intro: {
    zh: 'Themis 的数学是精确的，但下面这些不是数据，是 AI 按常识估的。答案成立与否，取决于它们合不合理。',
    en: "Themis's arithmetic is exact, but the values below are not data — the AI guessed them from common sense. Whether the answer holds depends on whether they are reasonable.",
  },
  numbersHead: { zh: '估的数值 · {n} 项', en: 'Estimated numbers · {n}' },
  edgesHead: { zh: 'AI 提议的因果边 · {n} 条', en: 'AI-proposed causal edges · {n}' },
} satisfies Record<string, Words>

/**
 * Disclosure panel for everything the LLM *proposed* rather than measured —
 * graph edges and θ priors. Present whenever the kernel attaches
 * ``extensions.llm_proposed_review``. This is the "坦白" surface: the answer's
 * math is exact, but it rests on these assumptions.
 *
 * The warning banner stays visible (a trust flag must not hide); the per-item
 * detail folds so it doesn't dominate the page.
 */
export function ProposedReview({ review }: { review: LlmProposedReview }) {
  const lang = useLang()
  const edges = review.edges ?? []
  const probs = review.probabilities ?? []
  if (!edges.length && !probs.length) return null

  const parts: string[] = []
  if (probs.length) parts.push(fill(SAYS.someNumbers, lang, { n: probs.length }))
  if (edges.length) parts.push(fill(SAYS.someEdges, lang, { n: edges.length }))

  return (
    <section className="proposed" role="note" aria-label={fill(SAYS.region, lang)}>
      <div className="proposed__head">
        <span className="proposed__badge">{fill(SAYS.badge, lang)}</span>
        <p className="proposed__title">{fill(SAYS.title, lang)}</p>
      </div>

      <Foldout summary={fill(SAYS.seeWhich, lang, { what: parts.join(' · ') })} tone="warn">
        <p className="proposed__intro">{fill(SAYS.intro, lang)}</p>

        {probs.length ? (
          <div className="proposed__group">
            <span className="proposed__grouphd">{fill(SAYS.numbersHead, lang, { n: probs.length })}</span>
            <div className="proposed__table">
              {probs.map((p, i) => (
                <div className="proposed__row" key={i}>
                  <span className="proposed__key mono">{p.key}</span>
                  <span className="proposed__val mono">{p.value}</span>
                  <span className="proposed__reason">{p.reason}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {edges.length ? (
          <div className="proposed__group">
            <span className="proposed__grouphd">{fill(SAYS.edgesHead, lang, { n: edges.length })}</span>
            <div className="proposed__edges">
              {edges.map((e, i) => (
                <span className="proposed__edge mono" key={i}>
                  {e.from} → {e.to}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </Foldout>
    </section>
  )
}
