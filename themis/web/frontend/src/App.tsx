import { useState } from 'react'
import { ApiKeyPanel } from './components/ApiKeyPanel'
import { AskWorkspace } from './components/AskWorkspace'
import { BuildWorkspace } from './components/BuildWorkspace'
import { EstimateWorkspace } from './components/EstimateWorkspace'
import { ENDONYM } from './lib/kernelWords.generated'
import { chooseLang, fill, LANGS, useLang, type Words } from './lib/language'
import { useOffers } from './lib/offers'
import { TIER_META, tierMeta } from './lib/verdict'

type Workspace = 'ask' | 'build' | 'estimate'

const SAYS = {
  tag: { zh: '因果验证器', en: 'Causal verifier' },
  nav: { zh: '工作区', en: 'Workspaces' },
  // The chooser's own label is in the language being read; only the options
  // are endonyms. Telling an English reader that the other choice is
  // "Chinese" would be telling them in the language they are choosing to
  // leave, which is why the kernel keeps what each language calls itself.
  language: { zh: '语言', en: 'Language' },
  ask: { zh: '问一问', en: 'Ask' },
  build: { zh: '建因果图', en: 'Build a graph' },
  estimate: { zh: '数据估计', en: 'Estimate from data' },
  foot: {
    zh: 'Themis · 本地因果验证器 · 识别 + 缺口诊断 + 数据估计（themis.run / estimate）',
    en: 'Themis · a local causal verifier · identification + gap diagnosis + estimation from data (themis.run / estimate)',
  },
} satisfies Record<string, Words>

// The legend reads the tier table rather than restating it. It used to hold
// its own three words, and so did the side panel in AskWorkspace — three
// authors of one vocabulary, two of which had already drifted from it
// ("点" for "点估计", "能算出" for "可以算出"). One table, three readers.
const TIER_ORDER = Object.keys(TIER_META) as (keyof typeof TIER_META)[]

export default function App() {
  // What this deployment offers, and so which workspaces there are. A
  // deployment with no model behind it has no Ask: the question would go
  // nowhere, and a tab that leads nowhere is worse than one that is not
  // there. The endpoint refuses too — see themis/web/app.py — because a
  // page is not a door.
  const offers = useOffers()
  // Not state until the reader picks one. Before that it is whatever this
  // deployment leads with, which is not known until the server answers;
  // making it state would mean choosing before knowing and correcting
  // afterwards, on screen.
  const [picked, setPicked] = useState<Workspace | null>(null)
  // The API key is optional — Ask / render default to the local proxy. The panel
  // only opens on demand (an LLM call failing because the proxy is unreachable),
  // so there's no persistent key button cluttering the masthead.
  const [showKey, setShowKey] = useState(false)
  // A graph handed from a result into another workspace's canvas. Consumed by
  // the matching workspace; cleared when the user navigates by hand.
  const [pending, setPending] = useState<{ target: Workspace; program: Record<string, unknown> } | null>(null)
  const lang = useLang()

  const workspace: Workspace = picked ?? (offers?.llm ? 'ask' : 'build')

  function sendTo(target: Workspace, program: Record<string, unknown>) {
    setPending({ target, program })
    setPicked(target)
  }
  function navTo(target: Workspace) {
    setPending(null)
    setPicked(target)
  }
  const seedProgram = pending && pending.target === workspace ? pending.program : undefined

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
            <span className="wordmark__tag">{fill(SAYS.tag, lang)}</span>
          </span>
        </a>

        <nav className="nav" aria-label={fill(SAYS.nav, lang)}>
          {offers?.llm ? (
            <button className="nav__item" aria-current={workspace === 'ask'} onClick={() => navTo('ask')}>
              {fill(SAYS.ask, lang)}
            </button>
          ) : null}
          <button className="nav__item" aria-current={workspace === 'build'} onClick={() => navTo('build')}>
            {fill(SAYS.build, lang)}
          </button>
          <button className="nav__item" aria-current={workspace === 'estimate'} onClick={() => navTo('estimate')}>
            {fill(SAYS.estimate, lang)}
          </button>
        </nav>

        <div className="langs" role="group" aria-label={fill(SAYS.language, lang)}>
          {LANGS.map((one) => (
            <button
              key={one}
              className="langs__item"
              lang={one}
              aria-current={one === lang}
              onClick={() => chooseLang(one)}
            >
              {fill(ENDONYM, one)}
            </button>
          ))}
        </div>
      </header>

      {showKey ? <ApiKeyPanel onClose={() => setShowKey(false)} /> : null}

      <main className={`stage ${workspace !== 'ask' ? 'stage--wide' : ''}`}>
        {offers === null ? null : workspace === 'ask' ? (
          <AskWorkspace onNeedKey={() => setShowKey(true)} onSendTo={sendTo} />
        ) : workspace === 'build' ? (
          <BuildWorkspace initialProgram={seedProgram} onSendTo={sendTo} />
        ) : (
          <EstimateWorkspace initialProgram={seedProgram} onSendTo={sendTo} />
        )}
      </main>

      <footer className="footer">
        <span>{fill(SAYS.foot, lang)}</span>
        <span className="footer__legend">
          {TIER_ORDER.map((tier) => (
            <span key={tier}>
              <i className="footer__dot" style={{ background: `var(--tier-${tier})` }} />{' '}
              {tierMeta(tier, lang).label}
            </span>
          ))}
        </span>
      </footer>
    </div>
  )
}
