import type { QueryResult } from '../types'
import { TIER_META, statusLabel, statusBlurb, fmtNum, structuralReadout, cleanPathNode, answerRows, routeRows } from '../lib/verdict'
import { fmtFormula } from '../lib/formula'
import { Foldout } from './Foldout'

const SEGS = [0, 1, 2]

export function Verdict({ result, naive }: { result: QueryResult; naive?: number | null }) {
  const report = result.data_gap_report
  const tier = report?.answer_tier
  const summary = report?.summary?.trim()
  const num = result.numeric_estimate
  // Structural-layer point value (plug-in identification once θ is supplied,
  // incl. via AI priors). Only shown when there's no data-backed estimate.
  const runNum = !num && result.numeric_result?.value != null ? result.numeric_result.value : null
  const bounds = result.bounds_result
  const struct = result.structural_result
  const sr = !tier && struct ? structuralReadout(result.query_kind, struct.value) : null
  const paths = struct?.supporting_paths?.filter((p) => p.length > 0) ?? []
  const formula = result.formula ? fmtFormula(result.formula) : null
  const sens = num?.sensitivity_analysis
  const ledger = result.extensions?.assumption_ledger
  const showCompare = num != null && num.point != null && naive != null
  const shaped = num ? answerRows(num) : null
  // How the estimand was identified. This foldout has been called
  // "怎么算出来的" all along while saying only the formula and the paths; the
  // ten blocks that answer that question are read here now.
  const routes = routeRows(result.extensions)
  // The "how it was computed" detail — machine artifacts a lay reader rarely
  // needs. Folded by default; nothing removed.
  const hasDetail = routes.length > 0 || paths.length > 0 || !!formula || !!bounds || sens?.e_value != null || !!ledger?.assumptions?.length

  return (
    <section className="verdict" aria-label="判决">
      <div className="verdict__head">
        {tier ? (
          <div className={`readout readout--${tier}`}>
            <span className="readout__cap">能给的最强答案</span>
            <span className="readout__value">
              <span className="readout__tier">{TIER_META[tier].label}</span>
            </span>
            <span className="readout__bar" aria-hidden>
              {SEGS.map((i) => (
                <span key={i} className="readout__seg" />
              ))}
            </span>
            <span className="readout__gloss">{TIER_META[tier].gloss}</span>
          </div>
        ) : sr ? (
          <div className={`readout readout--${sr.tone}`}>
            <span className="readout__cap">结论</span>
            <span className="readout__value">
              <span className="readout__tier">{sr.label}</span>
            </span>
            {sr.gloss ? <span className="readout__gloss">{sr.gloss}</span> : null}
          </div>
        ) : null}

        <div className="verdict__status">
          <span className="statuschip">
            {statusLabel(result.status)}
            <span className="mono">{result.status}</span>
          </span>
          {summary ? <p className="verdict__summary">{summary}</p> : null}
          {statusBlurb(result.status) ? <p className="verdict__blurb">{statusBlurb(result.status)}</p> : null}
        </div>
      </div>

      {showCompare || num || runNum != null || result.estimator_failure || hasDetail ? (
        <div className="verdict__body">
          {/* The number IS the answer — always visible. */}
          {showCompare ? (
            <div className="compare">
              <div className="compare__col compare__col--bad">
                <span className="compare__tag">✕ 未调整 · 粗相关</span>
                <span className="compare__num mono">{fmtNum(naive)}</span>
                <span className="compare__note">直接对比两组——被混杂带偏</span>
              </div>
              <div className="compare__col compare__col--good">
                <span className="compare__tag">✓ Themis 调整后</span>
                <span className="compare__num mono">{fmtNum(num!.point)}</span>
                <span className="compare__note">
                  {num!.ci_lower != null && num!.ci_upper != null
                    ? `${Math.round((num!.ci_level ?? 0.95) * 100)}% CI [${fmtNum(num!.ci_lower)}, ${fmtNum(num!.ci_upper)}]`
                    : ''}
                  {num!.adjustment?.length ? ` · 调整 {${num!.adjustment.join(', ')}}` : ''}
                </span>
              </div>
              <p className="compare__lesson">两个数明显不同 —— 混杂在作怪。这就是为什么要做因果调整,而不是直接对比。</p>
            </div>
          ) : num && shaped ? (
            /* An estimate whose estimand has no single number — a curve, a
               decomposition, a joint contrast, a bounded cell. Read through
               the same shape vocabulary the report uses; this branch used to
               not exist, so all of them rendered as one em-dash. */
            <div className="figure">
              <span className="figure__cap">{shaped.cap}{num.method ? ` · ${num.method}` : ''}</span>
              <div className="pathlist">
                {shaped.rows.map((r, i) => (
                  <div className="boundsexpr__row" key={i}>
                    <span className="boundsexpr__k">{r.label}</span>
                    <span className="boundsexpr__v mono">{r.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : num ? (
            <div className="figure">
              <span className="figure__cap">数值估计{num.method ? ` · ${num.method}` : ''}</span>
              <span className="figure__point mono">{fmtNum(num.point)}</span>
              {num.ci_lower != null && num.ci_upper != null ? (
                <span className="figure__ci mono">
                  {Math.round((num.ci_level ?? 0.95) * 100)}% CI · [{fmtNum(num.ci_lower)}, {fmtNum(num.ci_upper)}]
                  {num.adjustment?.length ? ` · 调整 {${num.adjustment.join(', ')}}` : ''}
                </span>
              ) : null}
            </div>
          ) : runNum != null ? (
            <div className="figure">
              <span className="figure__cap">点估计</span>
              <span className="figure__point mono">{fmtNum(runNum)}</span>
            </div>
          ) : null}

          {/* Estimator refusal — a load-bearing reason; kept visible. */}
          {result.estimator_failure ? (
            <div className="boundsexpr">
              <div className="boundsexpr__row">
                <span className="boundsexpr__k">拒绝</span>
                <span className="boundsexpr__v">{result.estimator_failure.failure_type}</span>
              </div>
              <p className="boundsexpr__note">{result.estimator_failure.reason}</p>
            </div>
          ) : null}

          {/* How it was computed — formula / paths / bounds / ledger. Machine
              artifacts a lay reader rarely needs; folded, nothing removed. */}
          {hasDetail ? (
            <Foldout summary="怎么算出来的 · 识别路线 / 公式 / 路径 / 假设">
              {routes.map((r, i) => (
                <div className="boundsexpr" key={`route-${i}`}>
                  <span className="figure__cap">{r.cap}</span>
                  {r.rows.map((row, j) => (
                    <div className="boundsexpr__row" key={j}>
                      <span className="boundsexpr__k">{row.label}</span>
                      <span className="boundsexpr__v">{row.value}</span>
                    </div>
                  ))}
                </div>
              ))}

              {paths.length ? (
                <div className="figure">
                  <span className="figure__cap">{result.query_kind === 'cause' ? '因果路径' : '支持路径'}</span>
                  <div className="pathlist">
                    {paths.map((p, i) => (
                      <div className="pathchain" key={i}>
                        {p.map((node, j) => (
                          <span className="pathchain__seg" key={j}>
                            <span className="pathnode mono">{cleanPathNode(node)}</span>
                            {j < p.length - 1 ? <span className="pathchain__arrow" aria-hidden>→</span> : null}
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {formula ? (
                <div className="figure">
                  <span className="figure__cap">识别公式</span>
                  <span className="formula mono">{formula}</span>
                </div>
              ) : null}

              {bounds ? (
                <div className="boundsexpr">
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">方法</span>
                    <span className="boundsexpr__v">{bounds.method}</span>
                  </div>
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">下界</span>
                    <span className="boundsexpr__v">{bounds.lower_expression}</span>
                  </div>
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">上界</span>
                    <span className="boundsexpr__v">{bounds.upper_expression}</span>
                  </div>
                  {bounds.width_when_uninformative ? (
                    <p className="boundsexpr__note">⚠ 这个区间退化到 [0,1] / [-1,1],诚实但无实际辨别力——需要更强假设或数据才能收窄。</p>
                  ) : (
                    <p className="boundsexpr__note">符号区间:把可观测分布代入即可得到数值区间。</p>
                  )}
                </div>
              ) : null}

              {sens?.e_value != null ? (
                <div className="boundsexpr">
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">E-value</span>
                    <span className="boundsexpr__v">{fmtNum(sens.e_value)}{sens.e_value_ci_bound != null ? ` · CI 界 ${fmtNum(sens.e_value_ci_bound)}` : ''}</span>
                  </div>
                  <p className="boundsexpr__note">敏感性:未测混杂要同时把处理与结局的风险比拉到 ≥ {fmtNum(sens.e_value)} 才能解释掉这个效应。越大越稳健。</p>
                </div>
              ) : null}

              {ledger?.assumptions?.length ? (
                <div className="ledger">
                  <span className="figure__cap">假设台账{ledger.summary ? ` · ${ledger.summary}` : ''}</span>
                  <ul className="ledger__list">
                    {ledger.assumptions.map((a, i) => (
                      <li className="ledger__item" key={i}>
                        <span className={`ledger__sev ledger__sev--${a.severity ?? 'info'}`}>{a.severity ?? ''}</span>
                        <span className="ledger__claim">{a.claim}</span>
                        {a.testable === false ? <span className="ledger__tag">不可检验</span> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Foldout>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
