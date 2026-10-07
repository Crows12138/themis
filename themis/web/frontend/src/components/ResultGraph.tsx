import { useEffect, useMemo, useRef, useState } from 'react'
import { graphShape, graphToProgram, programToFlow } from '../lib/graph'
import { fill, useLang, type Words } from '../lib/language'
import { CausalCanvas, type CausalCanvasHandle } from './CausalCanvas'

const SAYS = {
  label: { zh: '因果图', en: 'Causal graph' },
  restoreWhy: { zh: '回到最初的因果图重跑', en: 'Re-run the graph you started from' },
  restore: { zh: '还原原图', en: 'Restore the original' },
  rerunning: { zh: '重跑中…', en: 'Re-running…' },
  rerun: { zh: '用改后的图重跑 →', en: 'Re-run with this graph →' },
} satisfies Record<string, Words>

/**
 * The causal graph that produced this result — a thin shell over the shared
 * CausalCanvas. Editing (add a variable, draw / delete an edge) re-runs the
 * kernel via "用改后的图重跑"; "还原原图" snaps back to the original program.
 *
 * The explicit reseed(original) before onRerun matters: if `program` is already
 * === `original` by reference (canvas edited but never re-run), onRerun alone
 * wouldn't change state, so the seed effect wouldn't fire and the edits would
 * survive the restore.
 *
 * Between an edit and its re-run the page holds a graph and a result that are
 * not about each other. `onEdited` says when: the canvas no longer says what
 * the program the result was computed from says.
 */
export function ResultGraph({
  program,
  original,
  draft,
  busy,
  onRerun,
  onEdited,
}: {
  program: Record<string, unknown>
  original: Record<string, unknown>
  // A program the kernel refused to run — a revision the reader asked for
  // in a sentence, revised as asked and then refused. It goes on the canvas
  // in place of the graph the result came from, so the reader sees where
  // their words landed and can go on editing there; the result below is
  // then the old one, and says so, by the same edit-detection as any other
  // change to the canvas.
  draft?: Record<string, unknown>
  busy: boolean
  onRerun: (prog: Record<string, unknown>) => void
  onEdited?: (edited: boolean) => void
}) {
  const ref = useRef<CausalCanvasHandle>(null)
  const lang = useLang()
  const computedFrom = useMemo(() => {
    const seeded = programToFlow(program)
    return graphShape(seeded.nodes, seeded.edges)
  }, [program])
  const [shape, setShape] = useState<string | null>(null)
  const edited = shape !== null && shape !== computedFrom
  useEffect(() => { onEdited?.(edited) }, [edited, onEdited])
  useEffect(() => { if (draft) ref.current?.reseed(draft) }, [draft])
  return (
    <div className="dagview">
      <CausalCanvas
        ref={ref}
        seedProgram={program}
        label={fill(SAYS.label, lang)}
        onShapeChange={setShape}
        toolbarExtra={
          <>
            <button
              className="btn btn--ghost"
              disabled={busy}
              title={fill(SAYS.restoreWhy, lang)}
              onClick={() => { ref.current?.reseed(original); onRerun(original) }}
            >
              {fill(SAYS.restore, lang)}
            </button>
            <button
              className={edited ? 'btn btn--due' : 'btn'}
              disabled={busy}
              onClick={() => { if (ref.current) onRerun(graphToProgram(program, ref.current.getNodes(), ref.current.getEdges(), lang)) }}
            >
              {fill(busy ? SAYS.rerunning : SAYS.rerun, lang)}
            </button>
          </>
        }
      />
    </div>
  )
}
