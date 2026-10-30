---
title: Capabilities
description: What HEPLab implements today and how mature each project area is.
---

HEPLab is in early implementation. These labels describe software progress, not physics validation.

| Area | Current state | What is present |
|---|---|---|
| Local simulation | Working increment | Deterministic muon thin-slab reference bench, compiled Rust numerical engine, and optional native PYTHIA8 + DELPHES Drell–Yan chain. |
| CMS Open Data | Foundations in place | Versioned manifests, certification, exact source ranges, checksums, readers, and bounded cache with integrity checks. |
| Analysis workflow | Early implementation | Schema-v1 event model, dimuon analysis and cutflows, iminuit fits, and PNG plots. |
| Guided education | Early implementation | Six-step browser lab with evaluated checkpoints and local progress; the Python lab uses the same checks and digest-verified JSON resume. |
| Shareable results | Early implementation | Offline HTML result pages with provenance, accessible plot controls, and a browsable synthetic example gallery. |
| Python API | Early implementation | Versioned `heplab.run`, `load`, `read`, `fit_peak`, and `export_html` entry points with deterministic provenance. |
| Notebook integration | Early implementation | Interactive `Lab.display()` checkpoint widget, sandboxed result display, and throttled live histograms. |
| Validation evidence | Mixed named-reference status | PDG mean-table and pinned CMSSW field regressions have narrow scopes. Corrected CMS resonance v2 uses target-independent selection but currently fails its held-out Υ(2S) gate. No independent detector validation is established. |

## Simulator workbench

The local workbench includes source/model selection, run controls, particle inspection, XY/XZ/3D views with a shared path cursor, crossings, diagnostics, and result export. It provides a separate fixed-momentum muon survival experiment. The interface reports the selected backend and validation scope. It does not make a non-validated model valid by running it successfully.

## Data and analysis

The Run2016G DoubleMuon path carries certification and source-range provenance into cache chunks and analysis artifacts. The analysis layer retains signed event weights, cutflows, and fit results. The canonical manifests and technical requirements live in the [engineering handbook](https://github.com/adian007/HEPLab/tree/main/docs/engineering).

## Status labels

- **Working increment:** a bounded software path runs end to end.
- **Foundations in place:** contracts, data structures, or readers exist; a full user workflow may still be incomplete.
- **Early implementation:** a meaningful path exists, but integration or validation remains incomplete.
- **In progress:** implementation or evidence is still being completed.
- **Planned:** the capability is not yet available.

None of these labels means “physics validated.” See [how to read validation evidence](/validation/reading-results/).
