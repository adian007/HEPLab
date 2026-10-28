# A1 Proposal — Dimuon spectrum (R1, docs/WORKFLOW.md §2)

> Historical proposal. The [analysis specification](../../../../docs/engineering/09-analysis.md)
> separates inclusive low-mass and Z-region selections and defines the required
> trigger, weighting, pairing and validation gates. This prototype is not a
> calibrated mass/width measurement.

```mermaid
flowchart LR
    C[Certified trigger-compatible events] --> M[Defined muon selection]
    M --> P[Explicit opposite-charge pair policy]
    P --> H[Weighted spectrum and event cutflow]
    H --> F[Normalized fit and uncertainty validation]
```

- **Status:** proposed · **Phase:** P2 · **Author:** sketch

## Physics goal

Reconstruct the inclusive dimuon mass spectrum from CMS open data and fit the
Z→μμ line shape; expose J/ψ and Υ resonances in the same histogram. Then (A2)
report a Z yield with acceptance×efficiency and a stat/syst breakdown.

## Datasets

- **Data:** CMS Run2016 DoubleMuon NanoAOD (13 TeV) — manifest
  `manifests/datasets/run2016_doublemuon_example.yaml`.
- **Sim (A3):** Drell–Yan → μμ via PYTHIA8 → DELPHES (ADR-0004/0005), same
  selection, normalized to schema v1.

## Selection

See `config.yaml` — two muons, pT > 25 GeV, |η| < 2.4, iso < 0.15,
opposite charge for the Z window; full spectrum kept unbinned for A1.

## Observables & output

- m(μμ) spectrum (400 log bins, 0.5–200 GeV)
- cutflow table (per-selection yields)
- Voigtian+exponential fit in 70–110 GeV → Z mass/width (PDG target: 91.1880 GeV)

## Known pitfalls

- NanoAOD muon isolation is pfRelIso04 — map to schema `iso` in the reader,
  do not recompute.
- Simulation closure (R4) must precede any data claim (R5) — muon efficiency
  vs pT/η from DELPHES is a model, quoted with fidelity caveats (ADR-0004).
