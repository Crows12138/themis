import { useState } from 'react'
import { fill, say, useLang, type Words } from '../lib/language'

const SAYS = {
  // The parser's own complaint goes in a slot rather than being appended:
  // where a borrowed clause sits in a sentence is a thing the two languages
  // disagree about, and a `+` puts it where this file's author reads.
  badJson: { zh: 'JSON 格式错误：{why}', en: 'That is not valid JSON: {why}' },
  region: { zh: '编辑 kernel_ast', en: 'Edit the kernel_ast' },
  toggle: { zh: '查看 / 编辑因果图 JSON（kernel_ast）', en: 'View / edit the graph JSON (kernel_ast)' },
  rerunning: { zh: '重跑中…', en: 'Re-running…' },
  rerun: { zh: '用改后的 JSON 重跑 →', en: 'Re-run with this JSON →' },
} satisfies Record<string, Words>

/** 改 json: view / edit the raw kernel_ast and re-run it. */
export function JsonEditor({ program, busy, onRun }: { program: Record<string, unknown>; busy: boolean; onRun: (prog: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(() => JSON.stringify(program, null, 2))
  const [err, setErr] = useState<string | null>(null)
  const lang = useLang()

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
      setErr(fill(SAYS.badJson, lang, { why: (e as Error).message }))
      return
    }
    setErr(null)
    onRun(parsed)
  }

  return (
    <section className="jsonedit" aria-label={say(SAYS.region, lang, 'region')}>
      <button className="jsonedit__toggle" onClick={toggle}>
        {open ? '▾' : '▸'} {say(SAYS.toggle, lang, 'toggle')}
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
            {say(busy ? SAYS.rerunning : SAYS.rerun, lang, busy ? 'rerunning' : 'rerun')}
          </button>
        </div>
      ) : null}
    </section>
  )
}
