import { useState } from 'react'
import { getApiKey } from './api'
import { ApiKeyPanel } from './components/ApiKeyPanel'
import { AskWorkspace } from './components/AskWorkspace'
import { BuildWorkspace } from './components/BuildWorkspace'
import { EstimateWorkspace } from './components/EstimateWorkspace'

type Workspace = 'ask' | 'build' | 'estimate'

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace>('ask')
  const [showKey, setShowKey] = useState(false)
  const [hasKey, setHasKey] = useState(!!getApiKey())

  return (
    <div className="app">
      <header className="masthead">
        <a className="wordmark" href="/">
          <span className="wordmark__glyph" aria-hidden>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M12 3v18M6 7h12M8 17a4 3 0 0 0 8 0" />
            </svg>
          </span>
          <span>
            <span className="wordmark__name">Themis</span>
            <span className="wordmark__tag">因果验证器</span>
          </span>
        </a>

        <nav className="nav" aria-label="工作区">
          <button className="nav__item" aria-current={workspace === 'ask'} onClick={() => setWorkspace('ask')}>
            问一问
          </button>
          <button className="nav__item" aria-current={workspace === 'build'} onClick={() => setWorkspace('build')}>
            建因果图
          </button>
          <button className="nav__item" aria-current={workspace === 'estimate'} onClick={() => setWorkspace('estimate')}>
            数据估计
          </button>
        </nav>

        <button className="keybtn" onClick={() => setShowKey((v) => !v)}>
          <span className={`keybtn__dot ${hasKey ? 'keybtn__dot--on' : ''}`} aria-hidden />
          API Key
        </button>
      </header>

      {showKey ? (
        <ApiKeyPanel
          onClose={() => {
            setShowKey(false)
            setHasKey(!!getApiKey())
          }}
        />
      ) : null}

      <main className={`stage ${workspace !== 'ask' ? 'stage--wide' : ''}`}>
        {workspace === 'ask' ? (
          <AskWorkspace onNeedKey={() => setShowKey(true)} />
        ) : workspace === 'build' ? (
          <BuildWorkspace />
        ) : (
          <EstimateWorkspace />
        )}
      </main>

      <footer className="footer">
        <span>Themis · 本地因果验证器 · 识别 + 缺口诊断 + 数据估计(themis.run / estimate)</span>
        <span className="footer__legend">
          <span><i className="footer__dot" style={{ background: 'var(--tier-point)' }} /> 点</span>
          <span><i className="footer__dot" style={{ background: 'var(--tier-interval)' }} /> 区间</span>
          <span><i className="footer__dot" style={{ background: 'var(--tier-none)' }} /> 无</span>
        </span>
      </footer>
    </div>
  )
}
