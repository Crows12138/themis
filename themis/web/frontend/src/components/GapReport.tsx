import type { DataGap, DataGapReport } from '../types'
import {
  gapDescribes, gapIfProvided, gapTitle, gapWanted, gapWent, severityLabel,
  stated,
} from '../lib/verdict'
import { fill, useLang, type Lang, type Words } from '../lib/language'
import { Clamp } from './Clamp'
import { Foldout } from './Foldout'

const SEV_ORDER: Record<string, number> = { blocking: 0, important: 1, informational: 2 }

const SAYS = {
  region: { zh: '数据缺口报告', en: 'Data gaps' },
  title: { zh: '还缺什么', en: "What's missing" },
  count: { zh: '{n} 项', en: '{n} gaps' },
  blocking: { zh: ' · {n} 阻断', en: ' · {n} blocking' },
  ifProvided: { zh: '补上后：', en: 'Once you have it:' },
  alternatives: { zh: '或：', en: 'Or:' },
  needs: { zh: '需要：', en: 'Needs:' },
  someData: { zh: '数据', en: 'data' },
  nextSteps: { zh: '下一步', en: 'Next steps' },
  // The frame around a kernel-supplied phrase. This surface's own
  // sentence, like the captions above it — what is shared with the report
  // is the phrase that goes in the hole, and that comes from GAP_WANTED.
  supply: { zh: '补 {wanted}', en: 'supply {wanted}' },
  // What goes between two of a gap's statements. Typography of the
  // paragraph this surface lays out, so it is declared with the surface's
  // other wording — the same arrangement as the list separator elsewhere.
  seam: { zh: '', en: ' ' },
} satisfies Record<string, Words>

// What closing this gap would take, one item per thing the block states.
//
// Assembled rather than written out inline because the block has grown a
// second kind of entry: some of it is VALUES (a data type, the variables, a
// count) and some of it is STATEMENTS the kernel names and this surface
// says — what a sample of that size would buy, when the measurements would
// have to be taken, how the design could break SUTVA. Those three used to
// arrive as finished text and so could only be in one language.
//
// The list used to be shown only when `variables` was non-empty, which hid
// the whole block for every gap that names a sample size or a schedule
// without naming columns — the dose-response one names none.
function needed(rd: DataGap['required_data'], lang: Lang): string[] {
  if (!rd) return []
  const out: string[] = []
  if (rd.variables?.length) {
    out.push(`${rd.data_type ?? fill(SAYS.someData, lang)} · ${rd.variables.join(', ')}`)
  } else if (rd.data_type) {
    out.push(rd.data_type)
  }
  if (rd.confounders_required?.length) out.push(rd.confounders_required.join(', '))
  if (rd.min_sample_size) out.push(`n≥${rd.min_sample_size}`)
  if (rd.precision_target) out.push(stated(rd.precision_target, lang))
  if (rd.time_window) out.push(stated(rd.time_window, lang))
  for (const one of rd.sutva_concerns ?? []) out.push(stated(one, lang))
  return out.filter(Boolean)
}

export function GapReport({ report }: { report: DataGapReport }) {
  const lang = useLang()
  const gaps = [...(report.gaps ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )
  if (gaps.length === 0) return null

  // The next-steps tail, assembled here rather than read off the envelope:
  // every input to it is on the gaps this component is already showing.
  const steps = gaps
    .filter((g) => g.severity !== 'informational' && gapIfProvided(g, lang))
    .map((g) => fill(SAYS.supply, lang, { wanted: gapWanted(g.kind, lang) }))

  const blocking = gaps.filter((g) => g.severity === 'blocking').length

  return (
    <section className="gaps" aria-label={fill(SAYS.region, lang)}>
      <Foldout
        summary={<span className="gaps__title">{fill(SAYS.title, lang)}</span>}
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
              <p className="gap__desc">
                <Clamp text={gapDescribes(g, lang).join(fill(SAYS.seam, lang))} />
              </p>
              {gapIfProvided(g, lang) ? (
                <p className="gap__needs">
                  <b>{fill(SAYS.ifProvided, lang)}</b> {gapIfProvided(g, lang)}
                </p>
              ) : null}
              {g.alternative_paths?.length ? (
                <p className="gap__needs">
                  <b>{fill(SAYS.alternatives, lang)}</b>{' '}
                  {g.alternative_paths.map((a) => gapWent(a, lang)).join(' ')}
                </p>
              ) : null}
              {needed(g.required_data, lang).length ? (
                <p className="gap__needs">
                  <b>{fill(SAYS.needs, lang)}</b>{' '}
                  {needed(g.required_data, lang).join(' · ')}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {steps.length ? (
        <div className="steps">
          <p className="steps__cap">{fill(SAYS.nextSteps, lang)}</p>
          <ol>
            {steps.map((s, i) => (
              <li key={i}><Clamp text={s} lines={2} /></li>
            ))}
          </ol>
        </div>
      ) : null}
      </Foldout>
    </section>
  )
}
