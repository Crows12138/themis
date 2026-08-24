import { useState } from 'react'
import { FRAMING_FIELDS } from '../lib/verdict'
import { fill, useLang, type Words } from '../lib/language'
import type { ClarifyPick } from '../api'
import { Foldout } from './Foldout'

type FieldMap = Record<string, string>

const SAYS = {
  region: { zh: '补缺口', en: 'Fill the gaps' },
  title: { zh: '补缺口 · 把变量定义清楚', en: 'Fill the gaps · pin down what each variable means' },
  count: { zh: '{n} 个变量缺操作化定义', en: '{n} variables have no operational definition' },
  intro: {
    zh: '每个变量点「补全并重跑」即可用合理默认补上；想更精确，展开「维度」改任意字段——默认是起点，不是牢笼。补完内核会重新核验。',
    en: 'Hit "Fill in and re-run" to take sensible defaults for every variable; to be more exact, open a variable and edit any field — the defaults are a starting point, not a cage. The kernel re-checks everything afterwards.',
  },
  shut: { zh: '收起维度', en: 'Hide the fields' },
  open: { zh: '展开维度 ▾', en: 'Show the fields ▾' },
  rerunning: { zh: '重跑中…', en: 'Re-running…' },
  go: { zh: '补全并重跑 →', en: 'Fill in and re-run →' },
} satisfies Record<string, Words>

/** 补缺口: fill the operationalization fields for the variables that
 * carry a framing gap, then re-run (apply_patch_and_run). A field left
 * blank is answered too — the server records it as taking the standard
 * operationalisation, which the result then discloses. */
export function FramingFill({ vars, busy, onSubmit }: { vars: string[]; busy: boolean; onSubmit: (picks: ClarifyPick[]) => void }) {
  const [fields, setFields] = useState<Record<string, FieldMap>>(() =>
    Object.fromEntries(vars.map((v) => [v, {}])),
  )
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const lang = useLang()

  function setField(v: string, key: string, value: string) {
    setFields((f) => ({ ...f, [v]: { ...f[v], [key]: value } }))
  }

  function submit() {
    onSubmit(vars.map((v) => ({ predicate: v, fields: fields[v] ?? {} })))
  }

  return (
    <section className="framing" aria-label={fill(SAYS.region, lang)}>
      <Foldout
        summary={<span className="framing__title">{fill(SAYS.title, lang)}</span>}
        count={fill(SAYS.count, lang, { n: vars.length })}
      >
      <p className="framing__intro">{fill(SAYS.intro, lang)}</p>

      <div className="framing__list">
        {vars.map((v) => (
          <div className="framevar" key={v}>
            <div className="framevar__top">
              <span className="framevar__name mono">{v}</span>
              <button className="linklike" onClick={() => setOpen((o) => ({ ...o, [v]: !o[v] }))}>
                {fill(open[v] ? SAYS.shut : SAYS.open, lang)}
              </button>
            </div>
            {open[v] ? (
              <div className="framevar__fields">
                {FRAMING_FIELDS.map((f) => (
                  <label className="framefield" key={f.key}>
                    <span className="framefield__label">{fill(f.label, lang)}</span>
                    <input
                      className="framefield__input"
                      value={fields[v]?.[f.key] ?? ''}
                      placeholder={fill(f.placeholder, lang)}
                      onChange={(e) => setField(v, f.key, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <button className="btn framing__go" onClick={submit} disabled={busy}>
        {fill(busy ? SAYS.rerunning : SAYS.go, lang)}
      </button>
      </Foldout>
    </section>
  )
}
