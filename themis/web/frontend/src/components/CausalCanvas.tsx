import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
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
import { pathEdgeIds, programToFlow, reaches, type NodeRole } from '../lib/graph'
import { ButtonEdge, FloatingConnectionLine, PathContext } from './ButtonEdge'

type NData = { label: string; editing?: boolean; role?: NodeRole; rename?: (id: string, label: string) => void }

// Textbook structural roles, relative to the query (exposure X, outcome Y).
// Colour groups by what it means for adjustment: exposure/outcome carry the
// query, 混杂 is the thing to adjust, 中介/对撞 must NOT be conditioned for a
// total effect, 工具/他因 are auxiliary.
const ROLE_META: Record<NodeRole, { label: string; cls: string; gloss: string }> = {
  exposure: { label: '暴露', cls: 'exposure', gloss: '你问效应的处理（X）' },
  outcome: { label: '结局', cls: 'outcome', gloss: '被影响的结果（Y）' },
  confounder: { label: '混杂', cls: 'confounder', gloss: 'X、Y 的共同原因 —— 走后门要调整它' },
  mediator: { label: '中介', cls: 'mediator', gloss: '在 X→Y 路径上 —— 求总效应别调整它' },
  collider: { label: '对撞', cls: 'collider', gloss: '两个箭头相遇 —— 条件化它会引入偏倚' },
  instrument: { label: '工具', cls: 'instrument', gloss: '只经 X 影响 Y 的上游变量（工具候选，合法性需假设）' },
  causeY: { label: '他因', cls: 'causeY', gloss: 'Y 的其他原因（与处理无关）' },
}
const ROLE_ORDER: NodeRole[] = ['exposure', 'outcome', 'confounder', 'mediator', 'collider', 'instrument', 'causeY']

/** A variable node: a read-only label or an input (data.editing), tagged with
 *  its query role (干预 / 结果) when it has one, with a delete "×" that reveals
 *  on hover / selection. */
