import { useEffect, useRef, useState } from 'react'
import * as Plot from '@observablehq/plot'
import { ArrowUpRight, ShieldCheck } from 'lucide-react'
import { repoFile } from '../brand'
import { useRemote, type Evidence } from '../lib/api'

const CMS_FIELD_SOURCE = 'https://github.com/cms-sw/cmssw/blob/c04fa510bb587b8ee3fa171888468f80de714fa8/MagneticField/ParametrizedEngine/src/BCyl.h'

export function EvidenceFigure() {
  const remote = useRemote<Evidence>('/api/v1/project/evidence')
  const host = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)

  useEffect(() => {
    if (!host.current) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))))
    observer.observe(host.current)
    return () => observer.disconnect()
  }, [remote.state])

  useEffect(() => {
    if (!host.current || remote.state !== 'ready') return
    const { silicon } = remote.data
    const limit = silicon.acceptance.max_abs_relative_error
    const chart = Plot.plot({
      width, height: Math.round(Math.min(320, width * 0.55)),
      marginTop: 14, marginRight: 14, marginBottom: 44, marginLeft: 58,
      x: { type: 'log', label: 'Muon kinetic energy (GeV) →', grid: true, tickFormat: '~g' },
      y: { label: '↑ Held-out relative error', grid: true, domain: [-limit * 1.25, limit * 1.25], tickFormat: (v: number) => `${(v * 100).toFixed(1)}%` },
      marks: [
        Plot.ruleY([-limit, limit], { className: 'plot-gate', strokeDasharray: '4,4' }),
        Plot.ruleY([0], { className: 'plot-zero' }),
        Plot.dot(silicon.heldout_errors, {
          x: 'energy_gev', y: 'relative_error', r: 4, className: 'plot-point',
          title: (d: { energy_gev: number; relative_error: number; row: number }) =>
            `PDG row ${d.row}\n${d.energy_gev} GeV\n${(d.relative_error * 100).toFixed(3)}%`,
        }),
      ],
      style: { background: 'transparent', fontFamily: '"JetBrains Mono Variable", ui-monospace, monospace', fontSize: '10.5px' },
      ariaLabel: 'Held-out relative errors for the muon ionization model in silicon against kinetic energy. Dashed lines mark the acceptance limit.',
    })
    host.current.replaceChildren(chart)
    return () => chart.remove()
  }, [remote, width])

  if (remote.state !== 'ready') {
    return <div className="evidence-offline">
      <ShieldCheck size={20}/>
      <div>
        <b>{remote.state === 'loading' ? 'Loading recorded validation evidence…' : 'Live evidence needs the local service.'}</b>
        <p>Run <code>heplab gui</code> to load the held-out silicon fit and CMS field regression here, or read the recorded results in the repository.</p>
        <a className="text-link" href={repoFile('docs/engineering/geometry-calibration.md')} target="_blank" rel="noreferrer">Geometry & calibration record <ArrowUpRight size={14}/></a>
      </div>
    </div>
  }

  const { silicon, cms_field: field } = remote.data
  return <div className="evidence-grid">
    <figure className="card evidence-figure">
      <figcaption className="figure-head"><span className="mono-label">FIG. 1</span><b>Muon ionization in silicon — held-out points</b></figcaption>
      <div className="plot-host" ref={host}/>
      <p className="figure-note">Each point is a PDG table value withheld from the fit. Dashed bounds mark the ±{(silicon.acceptance.max_abs_relative_error * 100).toFixed(0)}% limit chosen before fitting. Worst case: <strong>{(silicon.max_abs_relative_error * 100).toFixed(3)}%</strong> over {silicon.heldout_errors.length} points.</p>
    </figure>
    <aside className="card evidence-side">
      <span className="mono-label">SOFTWARE REFERENCE CHECK</span>
      <h3>CMS tracker field model</h3>
      <dl className="metric-list">
        <div><dt>Tracker points</dt><dd>{field.tracker_rows.toLocaleString()}</dd></div>
        <div><dt>Max vector difference</dt><dd>{(field.max_vector_error_t * 1e6).toFixed(3)} <small>μT</small></dd></div>
        <div><dt>Gate (set in advance)</dt><dd>{(field.gate_max_vector_error_t * 1e6).toFixed(0)} <small>μT</small></dd></div>
        <div><dt>Result</dt><dd className={field.passed ? 'pass' : 'warn'}>{field.passed ? 'Within gate' : 'Outside gate'}</dd></div>
      </dl>
      <div className="link-stack">
        <a href={silicon.source_url} target="_blank" rel="noreferrer">PDG silicon table <ArrowUpRight size={13}/></a>
        <a href={CMS_FIELD_SOURCE} target="_blank" rel="noreferrer">CMSSW field reference <ArrowUpRight size={13}/></a>
      </div>
      <p className="caveat">Both checks cover named reference domains. Neither establishes detector calibration or physics validation.</p>
    </aside>
  </div>
}
