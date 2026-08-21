import type { DataGapReport } from '../types'
import { gapTitle, severityLabel } from '../lib/verdict'
import { fill, say, useLang, type Words } from '../lib/language'
import { Clamp } from './Clamp'
import { Foldout } from './Foldout'

const SEV_ORDER: Record<string, number> = { blocking: 0, important: 1, informational: 2 }

const SAYS = {
  region: { zh: '数据缺口报告', en: 'Data gaps' },
  title: { zh: '还缺什么', en: "What's missing" },
  count: { zh: '{n} 项', en: '{n} gaps' },
  blocking: { zh: ' · {n} 阻断', en: ' · {n} blocking' },
  ifProvided: { zh: '补上后：', en: 'Once you have it:' },
  needs: { zh: '需要：', en: 'Needs:' },
  someData: { zh: '数据', en: 'data' },
  nextSteps: { zh: '下一步', en: 'Next steps' },
} satisfies Record<string, Words>

export function GapReport({ report }: { report: DataGapReport }) {
  const lang = useLang()
  const gaps = [...(report.gaps ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )
  if (gaps.length === 0 && !(report.actionable_next_steps?.length)) return null

  const blocking = gaps.filter((g) => g.severity === 'blocking').length

  return (
    <section className="gaps" aria-label={say(SAYS.region, lang, 'region')}>
      <Foldout
        summary={<span className="gaps__title">{say(SAYS.title, lang, 'title')}</span>}
        count={
          fill(SAYS.count, lang, { n: gaps.length }) +
          (blocking ? fill(SAYS.blocking, lang, { n: blocking }) : '')
        }
      >
      <ol className="gaplist">
        {gaps.map((g, i) => (
          <li className="gap" key={`${g.kind}-${i}`}>
            <span className="gap__index" aria-hidden />
            <div className="gap__main">
              <div className="gap__top">
                <span className={`sev sev--${g.severity}`}>
                  <span className="sev__mark" aria-hidden />
                  {severityLabel(g.severity, lang)}
                </span>
                <span className="gap__kindtitle">{gapTitle(g.kind, lang)}</span>
                <span className="gap__kind">{g.kind}</span>
              </div>
              <p className="gap__desc"><Clamp text={g.description} /></p>
              {g.if_provided ? (
                <p className="gap__needs">
                  <b>{say(SAYS.ifProvided, lang, 'ifProvided')}</b> {g.if_provided}
                </p>
              ) : null}
              {g.required_data?.variables?.length ? (
                <p className="gap__needs">
                  <b>{say(SAYS.needs, lang, 'needs')}</b>{' '}
                  {g.required_data.data_type ?? say(SAYS.someData, lang, 'someData')} · {g.required_data.variables.join(', ')}
                  {g.required_data.min_sample_size ? ` · n≥${g.required_data.min_sample_size}` : ''}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {report.actionable_next_steps?.length ? (
        <div className="steps">
          <p className="steps__cap">{say(SAYS.nextSteps, lang, 'nextSteps')}</p>
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
