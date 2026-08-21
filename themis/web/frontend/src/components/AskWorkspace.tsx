import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ask, errorText, fetchExamples, getApiKey, KernelError, runProgram } from '../api'
import { say, useLang, type Words } from '../lib/language'
import { TIER_META, tierMeta } from '../lib/verdict'
import type { Envelope, ExampleItem, QueryResult } from '../types'
import { ResultView, type ResultPayload } from './ResultView'

const SAYS = {
  eyebrow: { zh: '不替你编数字', en: 'It will not invent a number for you' },
  titleHead: { zh: '问一个因果问题。', en: 'Ask a causal question.' },
  titleTailHead: { zh: '得到一个', en: 'Get an ' },
  titleTailLead: { zh: '诚实的判决', en: 'honest verdict' },
  titleTailTail: { zh: '，而不是一个编的数。', en: ', not a number somebody made up.' },
  ledeHead: {
    zh: 'Themis 不是聊天机器人。它先判断你这个因果问题',
    en: 'Themis is not a chatbot. Before it answers, it works out whether your causal question ',
  },
  ledeCanIt: { zh: '能不能算', en: 'can be answered at all' },
  ledeMid1: { zh: '、', en: ', ' },
  ledeMissing: { zh: '还缺什么数据', en: 'what data is still missing' },
  ledeMid2: {
    zh: '、诚实的答案到底是一个点、一个区间、还是',
    en: ', and whether the honest answer is a point, an interval, or ',
  },
  ledeNothing: { zh: '什么都给不了', en: 'nothing at all' },
  ledeTail: { zh: '——然后才回答。', en: '.' },
  placeholder: {
    zh: '问一个因果问题…例如「久坐会让人少活几年？」',
    en: 'Ask a causal question… e.g. "does sitting all day cost you years of life?"',
  },
  send: { zh: '提问', en: 'Ask' },
  examples: { zh: '现成案例 · 用内核直接跑，不需要 key', en: 'Worked examples · run straight through the kernel, no key needed' },
  running: { zh: '运行中…', en: 'Running…' },
  thinking: { zh: '正在把问题落成因果图、交给内核核验…', en: 'Turning the question into a causal graph and handing it to the kernel…' },
  fillKey: { zh: '填入 API Key', en: 'Enter an API key' },
  orExamples: { zh: '，或直接点上面的现成案例。', en: ', or just click one of the worked examples above.' },
  tiersCap: { zh: '答案有三档', en: 'Answers come in three tiers' },
  tiersFoot: {
    zh: 'Themis 永远先告诉你答案属于哪一档，而不是硬塞一个编出来的数。',
    en: 'Themis always tells you which tier the answer is in first, rather than pushing an invented number at you.',
  },
} satisfies Record<string, Words>

// Which stage of the bridge gave up. Keyed by the stage the error carries, so
// a stage added upstream shows as its own name rather than as "something went
// wrong" — `stageFailed` is the answer for a stage nobody has worded yet.
const STAGE_SAYS = {
  nl_to_kernel_ast: { zh: '翻译阶段失败', en: 'The translation step failed' },
  themis_run: { zh: '内核拒绝了这个图', en: 'The kernel refused this graph' },
  render_reply: { zh: '渲染阶段失败', en: 'The rendering step failed' },
} satisfies Record<string, Words>

const FAILED = {
  stageFailed: { zh: '出错了', en: 'Something went wrong' },
  kernelFailed: { zh: '内核出错', en: 'The kernel errored' },
} satisfies Record<string, Words>

const TIER_ORDER = Object.keys(TIER_META) as (keyof typeof TIER_META)[]

