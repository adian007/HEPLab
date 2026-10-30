---
title: Roadmap
description: Current engineering direction and release work that remains open.
---

The roadmap is conditional on verification evidence and physics review. A listed target is not an available feature or a release promise.

| Workstream | Current direction | Open work |
|---|---|---|
| Numerical core | Rust and Python reference implementations cover checked kinematics and selected response operations; a current verification registry checks named submodels. | Broader transport and response contracts, performance budgets, and independent verification across more domains. |
| Data path | Versioned manifests, certification, exact source ranges, integrity checks, and bounded caching are implemented for selected datasets. | More records, stronger transfer-byte limits, cache recovery evidence, and wider offline replay. |
| Simulation | A scoped educational reference bench, isolated muon survival experiment, and pinned native PYTHIA8/DELPHES workflow exist. | The current low-mass held-out reference regression fails its Υ(2S) gate; independent matched data/MC, response systematics and broader physics validation remain open. |
| Analysis | A dimuon workflow and reusable artifact contracts are available. | More analyses, uncertainty coverage, and review against independent references. |
| Distribution | A Windows desktop shell has been smoke-tested. | Public installers, signing, updates, and a documented support matrix. |

The detailed prioritized sequence and acceptance gates are maintained in the [engineering implementation roadmap](https://github.com/adian007/HEPLab/blob/main/docs/engineering/implementation-roadmap.md).
