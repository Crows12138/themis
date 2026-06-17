import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { programToBuilder } from '../lib/graph'

type VarData = { label: string; rename: (id: string, label: string) => void }

const NAME_POOL = ['x', 'y', 'z', 'm', 'n', 'w', 'u', 'v', 'p', 'q', 'r', 's']

function VariableNode({ id, data }: NodeProps<Node<VarData>>) {
  return (
    <div className="vnode">
      <Handle type="target" position={Position.Left} className="vnode__handle" />
      <input
        className="vnode__input nodrag"
        value={data.label}
        spellCheck={false}
        onChange={(e) => data.rename(id, e.target.value.replace(/[^a-zA-Z0-9_]/g, '_'))}
        aria-label="变量名"
      />
      <Handle type="source" position={Position.Right} className="vnode__handle" />
    </div>
  )
}

const nodeTypes = { variable: VariableNode }

function atom(pred: string) {
  return { predicate: pred, args: [{ type: 'const', name: 'me' }] }
}

let _seq = 0
const nextId = () => `dag${++_seq}`

export interface DagBuilderProps {
  submitLabel: string
  onSubmit: (program: Record<string, unknown>) => void
  busy?: boolean
  banner?: ReactNode
  intro?: ReactNode
  /** Carry an existing graph into the canvas (from a result handoff) instead of
   *  starting blank — nodes, edges and the query are pre-filled. */
  initialProgram?: Record<string, unknown>
}

export function DagBuilder({ submitLabel, onSubmit, busy, banner, intro, initialProgram }: DagBuilderProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<VarData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [edgeType, setEdgeType] = useState<'cause' | 'bidirected'>('cause')
  const [qx, setQx] = useState('')
  const [qy, setQy] = useState('')
  const [qkind, setQkind] = useState<'effect' | 'identify' | 'counterfactual'>('effect')
  const [error, setError] = useState<string | null>(null)

  const rename = useCallback(
    (id: string, label: string) => setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n))),
    [setNodes],
  )

  // Hydrate once from a handed-off program (the workspace remounts on each
  // handoff, so a mount-time fill is exactly one fresh seed).
  const hydrated = useRef(false)
  useEffect(() => {
    if (hydrated.current || !initialProgram) return
    hydrated.current = true
    const b = programToBuilder(initialProgram)
    if (b.nodes.length < 1) return
    setNodes(b.nodes.map((n) => ({
      id: n.id,
      type: 'variable',
      position: n.position,
      data: { label: n.label, rename },
      // seed a size so the hydrated edges anchor before React Flow measures
      initialWidth: Math.max(96, n.label.length * 8.5 + 44),
      initialHeight: 38,
    } as Node<VarData>)))
    setEdges(
      b.edges.map((e, i) => {
        const bidir = e.kind === 'bidirected'
        return {
          id: `seed-${i}`,
          source: e.source,
          target: e.target,
          data: { kind: e.kind },
          style: bidir ? { stroke: '#a23b2c', strokeWidth: 1.6, strokeDasharray: '5 4' } : { stroke: '#5a6a6f', strokeWidth: 1.6 },
          markerEnd: bidir ? undefined : { type: MarkerType.ArrowClosed, color: '#5a6a6f' },
          markerStart: bidir ? { type: MarkerType.ArrowClosed, color: '#a23b2c' } : undefined,
        } as Edge
      }),
    )
    setQx(b.qx)
    setQy(b.qy)
    setQkind(b.qkind)
  }, [initialProgram, rename, setNodes, setEdges])

  const addVariable = useCallback(() => {
    setNodes((ns) => {
      const used = new Set(ns.map((n) => n.data.label))
      const name = NAME_POOL.find((c) => !used.has(c)) ?? `v${ns.length + 1}`
      return [
        ...ns,
        {
          id: nextId(),
          type: 'variable',
          position: { x: 60 + (ns.length % 4) * 210, y: 50 + Math.floor(ns.length / 4) * 130 },
          data: { label: name, rename },
        } as Node<VarData>,
      ]
    })
  }, [rename, setNodes])

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source === c.target) return
      const bidir = edgeType === 'bidirected'
      setEdges((es) =>
        addEdge(
          {
            ...c,
            id: `${c.source}-${bidir ? '↔' : '→'}-${c.target}-${es.length}`,
            data: { kind: bidir ? 'bidirected' : 'cause' },
            style: bidir ? { stroke: '#a23b2c', strokeWidth: 1.6, strokeDasharray: '5 4' } : { stroke: '#5a6a6f', strokeWidth: 1.6 },
            markerEnd: bidir ? undefined : { type: MarkerType.ArrowClosed, color: '#5a6a6f' },
            markerStart: bidir ? { type: MarkerType.ArrowClosed, color: '#a23b2c' } : undefined,
          },
          es,
        ),
      )
    },
    [edgeType, setEdges],
  )

  const labelOf = useMemo(() => {
    const map = new Map(nodes.map((n) => [n.id, n.data.label]))
    return (id: string) => map.get(id) ?? id
  }, [nodes])

  const varNames = useMemo(() => nodes.map((n) => n.data.label), [nodes])

  function serialize(): Record<string, unknown> | string {
    const names = nodes.map((n) => n.data.label.trim())
    if (names.length < 2) return '至少需要两个变量'
    if (new Set(names).size !== names.length) return '变量名有重复——每个变量名要唯一'
    if (names.some((n) => !n)) return '有变量名是空的'
    if (!qx || !qy) return '请在下方选择「干预 X」和「结果 Y」'
    if (qx === qy) return '干预和结果不能是同一个变量'

    const statements: Record<string, unknown>[] = names.map((n) => ({ kind: 'variable', predicate: n, domain: [true, false] }))
    for (const e of edges) {
      const a = labelOf(e.source!)
      const b = labelOf(e.target!)
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

      <div className="build__toolbar">
        <button className="btn" onClick={addVariable}>＋ 加变量</button>
        <div className="seg">
          <button className={`seg__btn ${edgeType === 'cause' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('cause')}>因果 →</button>
          <button className={`seg__btn ${edgeType === 'bidirected' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('bidirected')}>潜混杂 ↔</button>
        </div>
        <span className="build__tip">
          {edgeType === 'cause'
            ? '从一个变量拖到另一个画边 ＝ 实线箭头：先拖的是「因」、后接的是「果」'
            : '从一个变量拖到另一个画边 ＝ 虚线双箭头：两者有未测到的共同原因（混杂，无方向）'}
        </span>
        {nodes.length > 0 ? (
          <button className="btn btn--ghost" onClick={() => { setNodes([]); setEdges([]); setQx(''); setQy('') }}>清空</button>
        ) : null}
      </div>

      {banner}

      <div className="canvas">
        {nodes.length === 0 ? (
          <div className="canvas__empty">
            <p>空画布</p>
            <button className="linklike" onClick={addVariable}>加第一个变量</button>
          </div>
        ) : null}
        <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }}>
          <Background gap={20} color="var(--line)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

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
