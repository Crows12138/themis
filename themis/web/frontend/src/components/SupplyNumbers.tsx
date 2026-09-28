import { useEffect, useState } from 'react'
import { asks, errorText, type Asked, type AskedTable, type SupplyAnswer } from '../api'
import { fill, useLang, type Words } from '../lib/language'
import { HOW_AN_ODDS_RATIO_READS } from '../lib/oddsRatio'
import { Foldout } from './Foldout'

const SAYS = {
  region: { zh: '自己填缺的数', en: 'Fill in the missing numbers yourself' },
  title: { zh: '有现成的数？自己填进去', en: 'Have the numbers? Fill them in yourself' },
  intro: {
    zh: '有数据、论文或统计资料里的数，就填在这里，不用 AI 估。每个数是一个条件概率，在 0 到 1 之间。没填的继续列在缺口里。填完后内核重新计算并复核。',
    en: 'If you have numbers from data, a paper or published statistics, enter them here instead of having the AI guess. Each is a conditional probability between 0 and 1. Anything left blank stays listed as a gap. The kernel recomputes and re-checks the answer afterwards.',
  },
  loading: { zh: '正在列出要填的数…', en: 'Listing the numbers to fill in…' },
  none: { zh: '这里没有能直接填的数。', en: 'There is no number to fill in here.' },
  // A table is asked for the way the AI is asked for it: fewer numbers than
  // its cells, and each one something a person can know. What the form
  // assumes is said here, before anyone commits to it, and again in the
  // assumption ledger beside the answer.
  tableIntro: {
    zh: '下面的表按「基线 + 优势比」来问，比逐格填少很多个数。基线：所有条件都取参照值时的概率（大于 0、小于 1）。',
    en: 'The tables below are asked for as a baseline and odds ratios, which is far fewer numbers than their cells. The baseline is the probability with every condition at its reference value (above 0 and below 1).',
  },
  noInteraction: {
    zh: '这种写法假设各个条件的作用互不影响（没有交互作用）：一个条件把优势乘以几倍，不管其他条件取什么值都一样。如果你知道它们有交互，就改成逐格填。这个假设会列在答案旁边的假设清单里。',
    en: 'This form assumes the conditions do not interact: each multiplies the odds by the same factor whatever the others are. If you know they interact, enter the table cell by cell instead. The assumption is listed with the others beside the answer.',
  },
  byCells: { zh: '改成逐格填（{n} 格）', en: 'Enter it cell by cell instead ({n} cells)' },
  byRatios: { zh: '改回按基线和优势比填', en: 'Back to a baseline and odds ratios' },
  baseline: { zh: '基线', en: 'Baseline' },
  notANumber: { zh: '不是一个数', en: 'not a number' },
  notAProbability: { zh: '要在 0 到 1 之间', en: 'must be between 0 and 1' },
  notABaseline: { zh: '要大于 0、小于 1', en: 'must be above 0 and below 1' },
  notARatio: { zh: '要大于 0', en: 'must be above 0' },
  incomplete: {
    zh: '这张表的基线和每个优势比要么都填，要么都不填',
    en: "fill in this table's baseline and every odds ratio, or none of them",
  },
  source: { zh: '这些数的来源（可选，会记在程序里）', en: 'Where these numbers come from (optional; kept in the program)' },
  sourceHint: { zh: '例如：某队列研究 2021；国家统计局 2023', en: 'e.g. a 2021 cohort study; national statistics 2023' },
  rerunning: { zh: '重跑中…', en: 'Re-running…' },
  go: { zh: '填进去并重跑 →', en: 'Fill in and re-run →' },
} satisfies Record<string, Words>

type Range = 'probability' | 'baseline' | 'ratio'

const OUT_OF_RANGE: Record<Range, Words> = {
  probability: SAYS.notAProbability,
  baseline: SAYS.notABaseline,
  ratio: SAYS.notARatio,
}

