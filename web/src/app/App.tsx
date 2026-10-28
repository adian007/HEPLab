import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { ArrowRight, ArrowUpRight, Check, Copy, Menu, Moon, Search, Sun, X } from 'lucide-react'
import { brand, repoFile } from '../brand'
import {
  architecture, capabilities, docs, fallbackRoadmap, fallbackStack, limits, maturityScale,
  quickstart, workflow, type Maturity,
} from '../content'
import { useRemote, type Overview } from '../lib/api'
import { Wordmark } from '../components/Logo'
import { TrackLab } from '../components/TrackLab'
import { EvidenceFigure } from '../features/EvidenceFigure'

const sections = [
  { id: 'simulator', label: 'Simulator' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'quickstart', label: 'Get started' },
  { id: 'docs', label: 'Docs' },
  { id: 'roadmap', label: 'Roadmap' },
]

type Theme = 'light' | 'dark'

function storedTheme(): Theme | null {
  try { const v = localStorage.getItem('theme'); return v === 'light' || v === 'dark' ? v : null } catch { return null }
}

function useTheme() {
  const system = (): Theme => window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? system())
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])
  const toggle = () => setTheme(current => {
    const next = current === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem('theme', next) } catch { /* private mode */ }
    return next
  })
  return [theme, toggle] as const
}

function useActiveSection() {
  const [active, setActive] = useState('')
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible[0]) setActive(visible[0].target.id)
    }, { rootMargin: '-45% 0px -50% 0px' })
    sections.forEach(s => { const el = document.getElementById(s.id); if (el) observer.observe(el) })
    return () => observer.disconnect()
  }, [])
  return active
}

