// Physics for the illustrative event display. Pure functions, no DOM, so they
// can be unit-tested. Units: metres, tesla, GeV, c = 1.
//
// Geometry: original CMS barrel (2009–2016), matching src/heplab/physics/detector.py
// for the pixel layers and tracker envelope. Strip radii and lengths from
// CMS Collaboration, JINST 3 (2008) S08004, section 3. Endcap disks are not
// drawn because they are perpendicular to this view.

export type Layer = { r: number; halfZ: number; kind: 'pixel' | 'tib' | 'tob' }

export const LAYERS: Layer[] = [
  ...[0.044, 0.073, 0.102].map(r => ({ r, halfZ: 0.265, kind: 'pixel' as const })),
  ...[0.255, 0.339, 0.4185, 0.498].map(r => ({ r, halfZ: 0.70, kind: 'tib' as const })),
  ...[0.608, 0.692, 0.78, 0.868, 0.965, 1.08].map(r => ({ r, halfZ: 1.18, kind: 'tob' as const })),
]
export const TRACKER = { r: 1.10, halfZ: 2.80 }
// ECAL barrel: inner face 1.29 m, 230 mm crystals, covers |η| < 1.479.
export const ECAL = { rInner: 1.29, rOuter: 1.52, maxEta: 1.479 }
export const OUTER_LAYER_R = 1.08
export const MUON_MASS = 0.10566
export const PION_MASS = 0.13957

export type Point = [number, number]
export type Particle = { pt: number; eta: number; phi: number; q: 1 | -1; mass: number; probe?: boolean }
export type Track = {
  particle: Particle
  R: number
  center: Point | null
  inTracker: Point[]
  beyond: Point[]
  hits: Point[]
  outerPoint: Point | null
  end: 'barrel' | 'endcap' | 'looper'
}

export function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Charged-pion transverse-momentum spectrum, Tsallis form used in LHC
// minimum-bias fits: dN/dpT ∝ pT · (1 + (mT − m)/(nT))^−n.
const TSALLIS = { T: 0.13, n: 7 }
const ptGrid = (() => {
  const xs: number[] = [], cdf: number[] = []
  let total = 0
  for (let i = 0; i <= 600; i++) {
    const pt = 0.05 * Math.pow(30 / 0.05, i / 600)
    const mT = Math.hypot(pt, PION_MASS)
    const density = pt * Math.pow(1 + (mT - PION_MASS) / (TSALLIS.n * TSALLIS.T), -TSALLIS.n)
    total += density * (i ? pt - xs[i - 1] : 0)
    xs.push(pt); cdf.push(total)
  }
  return { xs, cdf: cdf.map(c => c / total) }
})()

function samplePt(u: number) {
  const { xs, cdf } = ptGrid
  let i = cdf.findIndex(c => c >= u)
  if (i <= 0) return xs[Math.max(0, i)]
  const f = (u - cdf[i - 1]) / (cdf[i] - cdf[i - 1] || 1)
  return xs[i - 1] + f * (xs[i] - xs[i - 1])
}

function poisson(mean: number, rand: () => number) {
  const limit = Math.exp(-mean)
  let k = 0, p = rand()
  while (p > limit) { k++; p *= rand() }
  return k
}

// Toy minimum-bias event: about 6 charged particles per unit η (√s = 13 TeV)
// over |η| < 2.5, shown above a display threshold.
export const DISPLAY_PT_MIN = 0.5
export function minimumBiasEvent(seed: number): Particle[] {
  const rand = mulberry32(seed)
  const n = poisson(30, rand)
  const out: Particle[] = []
  for (let i = 0; i < n; i++) {
    const particle: Particle = {
      pt: samplePt(rand()), eta: -2.5 + 5 * rand(), phi: 2 * Math.PI * rand(),
      q: rand() < 0.5 ? 1 : -1, mass: PION_MASS,
    }
    if (particle.pt >= DISPLAY_PT_MIN) out.push(particle)
  }
  return out
}

