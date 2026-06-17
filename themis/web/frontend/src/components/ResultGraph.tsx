import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  ConnectionMode,
  Handle,
  Position,
  MarkerType,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  type OnConnectStart,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { graphToProgram, programToFlow, reaches } from '../lib/graph'
import { ButtonEdge, EdgeHoverContext, FloatingConnectionLine } from './ButtonEdge'

type NData = { label: string; editing?: boolean; rename?: (id: string, label: string) => void }

/** A variable node: read-only label (or an input for a freshly-added one),
 *  with a delete "×" that reveals on hover / selection. */
function GraphNode({ id, data, selected }: NodeProps<Node<NData>>) {
  const { deleteElements } = useReactFlow()
  return (
    <div className={`gnode ${selected ? 'gnode--selected' : ''}`}>
      {/* Each side carries both a target and a source handle (source rendered
          last → on top, so a drag can always START from either side). With
          ConnectionMode.Loose this lets you connect any node to any node from
          whichever side is closest; direction is decided by drag order, not by
          which handle type you happened to grab. */}
      <Handle id="tl" type="target" position={Position.Left} className="gnode__h" />
      <Handle id="sl" type="source" position={Position.Left} className="gnode__h" />
      {data.editing ? (
        <input
          className="gnode__input nodrag mono"
          value={data.label}
          spellCheck={false}
          onChange={(e) => data.rename?.(id, e.target.value.replace(/[^a-zA-Z0-9_]/g, '_'))}
          aria-label="变量名"
          autoFocus
        />
      ) : (
        <span className="gnode__label mono">{data.label}</span>
      )}
      <Handle id="tr" type="target" position={Position.Right} className="gnode__h" />
      <Handle id="sr" type="source" position={Position.Right} className="gnode__h" />
      <button
        className="gnode__del nodrag nopan"
        onClick={(e) => { e.stopPropagation(); deleteElements({ nodes: [{ id }] }) }}
        title="删除这个变量"
        aria-label="删除这个变量"
      >
        ×
      </button>
    </div>
  )
}

const nodeTypes = { plain: GraphNode }
const edgeTypes = { button: ButtonEdge }
const NAME_POOL = ['x', 'y', 'z', 'm', 'n', 'w', 'u', 'v', 'p', 'q', 'r', 's']
const DELETE_KEYS = ['Backspace', 'Delete']
let _seq = 0

/**
 * The causal graph that produced this result — directly editable, no mode to
 * toggle. Draw a cause / latent-confounder edge, hover an edge or node to get a
 * "×" and delete it, or add a variable; then "用改后的图重跑" re-runs the kernel
 * so you can watch the verdict change. "还原原图" re-runs the original program.
 *
 * Existing variables stay read-only labels (renaming one the query references
 * would break the kernel — do that in the JSON editor); newly-added nodes get
 * an input to name them.
 */
