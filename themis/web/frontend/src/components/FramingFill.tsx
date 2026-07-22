import { useState } from 'react'
import { FRAMING_FIELDS } from '../lib/verdict'
import type { ClarifyPick } from '../api'
import { Foldout } from './Foldout'

type FieldMap = Record<string, string>

/** 补缺口: fill the operationalization fields for the variables that
 * carry a framing gap, then re-run (apply_patch_and_run). Leaving fields
 * blank uses sensible defaults on the server — "采用标准操作化". */
export function FramingFill({ vars, busy, onSubmit }: { vars: string[]; busy: boolean; onSubmit: (picks: ClarifyPick[]) => void }) {
  const [fields, setFields] = useState<Record<string, FieldMap>>(() =>
    Object.fromEntries(vars.map((v) => [v, {}])),
  )
  const [open, setOpen] = useState<Record<string, boolean>>({})

  function setField(v: string, key: string, value: string) {
    setFields((f) => ({ ...f, [v]: { ...f[v], [key]: value } }))
  }

  function submit() {
    onSubmit(vars.map((v) => ({ predicate: v, fields: fields[v] ?? {} })))
  }

  return (
    <section className="framing" aria-label="补缺口">
      <Foldout
        summary={<span className="framing__title">补缺口 · 把变量定义清楚</span>}
        count={`${vars.length} 个变量缺操作化定义`}
      >
      <p className="framing__intro">
        每个变量点「补全并重跑」即可用合理默认补上;想更精确,展开「维度」改任意字段——默认是起点,不是牢笼。补完内核会重新核验。
      </p>

      <div className="framing__list">
        {vars.map((v) => (
          <div className="framevar" key={v}>
            <div className="framevar__top">
              <span className="framevar__name mono">{v}</span>
              <button className="linklike" onClick={() => setOpen((o) => ({ ...o, [v]: !o[v] }))}>
                {open[v] ? '收起维度' : '展开维度 ▾'}
              </button>
            </div>
            {open[v] ? (
              <div className="framevar__fields">
                {FRAMING_FIELDS.map((f) => (
                  <label className="framefield" key={f.key}>
                    <span className="framefield__label">{f.label}</span>
                    <input
                      className="framefield__input"
                      value={fields[v]?.[f.key] ?? ''}
                      placeholder={f.placeholder}
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
        {busy ? '重跑中…' : '补全并重跑 →'}
      </button>
      </Foldout>
    </section>
  )
}