// Helix in a uniform field along +z. s is the transverse arc length; positive
// charges turn clockwise seen from +z. R[m] = pT[GeV] / (0.3 B[T]).
export function trace(particle: Particle, B: number): Track {
  const { pt, eta, phi, q } = particle
  const R = B > 0 ? pt / (0.3 * B) : Infinity
  const center: Point | null = Number.isFinite(R) ? [q * R * Math.sin(phi), -q * R * Math.cos(phi)] : null
  const at = (s: number): Point => center
    ? [center[0] - q * R * Math.sin(phi - q * s / R), center[1] + q * R * Math.cos(phi - q * s / R)]
    : [s * Math.cos(phi), s * Math.sin(phi)]
  const dzds = Math.sinh(eta)
  const sZ = dzds === 0 ? Infinity : TRACKER.halfZ / Math.abs(dzds)
  const sLoop = center ? 2 * Math.PI * R : Infinity
  const ds = Math.min(0.004, center ? R / 60 : 0.004)
  const ecalHalfZ = ECAL.rInner * Math.sinh(ECAL.maxEta)
  const inTracker: Point[] = [[0, 0]]
  const beyond: Point[] = []
  const hits: Point[] = []
  let outerPoint: Point | null = null
  let end: Track['end'] = 'looper'
  let prev: Point = [0, 0], prevR = 0
  for (let s = ds; s <= Math.min(sLoop, 8); s += ds) {
    const p = at(s)
    const r = Math.hypot(p[0], p[1])
    const leaving = beyond.length > 0
    if (!leaving) {
      if (s > sZ) { end = 'endcap'; break }
      for (const layer of LAYERS) {
        if ((prevR - layer.r) * (r - layer.r) > 0 || prevR === r) continue
        const f = (layer.r - prevR) / (r - prevR)
        const z = (s - ds + f * ds) * dzds
        const hit: Point = [prev[0] + f * (p[0] - prev[0]), prev[1] + f * (p[1] - prev[1])]
        if (Math.abs(z) <= layer.halfZ) hits.push(hit)
        if (layer.r === OUTER_LAYER_R && !outerPoint && r > prevR) outerPoint = hit
      }
      inTracker.push(p)
      if (r >= TRACKER.r) { end = 'barrel'; beyond.push(p) }
    } else {
      const reach = particle.mass === MUON_MASS ? ECAL.rOuter + 0.1 : ECAL.rInner
      if (Math.abs(s * dzds) > ecalHalfZ || r >= reach) { beyond.push(p); break }
      beyond.push(p)
    }
    prev = p; prevR = r
  }
  return { particle, R, center, inTracker, beyond, hits, outerPoint, end }
}

// Sagitta of the arc between the beamline and a point at chord length L.
export function sagitta(R: number, L: number) {
  if (!Number.isFinite(R)) return 0
  if (2 * R < L) return NaN
  return R - Math.sqrt(R * R - (L * L) / 4)
}

// Transverse-momentum resolution at η = 0, PDG Review "Particle detectors at
// accelerators": Gluckstern measurement term for N equally spaced points with
// resolution σ over lever arm L, plus multiple scattering in x/X0 of material.
export const RESOLUTION = { sigma: 30e-6, lever: OUTER_LAYER_R - 0.044, material: 0.4 }
export function ptResolution(pt: number, B: number, mass: number, nHits: number) {
  if (B <= 0 || nHits < 3) return null
  const { sigma, lever, material } = RESOLUTION
  const beta = pt / Math.hypot(pt, mass)
  const measurement = (sigma * pt) / (0.3 * B * lever * lever) * Math.sqrt(720 / (nHits + 4))
  const scattering = (0.016 * Math.sqrt(material)) / (0.3 * B * lever * beta * beta)
  return { measurement, scattering, total: Math.hypot(measurement, scattering) }
}
