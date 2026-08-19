import { useState } from 'react'
import { getApiKey, setApiKey } from '../api'

export function ApiKeyPanel({ onClose }: { onClose: () => void }) {
  const [value, setValue] = useState(getApiKey())

  function save() {
    setApiKey(value.trim())
    onClose()
  }

  return (
    <div className="keypanel" role="dialog" aria-label="Anthropic API key">
      <h4>Anthropic API Key（可选）</h4>
      <p>
        默认 Ask / 解读走<b>本机代理</b>，无需 key。若代理没在跑、或你想用自己的额度，在这里填一个覆盖——只存你浏览器本地，按请求发送，服务端不留存。
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
        <button className="btn" onClick={save}>保存</button>
      </div>
      <p className="keypanel__note">不用 Ask 也行——下方"现成案例"用内核直接跑，不需要 key。</p>
    </div>
  )
}
