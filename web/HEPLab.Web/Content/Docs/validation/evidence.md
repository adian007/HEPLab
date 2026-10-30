---
title: Validation evidence
description: Recorded reference checks, their acceptance gates, and what they do not establish.
---

HEPLab distinguishes software verification, agreement with a named reference, detector calibration, and physics validation. These are different claims with different evidence requirements.

## Silicon mean-ionization reference

The muon mean-ionization model for silicon is compared with the PDG 2025 table. Alternate rows are used as interpolation knots; the remaining rows are held out. The predeclared gate is a maximum absolute relative error of 2%; the recorded maximum on the held-out rows is 0.410525%.

This result covers mean ionization for muons in silicon over the declared table domain. It does not include stochastic loss or radiative interactions, and it does not calibrate a detector. Source: [PDG silicon muon table](https://pdg.lbl.gov/2025/AtomicNuclearProperties/MUE/muE_silicon_Si.txt).

## CMS field reference regression

The CMS field implementation is compared against a pinned CMSSW reference over one million reference points, including 14,867 tracker points. The maximum vector difference is below the predeclared 2 μT software gate. The report says the payload IOV is not verified and full field-map transport is not enabled.

This is a software regression against a CMS software reference, not a new measured-data calibration. Source: [CMSSW BCyl reference](https://github.com/cms-sw/cmssw/blob/c04fa510bb587b8ee3fa171888468f80de714fa8/MagneticField/ParametrizedEngine/src/BCyl.h).

## Low-mass resonance reference-data regression

The corrected v2 sample chooses one opposite-charge candidate by maximum scalar `pT` sum. The candidate selector has no mass or PDG-target input. Events are split by a stable run/luminosity-block/event hash before fitting; training and held-out events are disjoint within one Run2016G file. They are not an independent dataset.

The frozen aggregate result is **failed**: J/ψ, Υ(1S) and Υ(3S) held-out mass gates pass, while the Υ(2S) held-out mean misses its existing tolerance. The threshold was retained. The report is a scoped reference-data regression, not a detector calibration or independent physics validation. The previous target-ranked v1 sample is preserved and marked exploratory. See the [v2 report](https://github.com/adian007/HEPLab/blob/main/src/heplab/data/reference/cms-resonance-data-report-v2.json) and [procedure](https://github.com/adian007/HEPLab/blob/main/docs/engineering/cms-physics-regression-v2.md).

## Muon survival teaching experiment

The local Workbench includes a separate fixed-momentum proper-time survival calculation with an analytic exponential comparison and reproducible seeded draws. Optional altitude inputs define only a plane-parallel straight path. This does not model atmospheric production, showers, air energy loss, scattering, or decay daughters.

## PYTHIA8/DELPHES checks

Two fixed-seed 1,000-event samples support a scoped muon response transfer check in a declared Drell–Yan process and kinematic domain. The supported chain is pinned to PYTHIA 8.312, DELPHES 3.5.1, ROOT 6.40.04, and HepMC3 3.3.1 on Linux x86-64.

These checks are implementation evidence for the pinned setup. They do not establish a full CMS detector simulation, general-purpose muon efficiencies, a measured cross section, or independent physics validation.

Generator/card transfer checks are a different evidence category from software parity, comparison with a reference table, or comparison with recorded CMS data. A reproducible PYTHIA/DELPHES artifact demonstrates the specified generator/card workflow; it is not an experimental CMS calibration.

## Source records

- [Geometry and calibration record](https://github.com/adian007/HEPLab/blob/main/docs/engineering/geometry-calibration.md)
- [Machine-readable field reference](https://github.com/adian007/HEPLab/blob/main/src/heplab/data/reference/cms-field-validation.json)
- [Machine-readable silicon calibration](https://github.com/adian007/HEPLab/blob/main/src/heplab/data/reference/silicon-calibration.json)
- [Verification requirements](https://github.com/adian007/HEPLab/blob/main/docs/engineering/14-verification.md)
