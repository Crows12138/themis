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
      <h4>Anthropic API Key</h4>
      <p>
        Ask 模式需要它把你的问题翻成因果图、再渲染回答。只存在你浏览器本地,按请求发送,服务端不留存。
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
      <p className="keypanel__note">不用 Ask 也行——下方"现成案例"用内核直接跑,不需要 key。</p>
    </div>
  )
}
