import { useRef } from 'react'
import { graphToProgram } from '../lib/graph'
import { CausalCanvas, type CausalCanvasHandle } from './CausalCanvas'

/**
 * The causal graph that produced this result — a thin shell over the shared
 * CausalCanvas. Editing (add a variable, draw / delete an edge) re-runs the
 * kernel via "用改后的图重跑"; "还原原图" snaps back to the original program.
 *
 * The explicit reseed(original) before onRerun matters: if `program` is already
 * === `original` by reference (canvas edited but never re-run), onRerun alone
 * wouldn't change state, so the seed effect wouldn't fire and the edits would
 * survive the restore.
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
  const ref = useRef<CausalCanvasHandle>(null)
  return (
    <div className="dagview">
      <CausalCanvas
        ref={ref}
        seedProgram={program}
        label="因果图"
        toolbarExtra={
          <>
            <button
              className="btn btn--ghost"
              disabled={busy}
              title="回到最初的因果图重跑"
              onClick={() => { ref.current?.reseed(original); onRerun(original) }}
            >
              还原原图
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => { if (ref.current) onRerun(graphToProgram(program, ref.current.getNodes(), ref.current.getEdges())) }}
            >
              {busy ? '重跑中…' : '用改后的图重跑 →'}
            </button>
          </>
        }
      />
    </div>
  )
}
