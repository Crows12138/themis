import type { QueryResult } from '../types'
import { TIER_META, statusLabel, fmtNum, structuralReadout, cleanPathNode } from '../lib/verdict'

const SEGS = [0, 1, 2]

export function Verdict({ result }: { result: QueryResult }) {
  const report = result.data_gap_report
  const tier = report?.answer_tier
  const summary = report?.summary?.trim()
  const num = result.numeric_estimate
  const bounds = result.bounds_result
  const struct = result.structural_result
  // For cause / assoc queries the kernel's answer IS the structural
  // result (yes/no + supporting paths); they carry no answer_tier.
  const sr = !tier && struct ? structuralReadout(result.query_kind, struct.value) : null
  const paths = struct?.supporting_paths?.filter((p) => p.length > 0) ?? []

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
        </div>
      </div>

      {num || bounds || result.estimator_failure || paths.length ? (
        <div className="verdict__body">
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

          {num ? (
            <div className="figure">
              <span className="figure__cap">数值估计{num.method ? ` · ${num.method}` : ''}</span>
              <span className="figure__point mono">{fmtNum(num.point)}</span>
              {num.ci_lower != null && num.ci_upper != null ? (
                <span className="figure__ci mono">
                  {Math.round((num.ci_level ?? 0.95) * 100)}% CI · [{fmtNum(num.ci_lower)}, {fmtNum(num.ci_upper)}]
                </span>
              ) : null}
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

          {result.estimator_failure ? (
            <div className="boundsexpr">
              <div className="boundsexpr__row">
                <span className="boundsexpr__k">拒绝</span>
                <span className="boundsexpr__v">{result.estimator_failure.failure_type}</span>
              </div>
              <p className="boundsexpr__note">{result.estimator_failure.reason}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
