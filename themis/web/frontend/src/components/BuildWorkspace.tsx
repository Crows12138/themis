import { useState } from 'react'
import { runProgram } from '../api'
import { DagBuilder } from './DagBuilder'
import { ResultView, type ResultPayload } from './ResultView'

export function BuildWorkspace({
  initialProgram,
  onSendTo,
}: {
  initialProgram?: Record<string, unknown>
  onSendTo?: (target: 'ask' | 'build' | 'estimate', program: Record<string, unknown>) => void
} = {}) {
  const [busy, setBusy] = useState(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(program: Record<string, unknown>) {
    setBusy(true)
    setError(null)
    try {
      const env = await runProgram(program)
      const r = env.results?.[0]
      const q = (program.statements as { query?: { kind?: string } }[] | undefined)?.find((s) => s.query)?.query
      if (r) setPayload({ asked: `因果图 · ${q?.kind ?? 'effect'} 查询`, result: r, program })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (payload) return <ResultView payload={payload} onSendTo={onSendTo} onReset={() => setPayload(null)} resetLabel="← 回到画布" />

  return (
    <DagBuilder
      submitLabel="交给内核 →"
      onSubmit={run}
      busy={busy}
      initialProgram={initialProgram}
      intro={
        <div className="build__intro">
          <h2 className="build__title">画出你的因果图</h2>
          <p className="build__lede">
            加变量、拉线连成因果关系，选一个干预和结果，交给内核判断——能不能识别、还缺什么。<b>实线带箭头</b>是因果,<b>虚线双箭头</b>是潜在共因(未观测混杂)。
          </p>
        </div>
      }
      banner={error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : undefined}
    />
  )
}
