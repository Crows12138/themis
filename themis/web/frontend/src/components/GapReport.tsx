import type { DataGapReport } from '../types'
import { gapTitle, severityLabel } from '../lib/verdict'
import { Clamp } from './Clamp'
import { Foldout } from './Foldout'

const SEV_ORDER: Record<string, number> = { blocking: 0, important: 1, informational: 2 }

export function GapReport({ report }: { report: DataGapReport }) {
  const gaps = [...(report.gaps ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )
  if (gaps.length === 0 && !(report.actionable_next_steps?.length)) return null

  const blocking = gaps.filter((g) => g.severity === 'blocking').length

  return (
    <section className="gaps" aria-label="数据缺口报告">
      <Foldout
        summary={<span className="gaps__title">还缺什么</span>}
        count={`${gaps.length} 项${blocking ? ` · ${blocking} 阻断` : ''}`}
      >
      <ol className="gaplist">
        {gaps.map((g, i) => (
          <li className="gap" key={`${g.kind}-${i}`}>
            <span className="gap__index" aria-hidden />
            <div className="gap__main">
              <div className="gap__top">
                <span className={`sev sev--${g.severity}`}>
                  <span className="sev__mark" aria-hidden />
                  {severityLabel(g.severity)}
                </span>
                <span className="gap__kindtitle">{gapTitle(g.kind)}</span>
                <span className="gap__kind">{g.kind}</span>
              </div>
              <p className="gap__desc"><Clamp text={g.description} /></p>
              {g.if_provided ? (
                <p className="gap__needs">
                  <b>补上后:</b> {g.if_provided}
                </p>
              ) : null}
              {g.required_data?.variables?.length ? (
                <p className="gap__needs">
                  <b>需要:</b> {g.required_data.data_type ?? '数据'} · {g.required_data.variables.join(', ')}
                  {g.required_data.min_sample_size ? ` · n≥${g.required_data.min_sample_size}` : ''}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {report.actionable_next_steps?.length ? (
        <div className="steps">
          <p className="steps__cap">下一步</p>
          <ol>
            {report.actionable_next_steps.map((s, i) => (
              <li key={i}><Clamp text={s} lines={2} /></li>
            ))}
          </ol>
        </div>
      ) : null}
      </Foldout>
    </section>
  )
}
