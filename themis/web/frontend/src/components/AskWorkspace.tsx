import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ask, fetchExamples, getApiKey, KernelError, runProgram } from '../api'
import type { Envelope, ExampleItem, QueryResult } from '../types'
import { ResultView, type ResultPayload } from './ResultView'

export function AskWorkspace({ onNeedKey }: { onNeedKey: () => void }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState<false | 'ask' | string>(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<{ title: string; msg: string; needKey?: boolean } | null>(null)
  const [examples, setExamples] = useState<ExampleItem[]>([])
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    fetchExamples().then((all) => setExamples(all.filter((e) => e.nl_input)))
  }, [])

  const first = (env: Envelope): QueryResult | null => env.results?.[0] ?? null

  async function submitAsk() {
    const nl = q.trim()
    if (!nl || busy) return
    setBusy('ask')
    setError(null)
    try {
      const res = await ask(nl, getApiKey())
      const r = first(res.envelope)
      if (r) setPayload({ asked: nl, result: r, reply: res.reply, program: res.kernel_ast })
    } catch (e) {
      const ke = e as KernelError
      setError({
        title:
          ke.stage === 'nl_to_kernel_ast' ? '翻译阶段失败' : ke.stage === 'themis_run' ? '内核拒绝了这个图' : ke.stage === 'render_reply' ? '渲染阶段失败' : '出错了',
        msg: ke.message,
        needKey: /key/i.test(ke.message),
      })
    } finally {
      setBusy(false)
    }
  }

  async function runExample(ex: ExampleItem) {
    if (busy) return
    setBusy(ex.name)
    setError(null)
    try {
      const r = first(await runProgram(ex.program))
      if (r) setPayload({ asked: ex.nl_input ?? ex.name, result: r, program: ex.program })
    } catch (e) {
      setError({ title: '内核出错', msg: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  function autosize(e: FormEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, window.innerHeight * 0.4) + 'px'
    setQ(el.value)
  }

  if (payload) {
    return (
      <ResultView
        payload={payload}
        onReset={() => {
          setPayload(null)
          setError(null)
          setQ('')
        }}
      />
    )
  }

  return (
    <div className="landing">
      <div className="landing__main">
      <div className="intro">
        <p className="intro__eyebrow">不替你编数字</p>
        <h1 className="intro__title">
          问一个因果问题。<br />
          得到一个<em>诚实的判决</em>,而不是一个编的数。
        </h1>
        <p className="intro__lede">
          Themis 不是聊天机器人。它先判断你这个因果问题<strong>能不能算</strong>、<strong>还缺什么数据</strong>、诚实的答案到底是一个点、一个区间、还是<strong>什么都给不了</strong>——然后才回答。
        </p>
      </div>

      <div className="ask">
        <div className="ask__field">
          <textarea
            ref={taRef}
            className="ask__input"
            rows={1}
            placeholder="问一个因果问题…例如「久坐会让人少活几年?」"
            value={q}
            onInput={autosize}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitAsk()
            }}
          />
          <button className="ask__send" onClick={submitAsk} disabled={busy === 'ask' || !q.trim()} aria-label="提问">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </div>
        <div className="ask__meta">
          <span className="ask__hint">
            <kbd>⌘</kbd> + <kbd>Enter</kbd> 发送 · Ask 默认走本机代理,无需 key
          </span>
        </div>
      </div>

      {examples.length > 0 ? (
        <div className="examples">
          <p className="examples__label">现成案例 · 用内核直接跑,不需要 key</p>
          <div className="chips">
            {examples.slice(0, 7).map((ex) => (
              <button key={ex.name} className="chip" onClick={() => runExample(ex)} disabled={busy === ex.name} title={ex.nl_input ?? ex.name}>
                {busy === ex.name ? '运行中…' : ex.nl_input}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {busy === 'ask' ? (
        <div className="loading">
          <span className="loading__pulse" aria-hidden>
            <span /><span /><span />
          </span>
          正在把问题落成因果图、交给内核核验…
        </div>
      ) : null}

      {error ? (
        <div className="errbox" role="alert">
          <p className="errbox__title">{error.title}</p>
          <p className="errbox__msg">{error.msg}</p>
          {error.needKey ? (
            <p className="errbox__hint">
              <button className="linklike" onClick={onNeedKey}>填入 API Key</button>,或直接点上面的现成案例。
            </p>
          ) : null}
        </div>
      ) : null}
      </div>

      <aside className="sidepanel">
        <p className="sidepanel__cap">答案有三档</p>
        <div className="sidepanel__list">
          <div className="tierrow tierrow--point">
            <span className="tierrow__key">点</span>
            <span className="tierrow__gloss">能算出一个具体数字——补齐数据即可。</span>
          </div>
          <div className="tierrow tierrow--interval">
            <span className="tierrow__key">区间</span>
            <span className="tierrow__gloss">给不了确切数字,但能给一个诚实的范围。</span>
          </div>
          <div className="tierrow tierrow--none">
            <span className="tierrow__key">无</span>
            <span className="tierrow__gloss">光凭图和数据给不了,需要额外假设。</span>
          </div>
        </div>
        <p className="sidepanel__foot">Themis 永远先告诉你答案属于哪一档,而不是硬塞一个编出来的数。</p>
      </aside>
    </div>
  )
}