export default function App() {
  const overview = useRemote<Overview>('/api/v1/project/overview')
  const live = overview.state === 'ready' ? overview.data : null
  const [theme, toggleTheme] = useTheme()
  const active = useActiveSection()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    document.body.style.overflow = menuOpen ? 'hidden' : ''
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="topbar">
      <div className="container topbar-inner">
        <a href="#top" className="brand-link" aria-label={`${brand.name} home`}><Wordmark name={brand.name}/></a>
        <nav id="site-nav" className={`topnav ${menuOpen ? 'open' : ''}`} aria-label="Sections">
          {sections.map(s => <a key={s.id} href={`#${s.id}`} className={active === s.id ? 'active' : ''} onClick={() => setMenuOpen(false)}>{s.label}</a>)}
        </nav>
        <div className="topbar-actions">
          <button className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}</button>
          <a className="icon-button" href={brand.repository} target="_blank" rel="noreferrer" aria-label="Source on GitHub"><GithubIcon/></a>
          <button className="icon-button menu-toggle" onClick={() => setMenuOpen(o => !o)} aria-controls="site-nav" aria-expanded={menuOpen} aria-label={menuOpen ? 'Close menu' : 'Open menu'}>{menuOpen ? <X size={18}/> : <Menu size={18}/>}</button>
        </div>
      </div>
    </header>

    <main id="main">
      <Hero live={live} apiState={overview.state}/>

      <section id="simulator" className="section">
        <div className="container">
          <SectionHead kicker="01 · Event display" title="Momentum is measured as a curve." lead="Charged particles bend in the detector's magnetic field. The sagitta — the depth of that bend across the tracker — is how momentum gets measured. Drag the controls and watch it change."/>
          <TrackLab/>
        </div>
      </section>

      <section id="capabilities" className="section">
        <div className="container">
          <SectionHead kicker="02 · Capabilities" title="What works today — and how mature it is." lead="Every capability carries its maturity, so a working software path is never mistaken for a validated physics model."/>
          <MaturityLegend/>
          <div className="capability-grid">
            {capabilities.map(c => <article className="card capability" key={c.id}>
              <MaturityMeter status={c.status}/>
              <h3>{c.name}</h3>
              <p>{c.summary}</p>
              <ul>{c.includes.map(item => <li key={item}><Check size={14}/>{item}</li>)}</ul>
              <a className="text-link" href={repoFile(c.href)} target="_blank" rel="noreferrer">Implementation notes <ArrowUpRight size={14}/></a>
            </article>)}
          </div>
          <ol className="workflow">
            {workflow.map((w, i) => <li key={w.step}><span className="workflow-index">{String(i + 1).padStart(2, '0')}</span><b>{w.step}</b><p>{w.detail}</p><code>{w.meta}</code></li>)}
          </ol>
        </div>
      </section>

      <section id="evidence" className="section section-alt">
        <div className="container">
          <SectionHead kicker="03 · Evidence" title="Results you can check." lead="Validation data is served from the repository's recorded references, with the acceptance gate fixed before the fit."/>
          <EvidenceFigure/>
        </div>
      </section>

      <section id="architecture" className="section">
        <div className="container">
          <SectionHead kicker="04 · Architecture" title="How the pieces fit." lead="Interfaces, services and compute engines are separate layers. This website only reads public project summaries — your simulations and data stay on your machine."/>
          <div className="arch">
            {architecture.map(layer => <div className="arch-lane" key={layer.lane}>
              <span className="mono-label">{layer.lane}</span>
              <div className="arch-nodes">{layer.nodes.map(n => <div key={n.name} className={`arch-node ${'planned' in n && n.planned ? 'planned' : ''}`}><b>{n.name}</b><small>{n.note}</small></div>)}</div>
            </div>)}
          </div>
          <div className="stack-list">
            {(live?.stack ?? fallbackStack).map(s => <div key={s.name}><b>{s.name}</b><span>{s.role}</span></div>)}
          </div>
        </div>
      </section>

      <section id="quickstart" className="section section-alt">
        <div className="container quickstart-layout">
          <SectionHead kicker="05 · Get started" title="Run it on your machine." lead={`Python 3.12 or newer. The command-line tool is \`${brand.cli}\`. PYTHIA8 + DELPHES are optional and need Linux or WSL.`}/>
          <Quickstart/>
        </div>
      </section>

      <section id="docs" className="section">
        <div className="container">
          <SectionHead kicker="06 · Documentation" title="The handbook is the source of truth." lead="This site orients you. Requirements, algorithms and validation records live with the code."/>
          <DocsSearch/>
        </div>
      </section>

      <section id="roadmap" className="section section-alt">
        <div className="container">
          <SectionHead kicker="07 · Limits & roadmap" title="Known limits and what comes next." lead="Physics software should make its validity domain visible. Here's what is incomplete, and what comes next."/>
          <div className="limits">
            {limits.map(l => <article className="card limit" key={l.area}>
              <div className="limit-head"><h3>{l.area}</h3><span className="tag">{l.state}</span></div>
              <p>{l.summary}</p>
              <p className="limit-next"><ArrowRight size={14}/> {l.next}</p>
            </article>)}
          </div>
          <ol className="roadmap">
            {(live?.roadmap ?? fallbackRoadmap).map(r => <li key={r.phase} className={r.status === 'PLANNED' ? 'planned' : ''}>
              <span className="roadmap-dot"/>
              <span className="mono-label">{r.phase}</span>
              <h3>{r.name}</h3>
              <p>{r.detail}</p>
              <span className="tag">{r.status.toLowerCase()}</span>
            </li>)}
          </ol>
        </div>
      </section>
    </main>

    <footer className="footer">
      <div className="container footer-inner">
        <div><Wordmark name={brand.name}/><p>{brand.tagline}</p></div>
        <div className="footer-meta">
          <span>v{live?.version ?? '0.1.0.dev0'} · {live?.license ?? 'Apache-2.0'}</span>
          <span>CERN Open Data is used under per-record terms and cited by DOI.</span>
          <span>Not affiliated with or endorsed by CERN or the CMS Collaboration.</span>
        </div>
      </div>
    </footer>
  </>
}

function Hero({ live, apiState }: { live: Overview | null; apiState: 'loading' | 'ready' | 'offline' }) {
  return <section id="top" className="hero">
    <div className="container hero-inner">
      <span className="status-pill"><i className={`status-dot ${apiState}`} aria-hidden="true"/>{(live?.stage ?? 'Early implementation').toLowerCase()} · open source<span className="sr-only">. {apiState === 'ready' ? 'Live project data loaded.' : apiState === 'loading' ? 'Loading project data.' : 'Project service unavailable; showing stored content.'}</span></span>
      <h1><span>LHC simulation and analysis</span><span>on your own machine.</span></h1>
      <p className="hero-lead">{brand.name} is an open-source simulator and analysis workbench for <a href="https://opendata.cern.ch" target="_blank" rel="noreferrer">CERN Open Data</a>. It is early software. Each capability below shows how far along it is, and the limits section lists what has not been validated.</p>
      <div className="hero-actions">
        <a className="button primary" href="#quickstart">Run it locally <ArrowRight size={16}/></a>
        <a className="button" href="#simulator">Try the event display</a>
      </div>
      <dl className="hero-facts">
        <div><dt>Runs</dt><dd>Locally · no account</dd></div>
        <div><dt>Data</dt><dd>CMS Open Data, by DOI</dd></div>
        <div><dt>Engines</dt><dd>Python · Rust · PYTHIA8</dd></div>
        <div><dt>License</dt><dd>{live?.license ?? 'Apache-2.0'}</dd></div>
      </dl>
    </div>
  </section>
}

