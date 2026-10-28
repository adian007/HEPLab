# 04 · Interactive event display

Files: `src/components/trackPhysics.ts` (physics, pure functions) and
`src/components/TrackLab.tsx` (canvas and controls).

A transverse (r–φ) view of a toy proton–proton event with one muon the visitor
controls. It shows how a tracker measures momentum from track curvature, and
why that measurement gets worse at high momentum.

It is computed in the browser, does not call the simulator, and is labelled as
an illustration on the page.

## Geometry

Original CMS barrel (2009–2016), the same era the simulator uses.

| Element | Radius (m) | Half-length \|z\| (m) | Source |
|---|---|---|---|
| Pixel barrel, 3 layers | 0.044, 0.073, 0.102 | 0.265 | `src/heplab/physics/detector.py` (CMS CR-2014/389) |
| Inner strip barrel (TIB), 4 layers | 0.255, 0.339, 0.4185, 0.498 | 0.70 | CMS, JINST 3 (2008) S08004 |
| Outer strip barrel (TOB), 6 layers | 0.608 – 1.080 | 1.18 | same |
| Tracker envelope | 1.10 | 2.80 | `detector.py` |
| ECAL barrel | 1.29 – 1.52, \|η\| < 1.479 | — | JINST 3 (2008) S08004 |

Endcap disks are not drawn: they are perpendicular to this view.

## Event

- Charged multiplicity: Poisson with mean 30 (about 6 per unit η at
  √s = 13 TeV, over |η| < 2.5).
- Each particle is a charged pion with η uniform in [−2.5, 2.5], φ uniform,
  random charge.
- pT from a Tsallis spectrum, the form used in LHC minimum-bias fits:
  `dN/dpT ∝ pT · (1 + (mT − m)/(nT))^−n` with T = 0.13 GeV, n = 7.
- Only particles with pT > 0.5 GeV are shown, which is typical for event
  displays. That leaves about 10 tracks per event.
- The highlighted track is a muon at η = 0 with the pT, field and charge from the
  controls.
- Seeded PRNG (mulberry32): the same event number always draws the same event.

## Track propagation

Uniform field along +z; positive charges turn clockwise seen from +z.

```text
R [m] = pT [GeV] / (0.3 · B [T])
centre C = ( q R sin φ0, −q R cos φ0 )
φ(s)   = φ0 − q s / R            s = transverse arc length
x(s)   = Cx − q R sin φ(s)
y(s)   = Cy + q R cos φ(s)
z(s)   = s · sinh η
```

A track is drawn solid while it is inside the tracker volume and ends when:

- it reaches r = 1.10 m (barrel exit), or
- |z| reaches 2.80 m (it leaves through an endcap), or
- it completes one full turn (a "looper"; real loopers keep spiralling along z
  and lose energy, which this view does not model).

Barrel-exit pions are extrapolated as a dashed line to the ECAL inner face; the
muon continues dashed through the ECAL toward the muon system. No calorimeter
energy deposits are drawn.

A hit is drawn where the track crosses a barrel layer **and** |z| at that point
is within the layer's half-length. Forward tracks therefore show fewer barrel
hits, as in the real detector.

## Readouts

**Sagitta** of the chord from the beamline to the outermost layer (L = 1.08 m):

```text
s = R − sqrt(R² − L²/4)  ≈ L² / (8R)
```

**Momentum resolution** at η = 0, from the PDG Review chapter "Particle
detectors at accelerators", combined in quadrature:

```text
measurement:  σ(pT)/pT = σ · pT / (0.3 B L²) · sqrt(720 / (N + 4))
scattering:   σ(pT)/pT = 0.016 · sqrt(x/X0) / (0.3 B L β²)
```

with σ = 30 µm per hit, L = 1.036 m (first to last barrel layer), N = barrel
hits on the track, x/X0 = 0.4 (approximate CMS tracker material at η = 0).

The Gluckstern formula assumes equally spaced, equally precise points; CMS has
neither, so treat the number as an order-of-magnitude illustration. It lands
near the published CMS muon-track resolution (about 1–2 % at 100 GeV in the
barrel), which is a sanity check, not a validation.

## Reference values

Computed from `trackPhysics.ts` with Node on 28 Oct 2026:

| Case | Expected |
|---|---|
| 4 GeV μ, 3.8 T, η = 0 | R = 3.51 m, 13 hits, sagitta 41.8 mm, σ/pT = 0.86 % |
| 50 GeV μ, 3.8 T | σ/pT = 1.17 % (the two terms are about equal here) |
| 100 GeV μ, 3.8 T | σ/pT = 1.81 % (measurement term 1.60 % dominates) |
| 0.4 GeV μ, 3.8 T | looper, never reaches the outer layer |
| 5 GeV π, η = 2 | leaves through an endcap with 2 pixel hits |
| Seeds 1–499 | 9.1 tracks shown per event on average |

## Rules for changing it

- Physics stays in `trackPhysics.ts`; the component only draws.
- Every new number or constant needs a unit and a source in this file.
- Any new readout needs a reference value in the table above.
- Do not add energy loss, showers or detector response here. Those belong to
  the simulator; show real simulator output with its provenance instead.