export function ResultGraph({
  program,
  original,
  busy,
  onRerun,
}: {
  program: Record<string, unknown>
  original: Record<string, unknown>
  busy: boolean
  onRerun: (prog: Record<string, unknown>) => void
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [edgeType, setEdgeType] = useState<'cause' | 'bidirected'>('cause')
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  // The node a connection drag started on — the cause. Captured here because
  // React Flow normalises onConnect's source/target by handle TYPE, which would
  // otherwise let handle layout (not drag order) decide the arrow direction.
  const connectFrom = useRef<string | null>(null)

  const rename = useCallback(
    (id: string, label: string) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n))),
    [setNodes],
  )

  // Seed (or re-seed) the canvas from the program. Runs on mount and whenever
  // the displayed program changes (after a re-run), so a re-run snaps the
  // canvas back to the structure that produced the new verdict.
  const seedFrom = useCallback((prog: Record<string, unknown>) => {
    const { nodes: sn, edges: se } = programToFlow(prog)
    setNodes(sn.map((n) => ({ ...n, type: 'plain', data: { label: (n.data as { label: string }).label, editing: false, rename } })))
    setEdges(se)
  }, [rename, setNodes, setEdges])

  useEffect(() => { seedFrom(program) }, [program, seedFrom])

  // 还原原图: re-seed the canvas from the original graph immediately AND re-run
  // it. The explicit re-seed matters — if `program` is already === `original`
  // by reference (no re-run happened), onRerun alone wouldn't change state, so
  // the effect wouldn't fire and manual canvas edits would survive the restore.
  const restore = useCallback(() => {
    seedFrom(original)
    onRerun(original)
  }, [seedFrom, original, onRerun])

  const addVariable = useCallback(() => {
    setNodes((ns) => {
      const used = new Set(ns.map((n) => n.data.label))
      const name = NAME_POOL.find((c) => !used.has(c)) ?? `v${ns.length + 1}`
      return [
        ...ns,
        {
          id: `rg${++_seq}`,
          type: 'plain',
          position: { x: 40 + (ns.length % 4) * 180, y: 30 + Math.floor(ns.length / 4) * 110 },
          data: { label: name, editing: true, rename },
        } as Node<NData>,
      ]
    })
  }, [rename, setNodes])

  const onConnectStart = useCallback<OnConnectStart>((_, p) => { connectFrom.current = p.nodeId ?? null }, [])

  const onConnect = useCallback(
    (c: Connection) => {
      // Direction = drag order: the node you started on causes the one you
      // dropped on, whichever handles/sides were involved.
      const start = connectFrom.current
      connectFrom.current = null
      let from = c.source, to = c.target
      if (start && (start === c.source || start === c.target)) {
        from = start
        to = start === c.source ? c.target : c.source
      }
      if (!from || !to || from === to) return
      const bidir = edgeType === 'bidirected'
      // A causal DAG can't have a cycle: block a cause edge that would close one
      // (drawing B→A when A→…→B already exists). ↔ confounder links are fine.
      if (!bidir && reaches(edges, to, from)) {
        setNote(`画不了:已经有「${to} → … → ${from}」,再加「${from} → ${to}」会形成回路——因果图不能有环。要表达双向关联,用「潜混杂 ↔」。`)
        return
      }
      setNote(null)
      setEdges((es) =>
        addEdge(
          {
            source: from,
            target: to,
            id: `e${++_seq}`,
            type: 'button',
            data: { kind: bidir ? 'bidirected' : 'cause' },
            className: bidir ? 'rf-edge rf-edge--bidir' : 'rf-edge rf-edge--cause',
            markerEnd: { type: MarkerType.ArrowClosed, color: bidir ? '#a23b2c' : '#5a6a6f' },
            markerStart: bidir ? { type: MarkerType.ArrowClosed, color: '#a23b2c' } : undefined,
          },
          es,
        ),
      )
    },
    [edgeType, edges, setEdges],
  )

  return (
    <div className="dagview">
      <div className="dagview__bar">
        <button className="btn btn--ghost" onClick={addVariable}>＋ 加变量</button>
        <div className="seg">
          <button className={`seg__btn ${edgeType === 'cause' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('cause')}>因果 →</button>
          <button className={`seg__btn ${edgeType === 'bidirected' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('bidirected')}>潜混杂 ↔</button>
        </div>
        <span className={`edgehint ${note ? 'edgehint--warn' : ''}`}>
          {note ??
            (edgeType === 'cause'
              ? '接下来画的边 ＝ 实线箭头：先拖的是「因」、后接的是「果」'
              : '接下来画的边 ＝ 虚线双箭头：两者有未测到的共同原因（混杂，无方向）')}
        </span>
        <span className="dagview__spacer" />
        <button className="btn btn--ghost" onClick={restore} disabled={busy} title="回到最初的因果图重跑">还原原图</button>
        <button className="btn" onClick={() => onRerun(graphToProgram(program, nodes, edges))} disabled={busy}>
          {busy ? '重跑中…' : '用改后的图重跑 →'}
        </button>
      </div>

      <div className="dagview__canvas dagview__canvas--edit">
        <span className="dagview__label">因果图</span>
        <EdgeHoverContext.Provider value={hoveredEdge}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            connectionMode={ConnectionMode.Loose}
            connectionLineComponent={FloatingConnectionLine}
            onEdgeMouseEnter={(_, e) => setHoveredEdge(e.id)}
            onEdgeMouseLeave={() => setHoveredEdge(null)}
            deleteKeyCode={DELETE_KEYS}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} color="var(--line-soft)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </EdgeHoverContext.Provider>
      </div>
    </div>
  )
}
