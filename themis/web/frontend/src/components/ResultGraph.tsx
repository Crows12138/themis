import { useCallback, useEffect, useState } from 'react'
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
import { graphToProgram, programToFlow } from '../lib/graph'

type NData = { label: string; editing?: boolean; rename?: (id: string, label: string) => void }

/** A clean label for an existing variable; an input for a freshly-added one. */
function GraphNode({ id, data }: NodeProps<Node<NData>>) {
  return (
    <div className="gnode">
      <Handle type="target" position={Position.Left} className="gnode__h" />
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
      <Handle type="source" position={Position.Right} className="gnode__h" />
    </div>
  )
}

const nodeTypes = { plain: GraphNode }
const NAME_POOL = ['x', 'y', 'z', 'm', 'n', 'w', 'u', 'v', 'p', 'q', 'r', 's']
let _seq = 0

/**
 * The causal graph that produced this result — directly editable, no mode to
 * toggle. Draw a cause / latent-confounder edge, select-and-delete, or add a
 * variable, then "用改后的图重跑" re-runs the kernel so you can watch the
 * verdict change when you, say, delete an LLM-proposed edge or add a confounder.
 * "还原原图" re-runs the original program.
 *
 * Existing variables stay read-only labels (renaming one the query references
 * would break it — do that in the JSON editor); newly-added nodes get an input
 * to name them. Selection is read off React Flow's own `selected` flags, never
 * an onSelectionChange callback (which loops setState in a controlled graph).
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

  const rename = useCallback(
    (id: string, label: string) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n))),
    [setNodes],
  )

  // Seed (or re-seed) the canvas from the program. Runs on mount and whenever
  // the displayed program changes (after a re-run), so a re-run snaps the
  // canvas back to the structure that produced the new verdict.
  const seed = useCallback(() => {
    const { nodes: sn, edges: se } = programToFlow(program)
    setNodes(sn.map((n) => ({ ...n, type: 'plain', data: { label: (n.data as { label: string }).label, editing: false, rename } })))
    setEdges(se)
  }, [program, rename, setNodes, setEdges])

  useEffect(() => { seed() }, [seed])

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

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source === c.target) return
      const bidir = edgeType === 'bidirected'
      setEdges((es) =>
        addEdge(
          {
            ...c,
            id: `e${++_seq}`,
            data: { kind: bidir ? 'bidirected' : 'cause' },
            style: bidir
              ? { stroke: '#a23b2c', strokeWidth: 1.6, strokeDasharray: '5 4' }
              : { stroke: '#5a6a6f', strokeWidth: 1.6 },
            markerEnd: { type: MarkerType.ArrowClosed, color: bidir ? '#a23b2c' : '#5a6a6f' },
            markerStart: bidir ? { type: MarkerType.ArrowClosed, color: '#a23b2c' } : undefined,
          },
          es,
        ),
      )
    },
    [edgeType, setEdges],
  )

  function deleteSelected() {
    const dropNodes = new Set(nodes.filter((n) => n.selected).map((n) => n.id))
    setEdges((es) => es.filter((e) => !e.selected && !dropNodes.has(e.source) && !dropNodes.has(e.target)))
    setNodes((ns) => ns.filter((n) => !n.selected))
  }

  const selCount = nodes.filter((n) => n.selected).length + edges.filter((e) => e.selected).length

  return (
    <div className="dagview">
      <div className="dagview__head">
        <span className="dagview__cap">因果图 · 可改</span>
        <span className="dagview__tip">从变量右侧的点拖到另一个变量画边 · 选中边/点后删除 · 改完点「重跑」看判决怎么变</span>
      </div>

      <div className="dagview__bar">
        <button className="btn btn--ghost" onClick={addVariable}>＋ 加变量</button>
        <div className="seg">
          <button className={`seg__btn ${edgeType === 'cause' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('cause')}>因果 →</button>
          <button className={`seg__btn ${edgeType === 'bidirected' ? 'seg__btn--on' : ''}`} onClick={() => setEdgeType('bidirected')}>潜混杂 ↔</button>
        </div>
        <button className="btn btn--ghost" onClick={deleteSelected} disabled={selCount === 0}>
          删除选中{selCount ? `（${selCount}）` : ''}
        </button>
        <span className="dagview__spacer" />
        <button className="btn btn--ghost" onClick={() => onRerun(original)} disabled={busy} title="回到最初的因果图重跑">还原原图</button>
        <button className="btn" onClick={() => onRerun(graphToProgram(program, nodes, edges))} disabled={busy}>
          {busy ? '重跑中…' : '用改后的图重跑 →'}
        </button>
      </div>

      <div className="dagview__canvas dagview__canvas--edit">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          zoomOnScroll={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={18} color="var(--line-soft)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  )
}
