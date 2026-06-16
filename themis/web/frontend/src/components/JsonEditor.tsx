import { useState } from 'react'

/** 改 json: view / edit the raw kernel_ast and re-run it. */
export function JsonEditor({ program, busy, onRun }: { program: Record<string, unknown>; busy: boolean; onRun: (prog: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(() => JSON.stringify(program, null, 2))
  const [err, setErr] = useState<string | null>(null)

  // Reflect external program changes (clarify / earlier edits) when closed.
  function toggle() {
    if (!open) setText(JSON.stringify(program, null, 2))
    setOpen((o) => !o)
    setErr(null)
  }

  function run() {
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(text)
    } catch (e) {
      setErr('JSON 格式错误:' + (e as Error).message)
      return
    }
    setErr(null)
    onRun(parsed)
  }

  return (
    <section className="jsonedit" aria-label="编辑 kernel_ast">
      <button className="jsonedit__toggle" onClick={toggle}>
        {open ? '▾' : '▸'} 查看 / 编辑因果图 JSON（kernel_ast）
      </button>
      {open ? (
        <div className="jsonedit__body">
          <textarea
            className="jsonedit__ta mono"
            value={text}
            spellCheck={false}
            onChange={(e) => setText(e.target.value)}
          />
          {err ? <p className="jsonedit__err">{err}</p> : null}
          <button className="btn" onClick={run} disabled={busy}>
            {busy ? '重跑中…' : '用改后的 JSON 重跑 →'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
