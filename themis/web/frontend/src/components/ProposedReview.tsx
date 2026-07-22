import type { LlmProposedReview } from '../types'
import { Foldout } from './Foldout'

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
  const edges = review.edges ?? []
  const probs = review.probabilities ?? []
  if (!edges.length && !probs.length) return null

  const parts: string[] = []
  if (probs.length) parts.push(`${probs.length} 个估的数值`)
  if (edges.length) parts.push(`${edges.length} 条 AI 提议的边`)

  return (
    <section className="proposed" role="note" aria-label="AI 提议的假设">
      <div className="proposed__head">
        <span className="proposed__badge">AI 估算</span>
        <p className="proposed__title">这个答案里有 AI 假设的部分 —— 请审核后再用</p>
      </div>

      <Foldout summary={`看是哪些 · ${parts.join(' · ')}`} tone="warn">
        <p className="proposed__intro">
          Themis 的数学是精确的,但下面这些不是数据,是 AI 按常识估的。答案成立与否,取决于它们合不合理。
        </p>

        {probs.length ? (
          <div className="proposed__group">
            <span className="proposed__grouphd">估的数值 · {probs.length} 项</span>
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
            <span className="proposed__grouphd">AI 提议的因果边 · {edges.length} 条</span>
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