function GithubIcon() {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.4-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z"/></svg>
}

function SectionHead({ kicker, title, lead }: { kicker: string; title: string; lead: string }) {
  return <header className="section-head"><span className="kicker">{kicker}</span><h2>{title}</h2><p>{lead.split('`').map((part, i) => i % 2 ? <code key={i}>{part}</code> : part)}</p></header>
}

function MaturityMeter({ status }: { status: Maturity }) {
  const entry = maturityScale.find(m => m.id === status) ?? maturityScale[0]
  return <div className="maturity" aria-label={`Maturity: ${entry.label}`}>
    <span className="maturity-bars">{[0, 1, 2].map(i => <i key={i} className={i < entry.level ? 'on' : ''}/>)}</span>
    <span>{entry.label}</span>
  </div>
}

function MaturityLegend() {
  return <div className="maturity-legend"><span className="mono-label">Maturity scale</span>
    {['Planned', 'In progress', 'Early implementation', 'Working'].map((label, i) => <span key={label} className="legend-step"><span className="maturity-bars">{[0, 1, 2].map(j => <i key={j} className={j < i ? 'on' : ''}/>)}</span>{label}</span>)}
    <span className="legend-note">None of these levels means “physics-validated”.</span>
  </div>
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1600) } catch { /* clipboard blocked */ }
  }
  return <>
    <button className="copy-button" onClick={copy} aria-label={`Copy command: ${text}`}>{copied ? <Check size={14}/> : <Copy size={14}/>}</button>
    <span className="sr-only" aria-live="polite">{copied ? 'Copied to clipboard' : ''}</span>
  </>
}

// WAI-ARIA tabs pattern: arrow keys, Home and End move between tabs.
function Quickstart() {
  const [tab, setTab] = useState(quickstart[0].id)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const index = Math.max(0, quickstart.findIndex(q => q.id === tab))
  const current = quickstart[index]
  const onKeyDown = (e: ReactKeyboardEvent) => {
    const last = quickstart.length - 1
    const next = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[e.key]
    if (next === undefined) return
    e.preventDefault()
    setTab(quickstart[next].id)
    tabs.current[next]?.focus()
  }
  return <div className="terminal">
    <div className="terminal-tabs" role="tablist" aria-label="Install and run" onKeyDown={onKeyDown}>
      {quickstart.map((q, i) => <button key={q.id} ref={el => { tabs.current[i] = el }} id={`tab-${q.id}`} role="tab" aria-selected={i === index} aria-controls="quickstart-panel" tabIndex={i === index ? 0 : -1} className={i === index ? 'on' : ''} onClick={() => setTab(q.id)}>{q.label}</button>)}
    </div>
    <div className="terminal-body" role="tabpanel" id="quickstart-panel" aria-labelledby={`tab-${current.id}`} tabIndex={0}>
      {current.steps.map(step => <div className="terminal-step" key={step.cmd}>
        <span className="terminal-note"># {step.note}</span>
        <div className="terminal-line"><code><span className="prompt">$</span> {step.cmd}</code><CopyButton text={step.cmd}/></div>
      </div>)}
    </div>
  </div>
}

function DocsSearch() {
  const [query, setQuery] = useState('')
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  const visible = docs.filter(d => terms.every(t => `${d.group} ${d.title} ${d.description}`.toLowerCase().includes(t)))
  return <div className="docs">
    <label className="search">
      <Search size={16} aria-hidden="true"/>
      <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search documentation" aria-label="Search documentation" aria-describedby="doc-count"/>
    </label>
    <p id="doc-count" className="sr-only" aria-live="polite">{visible.length} of {docs.length} documents shown</p>
    <div className="doc-list">
      {visible.map(d => <a className="doc-row" key={d.path} href={repoFile(d.path)} target="_blank" rel="noreferrer">
        <span className="mono-label">{d.group}</span>
        <b>{d.title}</b>
        <span className="doc-desc">{d.description}</span>
        <ArrowUpRight size={16}/>
      </a>)}
      {visible.length === 0 && <p className="empty">No documents match “{query}”.</p>}
    </div>
    <a className="docs-cta card" href={repoFile('docs/engineering/README.md')} target="_blank" rel="noreferrer">
      <div><b>Engineering handbook</b><span>Architecture, physics algorithms, contracts and validation strategy.</span></div><ArrowUpRight size={18}/>
    </a>
  </div>
}