export function AskWorkspace({
  onNeedKey,
  onSendTo,
}: {
  onNeedKey: () => void
  onSendTo?: (target: 'ask' | 'build' | 'estimate', program: Record<string, unknown>) => void
}) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState<false | 'ask' | string>(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<{ title: string; msg: string; needKey?: boolean } | null>(null)
  const [examples, setExamples] = useState<ExampleItem[]>([])
  const taRef = useRef<HTMLTextAreaElement>(null)
  const lang = useLang()

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
      const stage = ke.stage ? STAGE_SAYS[ke.stage as keyof typeof STAGE_SAYS] : undefined
      setError({
        title: say(stage ?? FAILED.stageFailed, lang, 'stageFailed'),
        msg: errorText(ke, lang),
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
      setError({ title: say(FAILED.kernelFailed, lang, 'kernelFailed'), msg: errorText(e, lang) })
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
        onSendTo={onSendTo}
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
        <p className="intro__eyebrow">{say(SAYS.eyebrow, lang, 'eyebrow')}</p>
        <h1 className="intro__title">
          {say(SAYS.titleHead, lang, 'titleHead')}<br />
          {say(SAYS.titleTailHead, lang, 'titleTailHead')}
          <em>{say(SAYS.titleTailLead, lang, 'titleTailLead')}</em>
          {say(SAYS.titleTailTail, lang, 'titleTailTail')}
        </h1>
        <p className="intro__lede">
          {say(SAYS.ledeHead, lang, 'ledeHead')}
          <strong>{say(SAYS.ledeCanIt, lang, 'ledeCanIt')}</strong>
          {say(SAYS.ledeMid1, lang, 'ledeMid1')}
          <strong>{say(SAYS.ledeMissing, lang, 'ledeMissing')}</strong>
          {say(SAYS.ledeMid2, lang, 'ledeMid2')}
          <strong>{say(SAYS.ledeNothing, lang, 'ledeNothing')}</strong>
          {say(SAYS.ledeTail, lang, 'ledeTail')}
        </p>
      </div>

      <div className="ask">
        <div className="ask__field">
          <textarea
            ref={taRef}
            className="ask__input"
            rows={1}
            placeholder={say(SAYS.placeholder, lang, 'placeholder')}
            value={q}
            onInput={autosize}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter keeps the newline (multi-line still possible).
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submitAsk()
              }
            }}
          />
          <button className="ask__send" onClick={submitAsk} disabled={busy === 'ask' || !q.trim()} aria-label={say(SAYS.send, lang, 'send')}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </div>

      {examples.length > 0 ? (
        <div className="examples">
          <p className="examples__label">{say(SAYS.examples, lang, 'examples')}</p>
          <div className="chips">
            {examples.slice(0, 7).map((ex) => (
              <button key={ex.name} className="chip" onClick={() => runExample(ex)} disabled={busy === ex.name} title={ex.nl_input ?? ex.name}>
                {busy === ex.name ? say(SAYS.running, lang, 'running') : ex.nl_input}
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
          {say(SAYS.thinking, lang, 'thinking')}
        </div>
      ) : null}

      {error ? (
        <div className="errbox" role="alert">
          <p className="errbox__title">{error.title}</p>
          <p className="errbox__msg">{error.msg}</p>
          {error.needKey ? (
            <p className="errbox__hint">
              <button className="linklike" onClick={onNeedKey}>{say(SAYS.fillKey, lang, 'fillKey')}</button>
              {say(SAYS.orExamples, lang, 'orExamples')}
            </p>
          ) : null}
        </div>
      ) : null}
      </div>

      <aside className="sidepanel">
        <p className="sidepanel__cap">{say(SAYS.tiersCap, lang, 'tiersCap')}</p>
        <div className="sidepanel__list">
          {TIER_ORDER.map((tier) => {
            const meta = tierMeta(tier, lang)
            return (
              <div className={`tierrow tierrow--${tier}`} key={tier}>
                <span className="tierrow__key">{meta.label}</span>
                <span className="tierrow__gloss">{meta.gloss}</span>
              </div>
            )
          })}
        </div>
        <p className="sidepanel__foot">{say(SAYS.tiersFoot, lang, 'tiersFoot')}</p>
      </aside>
    </div>
  )
}
