import { useState } from 'react'
import { getApiKey, setApiKey } from '../api'
import { say, useLang, type Words } from '../lib/language'

// A sentence with an emphasised phrase inside it is three parts, not one
// string with markup in it: the emphasis lands on a different word in a
// different language, and a `<b>` written into the text would fix it where
// the first author put it.
const SAYS = {
  title: { zh: 'Anthropic API Key（可选）', en: 'Anthropic API key (optional)' },
  whyHead: { zh: '默认 Ask / 解读走', en: 'Ask and the plain-language reading go through a ' },
  whyLead: { zh: '本机代理', en: 'local proxy' },
  whyTail: {
    zh: '，无需 key。若代理没在跑、或你想用自己的额度，在这里填一个覆盖——只存你浏览器本地，按请求发送，服务端不留存。',
    en: ' by default, so no key is needed. If the proxy is not running, or you would rather spend your own quota, put an override here — it stays in your browser, is sent per request, and is never kept on the server.',
  },
  save: { zh: '保存', en: 'Save' },
  note: {
    zh: '不用 Ask 也行——下方"现成案例"用内核直接跑，不需要 key。',
    en: 'You can skip Ask entirely — the worked examples below run straight through the kernel and need no key.',
  },
} satisfies Record<string, Words>

export function ApiKeyPanel({ onClose }: { onClose: () => void }) {
  const [value, setValue] = useState(getApiKey())
  const lang = useLang()

  function save() {
    setApiKey(value.trim())
    onClose()
  }

  return (
    <div className="keypanel" role="dialog" aria-label="Anthropic API key">
      <h4>{say(SAYS.title, lang, 'title')}</h4>
      <p>
        {say(SAYS.whyHead, lang, 'whyHead')}
        <b>{say(SAYS.whyLead, lang, 'whyLead')}</b>
        {say(SAYS.whyTail, lang, 'whyTail')}
      </p>
      <div className="keypanel__row">
        <input
          className="keyinput"
          type="password"
          placeholder="sk-ant-…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && save()}
          autoFocus
        />
        <button className="btn" onClick={save}>{say(SAYS.save, lang, 'save')}</button>
      </div>
      <p className="keypanel__note">{say(SAYS.note, lang, 'note')}</p>
    </div>
  )
}
