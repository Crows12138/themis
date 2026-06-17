import { useEffect, useRef, useState, type ReactNode } from 'react'
import { parseQuery } from '../lib/graph'
import { CausalCanvas, type CausalCanvasHandle } from './CausalCanvas'

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
 * (干预 / 结果 / 查询类型) and serializes the canvas + query into a kernel_ast.
 */
export function DagBuilder({ submitLabel, onSubmit, busy, banner, intro, initialProgram }: DagBuilderProps) {
  const ref = useRef<CausalCanvasHandle>(null)
  const [varNames, setVarNames] = useState<string[]>([])
  const [qx, setQx] = useState('')
  const [qy, setQy] = useState('')
  const [qkind, setQkind] = useState<'effect' | 'identify' | 'counterfactual'>('effect')
  const [error, setError] = useState<string | null>(null)

  // Pre-fill the query from a handed-off program (the graph is seeded by the
  // canvas). initialProgram is set once per mount, so this runs once.
  useEffect(() => {
    if (!initialProgram) return
    const q = parseQuery(initialProgram)
    setQx(q.qx)
    setQy(q.qy)
    setQkind(q.qkind)
  }, [initialProgram])

  function serialize(): Record<string, unknown> | string {
    const ns = ref.current?.getNodes() ?? []
    const es = ref.current?.getEdges() ?? []
    const names = ns.map((n) => (n.data.label as string).trim())
    if (names.length < 2) return '至少需要两个变量'
    if (new Set(names).size !== names.length) return '变量名有重复——每个变量名要唯一'
    if (names.some((n) => !n)) return '有变量名是空的'
    if (!qx || !qy) return '请在下方选择「干预 X」和「结果 Y」'
    if (qx === qy) return '干预和结果不能是同一个变量'

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

    return { version: '0.1', domain: { objects: [{ kind: 'object', name: 'me' }] }, statements }
  }

  function submit() {
    const ast = serialize()
    if (typeof ast === 'string') {
      setError(ast)
      return
    }
    setError(null)
    onSubmit(ast)
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
            <p>空画布</p>
            <button className="linklike" onClick={() => ref.current?.addVariable()}>加第一个变量</button>
          </>
        }
        toolbarExtra={
          varNames.length > 0 ? (
            <button className="btn btn--ghost" onClick={() => { ref.current?.clear(); setQx(''); setQy('') }}>清空</button>
          ) : null
        }
      />

      {banner}

      <div className="querybar">
        <span className="querybar__q">查询</span>
        <Select label="干预 do(" value={qx} onChange={setQx} options={varNames} />
        <span className="querybar__arrow">)→</span>
        <Select label="结果" value={qy} onChange={setQy} options={varNames} />
        <select className="qselect" value={qkind} onChange={(e) => setQkind(e.target.value as typeof qkind)} aria-label="查询类型">
          <option value="effect">效应 effect</option>
          <option value="identify">可识别? identify</option>
          <option value="counterfactual">反事实 counterfactual</option>
        </select>
        <button className="btn" onClick={submit} disabled={busy}>
          {busy ? '核验中…' : submitLabel}
        </button>
      </div>

      {error ? (
        <div className="errbox" role="alert">
          <p className="errbox__msg">{error}</p>
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
