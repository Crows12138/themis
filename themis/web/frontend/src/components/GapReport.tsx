import type { DataGap, DataGapReport } from '../types'
import {
  gapDescribes, gapIfProvided, gapTitle, gapWanted, gapWent, sentences,
  severityLabel, stated,
} from '../lib/verdict'
import { fill, useLang, type Lang, type Words } from '../lib/language'
import { named } from '../lib/names'
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
  // A distribution shown as the table its missing cells make up.
  table: { zh: '：这张表还缺 {n} 个数', en: ': {n} of its values are missing' },
  cells: { zh: '逐个列出这 {n} 个', en: 'List all {n}' },
  supplyTable: { zh: '补 {name} 的 {n} 个数', en: 'supply the {n} values of {name}' },
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

// The lines a gap says under its description, each with its caption. Empty
// text is a line this gap does not have.
interface Line { caption: Words; text: string }

function lines(g: DataGap, lang: Lang): Line[] {
  return [
    { caption: SAYS.ifProvided, text: gapIfProvided(g, lang) },
    { caption: SAYS.alternatives, text: (g.alternative_paths ?? []).map((a) => gapWent(a, lang)).join(' ') },
    { caption: SAYS.needs, text: needed(g.required_data, lang).join(' · ') },
  ]
}

function Said({ line, lang }: { line: Line; lang: Lang }) {
  return line.text ? (
    <p className="gap__needs"><b>{fill(line.caption, lang)}</b> {named(line.text)}</p>
  ) : null
}

// A distribution's missing cells are filed one gap each, and a graph with k
// binary common causes of its outcome files 2^k of them for one table. A
// row is either one gap or the cells of one distribution at one severity,
// shown as that table: its name once, the lines every cell shares once, and
// the cells under it with whatever line they do not share — so showing them
// together drops nothing a cell says.
interface Row { gaps: DataGap[]; distribution?: string }

function rowsOf(gaps: DataGap[]): Row[] {
  const out: Row[] = []
  const tables = new Map<string, Row>()
  for (const g of gaps) {
    const name = g.kind === 'missing_distribution' ? g.distribution : undefined
    if (!name) {
      out.push({ gaps: [g] })
      continue
    }
    const key = `${g.severity}\u0000${name}`
    const row = tables.get(key)
    if (row) {
      row.gaps.push(g)
    } else {
      const fresh: Row = { gaps: [g], distribution: name }
      tables.set(key, fresh)
      out.push(fresh)
    }
  }
  return out
}

function Top({ g, lang }: { g: DataGap; lang: Lang }) {
  return (
    <div className="gap__top">
      <span className={`sev sev--${g.severity}`}>
        <span className="sev__mark" aria-hidden />
        {severityLabel(g.severity, lang)}
      </span>
      <span className="gap__kindtitle" title={g.kind}>{gapTitle(g.kind, lang)}</span>
    </div>
  )
}

function OneGap({ g, lang }: { g: DataGap; lang: Lang }) {
  return (
    <>
      <Top g={g} lang={lang} />
      <p className="gap__desc">
        <Clamp text={sentences(gapDescribes(g, lang), lang)} />
      </p>
      {lines(g, lang).map((line, i) => <Said key={i} line={line} lang={lang} />)}
    </>
  )
}

function Table({ row, lang }: { row: Row; lang: Lang }) {
  const said = row.gaps.map((g) => lines(g, lang))
  // Which of the lines every cell says alike, by position.
  const shared = said[0].map((line, i) => said.every((one) => one[i].text === line.text))
  return (
    <>
      <Top g={row.gaps[0]} lang={lang} />
      <p className="gap__desc">
        <span className="mono">{row.distribution ? named(row.distribution) : null}</span>
        {fill(SAYS.table, lang, { n: row.gaps.length })}
      </p>
      {said[0].map((line, i) => (shared[i] ? <Said key={i} line={line} lang={lang} /> : null))}
      <Foldout summary={fill(SAYS.cells, lang, { n: row.gaps.length })}>
        <ol className="gap__cells">
          {row.gaps.map((g, c) => (
            <li key={c}>
              <Clamp text={sentences(gapDescribes(g, lang), lang)} lines={2} />
              {said[c].map((line, i) => (shared[i] ? null : <Said key={i} line={line} lang={lang} />))}
            </li>
          ))}
        </ol>
      </Foldout>
    </>
  )
}

export function GapReport({ report }: { report: DataGapReport }) {
  const lang = useLang()
  const gaps = [...(report.gaps ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )
  if (gaps.length === 0) return null
  const rows = rowsOf(gaps)

  // The next-steps tail, assembled here rather than read off the envelope:
  // every input to it is on the gaps this component is already showing. A
  // distribution is named by its name, and a table is one step.
  const steps = rows
    .filter((row) => row.gaps[0].severity !== 'informational' && gapIfProvided(row.gaps[0], lang))
    .map((row) =>
      !row.distribution
        ? fill(SAYS.supply, lang, { wanted: gapWanted(row.gaps[0].kind, lang) })
        : row.gaps.length > 1
          ? fill(SAYS.supplyTable, lang, { name: row.distribution, n: row.gaps.length })
          : fill(SAYS.supply, lang, { wanted: row.distribution }),
    )

  const blocking = rows.filter((row) => row.gaps[0].severity === 'blocking').length

  return (
    <section className="gaps" aria-label={fill(SAYS.region, lang)}>
      <Foldout
        summary={<span className="gaps__title">{fill(SAYS.title, lang)}</span>}
        count={
          fill(SAYS.count, lang, { n: rows.length }) +
          (blocking ? fill(SAYS.blocking, lang, { n: blocking }) : '')
        }
      >
      <ol className="gaplist">
        {rows.map((row, i) => (
          <li className="gap" key={`${row.gaps[0].kind}-${i}`}>
            <span className="gap__index" aria-hidden />
            <div className="gap__main">
              {row.gaps.length > 1
                ? <Table row={row} lang={lang} />
                : <OneGap g={row.gaps[0]} lang={lang} />}
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
