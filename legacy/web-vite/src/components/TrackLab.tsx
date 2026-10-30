import { useEffect, useMemo, useRef, useState } from 'react'
import { Dices, Minus, Plus } from 'lucide-react'
import {
  DISPLAY_PT_MIN, ECAL, LAYERS, MUON_MASS, OUTER_LAYER_R, TRACKER, minimumBiasEvent, ptResolution, sagitta, trace,
  type Point,
} from './trackPhysics'

// Illustrative transverse-plane event display. A toy minimum-bias event plus
// one muon the visitor controls, in an ideal uniform field. Physics and
// geometry sources are in ./trackPhysics.ts. This is not simulator output.

const VIEW_R = 1.62
const PROBE_PHI = 0.62

const colors = {
  axis: 'rgba(148, 170, 190, 0.10)', pixel: 'rgba(148, 190, 230, 0.45)', strip: 'rgba(148, 190, 230, 0.18)',
  ecal: 'rgba(63, 224, 192, 0.07)', ecalLine: 'rgba(63, 224, 192, 0.30)', track: 'rgba(127, 179, 255, 0.70)',
  extrapolation: 'rgba(127, 179, 255, 0.30)', hit: 'rgba(190, 215, 255, 0.9)', probe: '#ffb547',
  sagitta: '#3fe0c0', label: 'rgba(200, 214, 228, 0.6)',
}

