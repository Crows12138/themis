import { ReactFlow, Background, Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { programToFlow } from '../lib/graph'

function PlainNode({ data }: NodeProps<Node<{ label: string }>>) {
  return (
    <div className="gnode">
      <Handle type="target" position={Position.Left} className="gnode__h" isConnectable={false} />
      <span className="gnode__label mono">{data.label}</span>
      <Handle type="source" position={Position.Right} className="gnode__h" isConnectable={false} />
    </div>
  )
}

const nodeTypes = { plain: PlainNode }

/** Read-only causal-graph view of the program that produced this result. */
export function DagView({ program }: { program?: Record<string, unknown> }) {
  const { nodes, edges } = programToFlow(program)
  if (nodes.length === 0) return null
  return (
    <div className="dagview">
      <span className="dagview__cap">因果图</span>
      <div className="dagview__canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          zoomOnScroll={false}
          panOnDrag={false}
        >
          <Background gap={18} color="var(--line-soft)" />
        </ReactFlow>
      </div>
    </div>
  )
}
