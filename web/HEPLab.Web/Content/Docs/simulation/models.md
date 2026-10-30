---
title: Simulation models and fidelity
description: Distinguish analytic demonstrations, the reference bench, native fast simulation, and future transport work.
---

HEPLab contains models at different levels of fidelity. The software must state which model produced an output; a shared file format does not make the models equivalent.

| Tier | Role | Current boundary |
|---|---|---|
| Analytic/toy | Demonstrate kinematics and controlled response. | Analytic demonstrations are illustrative; simulation outputs come from the local workbench. |
| Reference bench | Exercise transparent, scoped propagation and a thin-slab material response. | Heavy, singly charged particles in thin silicon; no full detector material budget or showers. |
| PYTHIA8 + DELPHES | Generate collisions and apply a pinned fast-simulation reference. | Linux/WSL, fixed process and CMS card; no pileup or NLO matching claim. |
| Detailed transport | Future integration of more complete particle-matter interactions. | Not implemented as a supported HEPLab workflow. |

## Output layers are different objects

- A **declared analytic pair** is a controlled teaching input, not collision data.
- A **truth particle** comes from the event generator and is not a reconstructed object.
- A **DELPHES object** is a fast-simulation response under the named card and settings. It is not a measured CMS muon.
- A **recorded NanoAOD object** is a reconstructed quantity from the named CMS data source. The Workbench's IP-assumed ideal-field display path is only a visualization; it is not the fitted track or a hit.
- A **predicted surface crossing** is a geometric calculation. A **digitized slab channel** is a separate illustrative electronics calculation. Neither is a recorded detector hit.

The silicon table provides **mean stopping power**. The bounded slab separately applies deterministic continuous mean loss, a sampled Gaussian Highland scattering core, and independent ADC digitization. They are distinct model components. Mean loss does not imply a stochastic loss distribution, and ADC output is not calibrated CMS electronics.

## Muon survival experiment

The Workbench offers a separate single-muon proper-time experiment. It uses the 2025 PDG mean lifetime at fixed momentum, compares seeded sampled survival with the analytic exponential, and can calculate a plane-parallel path from production/detector altitudes below 75 degrees. The altitude option does not model atmospheric matter, shower production, energy loss, scattering, or decay daughters.

## Magnetic curvature and sagitta

The [versioned curvature sweep](/examples/curvature-sagitta-sweep-v1.html) compares exact uniform-field helices over both charge signs, four momenta, and four field strengths, then compares the bounded pinned OAE field function with the exact nominal 3.8 T helix. Its circle-formula check is software verification. OAE endpoint differences are displayed without a field-measurement gate; neither comparison establishes CMS field accuracy or run-era conditions. The paths are vacuum predictions without material, scattering, response, or measured hits.

## Interpretation rules

- A run that completes is not automatically physics validated.
- A reference-table regression establishes agreement only with that table and declared domain.
- PYTHIA/DELPHES results depend on the pinned versions, process settings, cards, and seeds.
- Detector calibration requires independent evidence; using CMS-branded conditions does not establish calibration.
- Software parity, agreement with a reference table, a PYTHIA/DELPHES generator-card transfer, a comparison with recorded CMS data, and experimental detector validation are separate evidence categories.

See the engineering [project charter](https://github.com/adian007/HEPLab/blob/main/docs/engineering/00-charter.md) and [native runtime guide](https://github.com/adian007/HEPLab/blob/main/docs/engineering/sim-runtime.md).