export function TrackLab() {
  const canvas = useRef<HTMLCanvasElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const [pt, setPt] = useState(4)
  const [B, setB] = useState(3.8)
  const [q, setQ] = useState<1 | -1>(1)
  const [seed, setSeed] = useState(42)
  const [size, setSize] = useState(520)
  const [progress, setProgress] = useState(1)

  const background = useMemo(() => minimumBiasEvent(seed), [seed])
  const tracks = useMemo(() => [...background, { pt, eta: 0, phi: PROBE_PHI, q, mass: MUON_MASS, probe: true }].map(p => trace(p, B)), [background, pt, q, B])
  const probe = tracks[tracks.length - 1]
  const s = probe.outerPoint ? sagitta(probe.R, OUTER_LAYER_R) : NaN
  const resolution = ptResolution(pt, B, MUON_MASS, probe.hits.length)

  useEffect(() => {
    if (!wrap.current) return
    const observer = new ResizeObserver(([entry]) => setSize(Math.max(260, Math.floor(entry.contentRect.width))))
    observer.observe(wrap.current)
    return () => observer.disconnect()
  }, [])

  // Grow tracks outward whenever a new event is drawn.
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setProgress(1); return }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900)
      setProgress(1 - Math.pow(1 - t, 3))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [seed])

  useEffect(() => {
    const el = canvas.current
    const ctx = el?.getContext('2d')
    if (!el || !ctx) return
    const dpr = window.devicePixelRatio || 1
    el.width = size * dpr
    el.height = size * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size, size)
    const c = size / 2
    const scale = c / VIEW_R
    const X = (p: Point) => c + p[0] * scale
    const Y = (p: Point) => c - p[1] * scale
    const ring = (r: number, stroke: string, dash: number[] = []) => {
      ctx.beginPath(); ctx.setLineDash(dash); ctx.strokeStyle = stroke; ctx.lineWidth = 1
      ctx.arc(c, c, r * scale, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([])
    }
    const path = (points: Point[], count = points.length) => {
      ctx.beginPath()
      points.slice(0, count).forEach((p, i) => i ? ctx.lineTo(X(p), Y(p)) : ctx.moveTo(X(p), Y(p)))
      ctx.stroke()
    }

    ctx.strokeStyle = colors.axis; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, c); ctx.lineTo(size, c); ctx.moveTo(c, 0); ctx.lineTo(c, size); ctx.stroke()
    ctx.beginPath(); ctx.fillStyle = colors.ecal
    ctx.arc(c, c, ECAL.rOuter * scale, 0, Math.PI * 2); ctx.arc(c, c, ECAL.rInner * scale, 0, Math.PI * 2, true); ctx.fill()
    ring(ECAL.rInner, colors.ecalLine); ring(ECAL.rOuter, colors.ecalLine)
    LAYERS.forEach(l => ring(l.r, l.kind === 'pixel' ? colors.pixel : colors.strip))
    ring(TRACKER.r, colors.label, [2, 5])

    ctx.font = '500 10px "JetBrains Mono Variable", monospace'
    ctx.fillStyle = colors.label
    ctx.fillText('TRACKER', c + 6, c - TRACKER.r * scale + 13)
    ctx.fillText('ECAL BARREL', c + 6, c - ECAL.rInner * scale - 5)

    // Draw the probe last so it sits on top.
    for (const t of tracks) {
      const isProbe = !!t.particle.probe
      const count = Math.max(2, Math.floor(t.inTracker.length * progress))
      ctx.lineCap = 'round'
      ctx.strokeStyle = isProbe ? colors.probe : colors.track
      ctx.lineWidth = isProbe ? 2.6 : 1.3
      path(t.inTracker, count)
      if (progress < 1) continue
      if (t.beyond.length > 1) {
        ctx.setLineDash([3, 4])
        ctx.strokeStyle = isProbe ? colors.probe : colors.extrapolation
        ctx.lineWidth = isProbe ? 1.8 : 1
        path(t.beyond)
        ctx.setLineDash([])
      }
      ctx.fillStyle = isProbe ? colors.probe : colors.hit
      t.hits.forEach(p => { ctx.beginPath(); ctx.arc(X(p), Y(p), isProbe ? 2.4 : 1.6, 0, Math.PI * 2); ctx.fill() })
    }

    // Chord from the beamline to the outermost layer, and the sagitta.
    if (progress >= 1 && probe.outerPoint && probe.center && Number.isFinite(s) && s > 0) {
      const E = probe.outerPoint, C = probe.center
      const M: Point = [E[0] / 2, E[1] / 2]
      const d = Math.hypot(M[0] - C[0], M[1] - C[1])
      const A: Point = [C[0] + (M[0] - C[0]) / d * probe.R, C[1] + (M[1] - C[1]) / d * probe.R]
      ctx.setLineDash([4, 4]); ctx.strokeStyle = colors.sagitta; ctx.lineWidth = 1.2
      path([[0, 0], E]); ctx.setLineDash([])
      ctx.lineWidth = 2; path([M, A])
      ctx.fillStyle = colors.sagitta
      ctx.font = '600 12px "JetBrains Mono Variable", monospace'
      ctx.fillText('s', X(A) + 6, Y(A) - 4)
    }
    ctx.fillStyle = '#e9eef3'
    ctx.beginPath(); ctx.arc(c, c, 2.5, 0, Math.PI * 2); ctx.fill()

    const bar = 0.5 * scale
    ctx.strokeStyle = colors.label; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(14, size - 16); ctx.lineTo(14 + bar, size - 16); ctx.moveTo(14, size - 20); ctx.lineTo(14, size - 12); ctx.moveTo(14 + bar, size - 20); ctx.lineTo(14 + bar, size - 12); ctx.stroke()
    ctx.fillStyle = colors.label; ctx.font = '500 10px "JetBrains Mono Variable", monospace'
    ctx.fillText('0.5 m', 14 + bar + 6, size - 12)
  }, [tracks, size, progress, probe, s])

  const status = B === 0
    ? 'No field: the track is straight and its momentum cannot be measured.'
    : probe.end === 'looper' ? 'Loops inside the tracker: too little momentum to reach the outer layers.'
    : 'Reaches all barrel layers.'
  return <div className="tracklab">
    <div className="tracklab-display">
      <div className="tracklab-hud">
        <span><i className="live-dot"/> TRANSVERSE VIEW · r–φ</span>
        <span>EVENT {String(seed).padStart(5, '0')} · {background.length} TRACKS pT &gt; {DISPLAY_PT_MIN} GeV</span>
      </div>
      <div ref={wrap} className="tracklab-canvas-wrap">
        <canvas ref={canvas} style={{ width: size, height: size }} role="img" aria-describedby="tracklab-summary"
          aria-label={`Illustrative event display: ${background.length} charged pions above ${DISPLAY_PT_MIN} GeV and one muon with transverse momentum ${pt.toFixed(1)} GeV in a ${B.toFixed(1)} tesla field.`}/>
        <ul id="tracklab-summary" className="sr-only">
          {tracks.map((t, i) => <li key={i}>{t.particle.probe ? 'Muon' : 'Pion'} {t.particle.q > 0 ? 'positive' : 'negative'}, pT {t.particle.pt.toFixed(2)} GeV, η {t.particle.eta.toFixed(2)}, {t.hits.length} barrel hits, {t.end === 'barrel' ? 'leaves through the barrel' : t.end === 'endcap' ? 'leaves through an endcap' : 'loops inside the tracker'}.</li>)}
        </ul>
      </div>
      <ul className="tracklab-legend" aria-label="Legend">
        <li><i className="swatch probe"/> Muon you control (η = 0)</li>
        <li><i className="swatch track"/> Charged pions, toy minimum-bias</li>
        <li><i className="swatch dashed"/> Extrapolated beyond the tracker</li>
      </ul>
    </div>
    <div className="tracklab-panel">
      <div className="readouts">
        <div><span>Radius of curvature</span><b>{Number.isFinite(probe.R) ? probe.R.toFixed(2) : '∞'}<small> m</small></b></div>
        <div className="readout-key"><span>Sagitta over 1.08 m</span><b>{Number.isFinite(s) && probe.outerPoint ? (s * 1000).toFixed(s < 0.01 ? 2 : 1) : '—'}<small> mm</small></b></div>
        <div><span>σ(pT) / pT</span><b>{resolution && probe.outerPoint ? (resolution.total * 100).toFixed(2) : '—'}<small> %</small></b></div>
        <div><span>Barrel hits</span><b>{probe.hits.length}<small> / {LAYERS.length}</small></b></div>
        <div className="readout-wide" aria-live="polite"><span>Track status</span><b className={probe.end === 'looper' || B === 0 ? 'warn' : ''}>{status}</b></div>
      </div>
      <label className="control">
        <span><b>Muon transverse momentum</b><output>{pt < 10 ? pt.toFixed(1) : pt.toFixed(0)} GeV</output></span>
        <input type="range" min={-0.5} max={2.3} step={0.01} value={Math.log10(pt)} aria-valuetext={`${pt.toFixed(pt < 10 ? 1 : 0)} GeV`} onChange={e => setPt(Math.pow(10, Number(e.target.value)))}/>
      </label>
      <label className="control">
        <span><b>Magnetic field</b><output>{B.toFixed(1)} T</output></span>
        <input type="range" min={0} max={4} step={0.1} value={B} aria-valuetext={`${B.toFixed(1)} tesla`} onChange={e => setB(Number(e.target.value))}/>
        <small>CMS solenoid: 3.8 T</small>
      </label>
      <div className="control-row">
        <div className="segmented" role="group" aria-label="Muon charge">
          <button className={q === 1 ? 'on' : ''} onClick={() => setQ(1)} aria-pressed={q === 1}><Plus size={14}/> μ⁺</button>
          <button className={q === -1 ? 'on' : ''} onClick={() => setQ(-1)} aria-pressed={q === -1}><Minus size={14}/> μ⁻</button>
        </div>
        <button className="ghost-button" onClick={() => setSeed(v => (v * 1103515245 + 12345) % 99991)}><Dices size={15}/> New event</button>
      </div>
      <p className="tracklab-note">
        A stiffer track has a smaller sagitta, so its momentum is measured less precisely. Below about 50 GeV the
        error is dominated by multiple scattering in the tracker material; above that, by hit precision.
        Forward pions leave through the endcaps after fewer barrel layers.
        <em>Illustration: ideal uniform field, original CMS barrel geometry, 30 µm hits, 0.4 X₀ material. Not simulator output.</em>
      </p>
    </div>
  </div>
}