// Only what a reader can be told while typing. The kernel holds every one of
// these ranges itself — a probability, a baseline strictly inside (0, 1), a
// positive ratio are rules of the program schema — so this is where a typo is
// caught, not what makes a number admissible.
function inRange(v: number, range: Range): boolean {
  if (range === 'probability') return v >= 0 && v <= 1
  if (range === 'baseline') return v > 0 && v < 1
  return v > 0
}

// A field as typed: blank, a number in range, or what is wrong with it.
type Read = { blank: true } | { value: number } | { wrong: Words }

function read(text: string | undefined, range: Range): Read {
  const t = (text ?? '').trim()
  if (!t) return { blank: true }
  const v = Number(t)
  if (!Number.isFinite(v)) return { wrong: SAYS.notANumber }
  return inRange(v, range) ? { value: v } : { wrong: OUT_OF_RANGE[range] }
}

const isTable = (a: Asked): a is AskedTable => 'table' in a

// The field names under which each number is typed.
const cellField = (i: number) => `${i}`
const baselineField = (i: number) => `${i}:b`
const ratioField = (i: number, j: number) => `${i}:r${j}`
const tableCellField = (i: number, k: number) => `${i}:c${k}`

interface Gathered {
  answers: SupplyAnswer[]
  // What is wrong, by field, and by table for one left half-filled.
  wrong: Record<string, Words>
}

function gather(asked: Asked[], typed: Record<string, string>, byCells: Record<number, boolean>): Gathered {
  const answers: SupplyAnswer[] = []
  const wrong: Record<string, Words> = {}
  const each = (field: string, range: Range): number | undefined => {
    const r = read(typed[field], range)
    if ('wrong' in r) wrong[field] = r.wrong
    return 'value' in r ? r.value : undefined
  }
  for (const a of asked) {
    if (!isTable(a)) {
      const v = each(cellField(a.index), 'probability')
      if (v !== undefined) answers.push({ index: a.index, value: v })
    } else if (byCells[a.index]) {
      const cells = a.cells.flatMap((c) => {
        const v = each(tableCellField(a.index, c.cell), 'probability')
        return v === undefined ? [] : [{ cell: c.cell, value: v }]
      })
      if (cells.length) answers.push({ index: a.index, cells })
    } else {
      const fields = [baselineField(a.index), ...a.ratios.map((r) => ratioField(a.index, r.ratio))]
      const baseline = each(fields[0], 'baseline')
      const ratios = a.ratios.map((r) => each(ratioField(a.index, r.ratio), 'ratio'))
      const typedAny = fields.some((f) => (typed[f] ?? '').trim())
      if (!typedAny) continue
      if (baseline === undefined || ratios.some((v) => v === undefined)) {
        if (!fields.some((f) => wrong[f])) wrong[`${a.index}`] = SAYS.incomplete
        continue
      }
      answers.push({ index: a.index, baseline, odds_ratios: ratios as number[] })
    }
  }
  return { answers, wrong }
}

function Field({
  label, field, typed, wrong, onType,
}: {
  label: string
  field: string
  typed: Record<string, string>
  wrong: Record<string, Words>
  onType: (field: string, text: string) => void
}) {
  const lang = useLang()
  return (
    <label className="supply__row">
      <span className="supply__label mono">{label}</span>
      <input
        className="framefield__input supply__input mono"
        inputMode="decimal"
        value={typed[field] ?? ''}
        aria-invalid={wrong[field] ? true : undefined}
        onChange={(e) => onType(field, e.target.value)}
      />
      {wrong[field] ? <span className="supply__wrong">{fill(wrong[field], lang)}</span> : null}
    </label>
  )
}

/** 自己填缺的数: the probabilities the kernel is short of, asked the way the
 * AI is asked for them (`/api/asks`), typed in by the reader and run again
 * (`/api/supply`). No model is involved, so this is offered whether or not
 * the deployment has one. */
