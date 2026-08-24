import { useEffect, useRef, useState, type ReactNode } from 'react'
import { parseQuery } from '../lib/graph'
import { fill, say, useLang, type Words } from '../lib/language'
import { CausalCanvas, type CausalCanvasHandle } from './CausalCanvas'

// What `serialize` refuses on. Words rather than strings because the check
// runs where no reader is present and the message is read where one is — the
// same split the kernel's own refusals make.
const REFUSES = {
  tooFew: { zh: '至少需要两个变量', en: 'At least two variables are needed' },
  duplicate: { zh: '变量名有重复——每个变量名要唯一', en: 'Two variables share a name — each name has to be unique' },
  blank: { zh: '有变量名是空的', en: 'A variable has no name' },
  noQuery: { zh: '请在下方选择「干预 X」和「结果 Y」', en: 'Pick an intervention X and an outcome Y below' },
  sameVar: { zh: '干预和结果不能是同一个变量', en: 'The intervention and the outcome cannot be the same variable' },
} satisfies Record<string, Words>

const SAYS = {
  emptyCanvas: { zh: '空画布', en: 'Empty canvas' },
  addFirst: { zh: '加第一个变量', en: 'Add the first variable' },
  clear: { zh: '清空', en: 'Clear' },
  query: { zh: '查询', en: 'Query' },
  doX: { zh: '干预 do(', en: 'intervene do(' },
  outcome: { zh: '结果', en: 'outcome' },
  queryKind: { zh: '查询类型', en: 'Query kind' },
  effect: { zh: '效应 effect', en: 'effect' },
  identify: { zh: '可识别？identify', en: 'identifiable? identify' },
  counterfactual: { zh: '反事实 counterfactual', en: 'counterfactual' },
  checking: { zh: '核验中…', en: 'Checking…' },
} satisfies Record<string, Words>

function atom(pred: string) {
  return { predicate: pred, args: [{ type: 'const', name: 'me' }] }
}

export interface DagBuilderProps {
  submitLabel: string
  onSubmit: (program: Record<string, unknown>) => void
  busy?: boolean
  banner?: ReactNode
  intro?: ReactNode
  /** Carry an existing graph into the canvas (from a result handoff) — the
   *  canvas pre-fills the nodes/edges, this shell pre-fills the query. */
  initialProgram?: Record<string, unknown>
}

/**
 * Build a causal graph by hand (or seeded from a handoff) and hand it to the
 * kernel. A thin shell over the shared CausalCanvas: it adds the query bar
 * (intervention / outcome / query kind) and serializes the canvas + query
 * into a kernel_ast.
 */
export function DagBuilder({ submitLabel, onSubmit, busy, banner, intro, initialProgram }: DagBuilderProps) {
  const ref = useRef<CausalCanvasHandle>(null)
  const [varNames, setVarNames] = useState<string[]>([])
  const [qx, setQx] = useState('')
  const [qy, setQy] = useState('')
  const [qkind, setQkind] = useState<'effect' | 'identify' | 'counterfactual'>('effect')
  const [error, setError] = useState<Words | null>(null)
  const lang = useLang()

  // Pre-fill the query from a handed-off program (the graph is seeded by the
  // canvas). initialProgram is set once per mount, so this runs once.
  useEffect(() => {
    if (!initialProgram) return
    const q = parseQuery(initialProgram)
    setQx(q.qx)
    setQy(q.qy)
    setQkind(q.qkind)
  }, [initialProgram])

  function serialize(): { program: Record<string, unknown> } | { refused: Words } {
    const ns = ref.current?.getNodes() ?? []
    const es = ref.current?.getEdges() ?? []
    const names = ns.map((n) => (n.data.label as string).trim())
    if (names.length < 2) return { refused: REFUSES.tooFew }
    if (new Set(names).size !== names.length) return { refused: REFUSES.duplicate }
    if (names.some((n) => !n)) return { refused: REFUSES.blank }
    if (!qx || !qy) return { refused: REFUSES.noQuery }
    if (qx === qy) return { refused: REFUSES.sameVar }

    const labelOf = new Map(ns.map((n) => [n.id, (n.data.label as string).trim()]))
    const statements: Record<string, unknown>[] = names.map((n) => ({ kind: 'variable', predicate: n, domain: [true, false] }))
    for (const e of es) {
      const a = labelOf.get(e.source) ?? e.source
      const b = labelOf.get(e.target) ?? e.target
      if ((e.data as { kind?: string })?.kind === 'bidirected') statements.push({ kind: 'bidirected', left: atom(a), right: atom(b) })
      else statements.push({ kind: 'cause', from: atom(a), to: atom(b) })
    }

    let query: Record<string, unknown>
    if (qkind === 'identify') query = { kind: 'identify', intervention: { atom: atom(qx), value: true }, target: atom(qy), given: [] }
    else if (qkind === 'counterfactual')
      query = { kind: 'counterfactual', observed: { atom: atom(qx), value: false }, counterfactual_intervention: { atom: atom(qx), value: true }, counterfactual_target: { atom: atom(qy), value: true } }
    else query = { kind: 'effect', intervention: { atom: atom(qx), value: true }, target: { atom: atom(qy), value: true }, given: [] }
    statements.push({ kind: 'query', id: 'q', query })

    return { program: { version: '0.1', domain: { objects: [{ kind: 'object', name: 'me' }] }, statements } }
  }

  function submit() {
    const built = serialize()
    if ('refused' in built) {
      setError(built.refused)
      return
    }
    setError(null)
    onSubmit(built.program)
  }

  return (
    <div className="build">
      {intro}

      <CausalCanvas
        ref={ref}
        seedProgram={initialProgram}
        seedEditable
        height={440}
        onVarsChange={setVarNames}
        emptyHint={
          <>
            <p>{fill(SAYS.emptyCanvas, lang)}</p>
            <button className="linklike" onClick={() => ref.current?.addVariable()}>{fill(SAYS.addFirst, lang)}</button>
          </>
        }
        toolbarExtra={
          varNames.length > 0 ? (
            <button className="btn btn--ghost" onClick={() => { ref.current?.clear(); setQx(''); setQy('') }}>{fill(SAYS.clear, lang)}</button>
          ) : null
        }
      />

      {banner}

      <div className="querybar">
        <span className="querybar__q">{fill(SAYS.query, lang)}</span>
        <Select label={fill(SAYS.doX, lang)} value={qx} onChange={setQx} options={varNames} />
        <span className="querybar__arrow">)→</span>
        <Select label={fill(SAYS.outcome, lang)} value={qy} onChange={setQy} options={varNames} />
        <select className="qselect" value={qkind} onChange={(e) => setQkind(e.target.value as typeof qkind)} aria-label={fill(SAYS.queryKind, lang)}>
          <option value="effect">{fill(SAYS.effect, lang)}</option>
          <option value="identify">{fill(SAYS.identify, lang)}</option>
          <option value="counterfactual">{fill(SAYS.counterfactual, lang)}</option>
        </select>
        <button className="btn" onClick={submit} disabled={busy}>
          {busy ? fill(SAYS.checking, lang) : submitLabel}
        </button>
      </div>

      {error ? (
        <div className="errbox" role="alert">
          <p className="errbox__msg">{say(error, lang, '')}</p>
        </div>
      ) : null}
    </div>
  )
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <label className="qfield">
      <span className="qfield__label">{label}</span>
      <select className="qselect" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}
