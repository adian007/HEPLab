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

## Interpretation rules

- A run that completes is not automatically physics validated.
- A reference-table regression establishes agreement only with that table and declared domain.
- PYTHIA/DELPHES results depend on the pinned versions, process settings, cards, and seeds.
- Detector calibration requires independent evidence; using CMS-branded conditions does not establish calibration.

See the engineering [project charter](https://github.com/adian007/HEPLab/blob/main/docs/engineering/00-charter.md) and [native runtime guide](https://github.com/adian007/HEPLab/blob/main/docs/engineering/sim-runtime.md).