export function SupplyNumbers({
  program, busy, onSubmit,
}: {
  program: Record<string, unknown>
  busy: boolean
  onSubmit: (answers: SupplyAnswer[], source: string) => void
}) {
  const lang = useLang()
  const [open, setOpen] = useState(false)
  const [asked, setAsked] = useState<Asked[] | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [typed, setTyped] = useState<Record<string, string>>({})
  const [byCells, setByCells] = useState<Record<number, boolean>>({})
  const [source, setSource] = useState('')

  // What is asked is a fact about this program: another program — a re-run,
  // an edited graph, the numbers already supplied — is asked again, and
  // nothing typed against the last one's indices is kept.
  useEffect(() => {
    setAsked(null)
    setFailed(null)
    setTyped({})
    setByCells({})
  }, [program])

  useEffect(() => {
    if (!open || asked || failed) return
    let current = true
    asks(program).then(
      ({ requests }) => { if (current) setAsked(requests) },
      (e) => { if (current) setFailed(errorText(e, lang)) },
    )
    return () => { current = false }
  }, [open, asked, failed, program])

  const onType = (field: string, text: string) => setTyped((t) => ({ ...t, [field]: text }))
  const { answers, wrong } = asked ? gather(asked, typed, byCells) : { answers: [], wrong: {} }
  const ready = answers.length > 0 && Object.keys(wrong).length === 0
  const tables = (asked ?? []).filter(isTable)
  const shared = { typed, wrong, onType }

  return (
    <section className="framing" aria-label={fill(SAYS.region, lang)}>
      <Foldout summary={<span className="framing__title">{fill(SAYS.title, lang)}</span>} onToggle={setOpen}>
        <p className="framing__intro">{fill(SAYS.intro, lang)}</p>
        {failed ? <p className="supply__wrong">{failed}</p> : null}
        {open && !asked && !failed ? <p className="framing__intro">{fill(SAYS.loading, lang)}</p> : null}
        {asked && !asked.length ? <p className="framing__intro">{fill(SAYS.none, lang)}</p> : null}
        {tables.length ? (
          <>
            <p className="framing__intro">{fill(SAYS.tableIntro, lang)}</p>
            <p className="framing__intro">{fill(HOW_AN_ODDS_RATIO_READS, lang)}</p>
            <p className="framing__intro">{fill(SAYS.noInteraction, lang)}</p>
          </>
        ) : null}

        <div className="framing__list">
          {(asked ?? []).map((a) => !isTable(a) ? (
            <div className="framevar" key={a.index}>
              <Field label={a.probability} field={cellField(a.index)} {...shared} />
            </div>
          ) : (
            <div className="framevar" key={a.index}>
              <div className="framevar__top">
                <span className="framevar__name mono">{a.table}</span>
                <button className="linklike" onClick={() => setByCells((b) => ({ ...b, [a.index]: !b[a.index] }))}>
                  {fill(byCells[a.index] ? SAYS.byRatios : SAYS.byCells, lang, { n: a.cells.length })}
                </button>
              </div>
              {byCells[a.index]
                ? a.cells.map((c) => (
                    <Field key={c.cell} label={c.probability} field={tableCellField(a.index, c.cell)} {...shared} />
                  ))
                : (
                  <>
                    <Field label={`${fill(SAYS.baseline, lang)} ${a.baseline}`} field={baselineField(a.index)} {...shared} />
                    {a.ratios.map((r) => (
                      <Field key={r.ratio} label={r.label} field={ratioField(a.index, r.ratio)} {...shared} />
                    ))}
                  </>
                )}
              {wrong[`${a.index}`] ? <p className="supply__wrong">{fill(wrong[`${a.index}`], lang)}</p> : null}
            </div>
          ))}
        </div>

        {asked?.length ? (
          <>
            <label className="framefield supply__source">
              <span className="framefield__label">{fill(SAYS.source, lang)}</span>
              <input
                className="framefield__input"
                value={source}
                placeholder={fill(SAYS.sourceHint, lang)}
                onChange={(e) => setSource(e.target.value)}
              />
            </label>
            <button className="btn framing__go" onClick={() => onSubmit(answers, source)} disabled={busy || !ready}>
              {fill(busy ? SAYS.rerunning : SAYS.go, lang)}
            </button>
          </>
        ) : null}
      </Foldout>
    </section>
  )
}