function GraphNode({ id, data, selected }: NodeProps<Node<NData>>) {
  const { deleteElements } = useReactFlow()
  return (
    <div className={`gnode ${selected ? 'gnode--selected' : ''} ${data.role ? `gnode--${ROLE_META[data.role].cls}` : ''}`}>
      {data.role ? (
        <span className={`gnode__role gnode__role--${ROLE_META[data.role].cls}`} title={ROLE_META[data.role].gloss}>
          {ROLE_META[data.role].label}
        </span>
      ) : null}
      {/* Both a target and a source handle on each side (source last → on top, so
          a drag can always START from either side). With ConnectionMode.Loose
          this lets you connect any node to any node from whichever side is
          closest; direction is decided by drag order, not by handle type. */}
      <Handle id="tl" type="target" position={Position.Left} className="gnode__h" />
      <Handle id="sl" type="source" position={Position.Left} className="gnode__h" />
      {data.editing ? (
        <input
          className="gnode__input nodrag mono"
          value={data.label}
          spellCheck={false}
          onChange={(e) => data.rename?.(id, e.target.value.replace(/[^a-zA-Z0-9_]/g, '_'))}
          aria-label="变量名"
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

export interface CausalCanvasHandle {
  getNodes(): Node<NData>[]
  getEdges(): Edge[]
  reseed(program: Record<string, unknown>): void
  clear(): void
  addVariable(): void
}

export interface CausalCanvasProps {
  /** Hydrate the canvas from a kernel_ast (nodes + cause/bidirected edges). */
  seedProgram?: Record<string, unknown>
  /** Whether seeded variables are renamable. Result graph: false (renaming a
   *  query-referenced name breaks the kernel). Build canvas: true. */
  seedEditable?: boolean
  /** Reactive variable-name list, for a parent's query dropdowns. */
  onVarsChange?: (names: string[]) => void
  /** Parent action buttons (re-run / restore, or clear) shown right-aligned in
   *  the toolbar. */
  toolbarExtra?: ReactNode
  /** A corner label drawn inside the canvas (e.g. "因果图"). */
  label?: string
  /** Shown centered over an empty canvas. */
  emptyHint?: ReactNode
  height?: number
}

/**
 * The shared editable causal-graph surface used by BOTH the result view and the
 * build / estimate canvas. Everything inside is identical — add a variable, draw
 * a cause / latent-confounder edge (direction follows drag order, a cycle is
 * refused), hover an edge or node for a "×", floating edges that fan apart when
 * parallel. The two callers differ only in the thin shell around it (re-run vs a
 * query bar), which they layer on via `toolbarExtra` and the ref.
 */
export const CausalCanvas = forwardRef<CausalCanvasHandle, CausalCanvasProps>(function CausalCanvas(
  { seedProgram, seedEditable = false, onVarsChange, toolbarExtra, label, emptyHint, height = 320 },
  ref,
) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [edgeType, setEdgeType] = useState<'cause' | 'bidirected'>('cause')
  const [note, setNote] = useState<string | null>(null)
  const connectFrom = useRef<string | null>(null)

  const rename = useCallback(
    (id: string, label2: string) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, label: label2 } } : n))),
    [setNodes],
  )

  const seedFrom = useCallback(
    (prog: Record<string, unknown>) => {
      const { nodes: sn, edges: se } = programToFlow(prog)
      setNodes(sn.map((n) => {
        const d = n.data as { label: string; role?: NodeRole }
        return { ...n, type: 'plain', data: { label: d.label, editing: seedEditable, role: d.role, rename } }
      }))
      setEdges(se)
      setNote(null)
    },
    [rename, seedEditable, setNodes, setEdges],
  )

  // (Re)seed whenever the seed program changes (e.g. after a re-run).
  useEffect(() => { if (seedProgram) seedFrom(seedProgram) }, [seedProgram, seedFrom])

  // Reactive variable names for a parent query bar — only when the name SET
  // changes, so dragging a node (which mutates positions every frame) doesn't
  // storm the parent with re-renders.
  const lastVars = useRef('')
  useEffect(() => {
    const names = nodes.map((n) => n.data.label)
    const key = names.join('')
    if (key !== lastVars.current) { lastVars.current = key; onVarsChange?.(names) }
  }, [nodes, onVarsChange])

  const addVariable = useCallback(() => {
    setNodes((ns) => {
      const used = new Set(ns.map((n) => n.data.label))
      const name = NAME_POOL.find((c) => !used.has(c)) ?? `v${ns.length + 1}`
      return [
        ...ns,
        {
          id: `cc${++_seq}`,
          type: 'plain',
          position: { x: 40 + (ns.length % 4) * 180, y: 30 + Math.floor(ns.length / 4) * 110 },
          data: { label: name, editing: true, rename },
          initialWidth: Math.max(96, name.length * 8.5 + 44),
          initialHeight: 38,
        } as Node<NData>,
      ]
    })
  }, [rename, setNodes])

  useImperativeHandle(
    ref,
    () => ({
      getNodes: () => nodes,
      getEdges: () => edges,
      reseed: (prog) => seedFrom(prog),
      clear: () => { setNodes([]); setEdges([]); setNote(null) },
      addVariable,
    }),
    [nodes, edges, seedFrom, addVariable, setNodes, setEdges],
  )

  const onConnectStart = useCallback<OnConnectStart>((_, p) => { connectFrom.current = p.nodeId ?? null }, [])

  const onConnect = useCallback(
    (c: Connection) => {
      // Direction = drag order: the node you started on causes the one you dropped on.
      const start = connectFrom.current
      connectFrom.current = null
      let from = c.source, to = c.target
      if (start && (start === c.source || start === c.target)) {
        from = start
        to = start === c.source ? c.target : c.source
      }
      if (!from || !to || from === to) return
      const bidir = edgeType === 'bidirected'
      // A causal DAG can't have a cycle: refuse a cause edge that would close one.
      if (!bidir && reaches(edges, to, from)) {
        const lbl = (id: string) => nodes.find((n) => n.id === id)?.data.label ?? id
        setNote(`画不了:已经有「${lbl(to)} → … → ${lbl(from)}」,再加「${lbl(from)} → ${lbl(to)}」会形成回路——因果图不能有环。要表达双向关联,用「潜混杂 ↔」。`)
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
    [edgeType, edges, nodes, setEdges],
  )

  // The causal path X→…→Y, recomputed live so the route the effect travels
  // thickens (and re-thickens) as you rewire the graph.
  const xId = nodes.find((n) => n.data.role === 'exposure')?.id
  const yId = nodes.find((n) => n.data.role === 'outcome')?.id
  const pathIds = useMemo(() => (xId && yId ? pathEdgeIds(edges, xId, yId) : new Set<string>()), [edges, xId, yId])
  const present = new Set(nodes.map((n) => n.data.role).filter(Boolean) as NodeRole[])
  const presentRoles = ROLE_ORDER.filter((r) => present.has(r))
  const hasProposed = edges.some((e) => (e.className ?? '').includes('rf-edge--proposed'))

  return (
    <>
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
        {toolbarExtra ? <><span className="dagview__spacer" />{toolbarExtra}</> : null}
      </div>

      <div className="dagview__canvas dagview__canvas--edit" style={{ height }}>
        {label ? <span className="dagview__label">{label}</span> : null}
        {nodes.length === 0 && emptyHint ? <div className="canvas__empty">{emptyHint}</div> : null}
        <PathContext.Provider value={pathIds}>
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
            deleteKeyCode={DELETE_KEYS}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} color="var(--line-soft)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </PathContext.Provider>
      </div>

      {presentRoles.length || pathIds.size > 0 || hasProposed ? (
        <div className="dagview__legend">
          {presentRoles.map((r) => (
            <span className="legend__item" key={r}>
              <span className={`gnode__role gnode__role--${ROLE_META[r].cls}`}>{ROLE_META[r].label}</span>
              {ROLE_META[r].gloss}
            </span>
          ))}
          {pathIds.size > 0 ? (
            <span className="legend__item"><span className="legend__path" aria-hidden />粗线 ＝ 因果路径（暴露→…→结局 的通路）；其余实线同样是因果边，只是不在这条通路上</span>
          ) : null}
          {hasProposed ? (
            <span className="legend__item"><span className="legend__q" aria-hidden>?</span>带 ? 的边 ＝ AI 提议（未验证）—— 点边选中后可 ✓ 确认（用户断言）或 × 删除</span>
          ) : null}
        </div>
      ) : null}
    </>
  )
})
