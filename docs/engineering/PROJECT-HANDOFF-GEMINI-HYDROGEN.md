# HEPLab project handoff for Gemini Hydrogen

Prepared 24 November 2026 for a coding assistant continuing work in this repository.

## Project in brief

HEPLab is an educational high-energy physics workbench for scoped particle simulation and analysis of CERN Open Data. The active desktop simulator is a **native C++20 / Qt 6 application**. It uses a **local Python worker** for simulation, data access, and analysis. A separate **ASP.NET Core Razor Pages website targeting .NET 10** is the project guide and documentation site.

The desktop’s purpose is to let a learner configure a run, inspect generated or recorded events, study plots and cutflows, compare runs, and keep provenance with saved results. The project is early implementation. Treat scientific scope and verification status precisely; do not describe the app as a calibrated CMS detector or a publication-ready analysis.

## What to keep

- Native desktop application: `desktop/` and the root `CMakeLists.txt`, `CMakePresets.json`.
- Python application and worker: `src/heplab/`, `tests/`, and required runtime/configuration files.
- .NET documentation site: `web/HEPLab.Web/` and `web/docs/`.
- Scientific and engineering documentation: `docs/`, `contracts/`, `manifests/`, `kernels/`, and relevant build/deployment support.
- The `validation-worktree/` directory is a separate validation checkout. **Do not edit, move, clean, reset, or delete it.**

The old React/Vite site and Python browser Workbench are retired. Do not restore them or build new browser-based simulator interfaces. Python code is still required by the Qt app and must be preserved.

## Desktop architecture and entry points

```text
Qt 6 / C++20 desktop shell (`desktop/src`)
  ├─ JSON-lines worker client (`desktop/src/WorkerClient.*`)
  ├─ Python operations and scientific services (`src/heplab/desktop`, `src/heplab/sim`, readers/analyses)
  ├─ immutable run and project state (`desktop/src/ProjectStore.*`, worker artifacts)
  ├─ Qt Widgets and QPainter projections/plots
  └─ Qt OpenGL 3D detector/event view (`desktop/src/DetectorViewport3D.*`)
```

- Main window and workspaces: `desktop/src/MainWindow.cpp`, `desktop/src/MainWindow.h`.
- Typed event conversion and units: `desktop/src/EventData.cpp`, `desktop/src/EventData.h`.
- 2D event projections: `desktop/src/EventProjectionWidget.*`.
- 3D view: `desktop/src/DetectorViewport3D.*`.
- Scientific plots: `desktop/src/ScientificPlotWidget.*`.
- Worker lifecycle/protocol: `desktop/src/WorkerClient.*`, `src/heplab/desktop/worker.py`, `src/heplab/desktop/operations.json`.
- Native test suite: `desktop/tests/MainWindowTests.cpp`, registered in `desktop/CMakeLists.txt`.
- Standard launcher: `tools/start_workbench.ps1`. It starts the built native Qt executable and can configure the WSL simulation runtime with `-Distro Ubuntu`.
- Build presets: `windows-ninja`, `windows-ninja-release`, `windows-vs2022` in `CMakePresets.json`. Qt 6.8+ and a configured Windows C++ toolchain are required.

## Current desktop feature map

The navigation contains **Simulation**, **Event Inspector**, **CMS data**, **Runs / Comparisons**, **Validation**, **Learning / Documentation**, and **Projects**.

- **Simulation:** analytic teaching source and a capability-gated, real PYTHIA8 8.312 → DELPHES 3.5.1 Drell–Yan collision path through Linux/WSL. Collision config includes event count/seed and reconstructed-muon cuts. Runtime setup is described in `docs/engineering/sim-runtime.md`.
- **Event Inspector:** event/object table, linked XY/XZ projections and interactive 3D detector view; track selection, filtering, framing, event navigation and model/crossing layers. It can display multiple stable generated charged-particle paths for collision events. CMS recorded-data events show reconstructed muons with ideal-solenoid predicted paths, not measured detector hits.
- **CMS data:** manifest/catalog-backed datasets, metadata/certification/provenance/files/scope, dimuon selection and plots when samples are available. Windows acceptance and scientific limitations are documented in `docs/engineering/desktop-cms-workspace-2026-10-29.md`.
- **Runs / Comparisons:** committed result plots and cutflows; pinning a run shares binning/range for comparison. Supported observables depend on artifact availability and include invariant mass, muon pT/eta, MET and jet count. The comparison is exploratory and not luminosity-normalized unless a particular result says otherwise.
- **Projects and run history:** project/run persistence with filterable run history, status/backend columns and selection-driven run details.
- **Validation:** scoped reference checks and evidence, not global validation of the complete simulator.
- **Learning / Documentation:** embedded learning content and evidence requirements.

Relevant desktop design and evidence references:

- `docs/engineering/native-gui-standards.md` — interaction/design principles and workspace-specific usability goals.
- `docs/engineering/gui-design.md` — layout, navigation, keyboard, views, plots, and workflow intent.
- `docs/engineering/desktop-collisions-2026-10-29.md` — collision workflow and its explicit physics boundary.
- `docs/engineering/desktop-cms-workspace-2026-10-29.md` — CMS workflow and data limitations.
- `docs/engineering/sim-runtime.md` — supported generator runtime, setup, and acceptance constraints.
- `docs/engineering/run2-z-validation.md` — cautious validation plan; it is a specification, not proof that all gates have passed.

Some rebuild-audit records are historical and may predate the current native rebuild. Confirm a claim against the current source and current tests before relying on an older status table. `README.md` and `docs/engineering/README.md` are useful orientation, but the implementation is authoritative for what currently exists.

## Scientific and product boundaries

- The registered generator path is a restricted symmetric 13 TeV pp Drell–Yan γ*/Z → μμ configuration with a 60–120 GeV process window, PYTHIA Monash tune/internal PDF set 13 and a DELPHES CMS card. It has no pileup and is not a general process editor.
- Generated truth particles, DELPHES reconstructed objects, and ideal-field propagated display trajectories are different things. Preserve their labels and provenance. Do not call ideal propagated paths measured tracks or detector hits.
- CMS recorded data selections and collision simulation are distinct sources. Keep certification/provenance and per-source limitations visible.
- Do not upgrade exploratory shapes or smoke tests into a claim of CMS calibration, complete conservation through detector response, or publication-quality results.
- Missing optional backends, samples, or runtime capabilities must produce an explicit unavailable state, never simulated success.
- Keep units explicit and consistent (momentum in GeV/c where shown; positions in metres; field in tesla; invariant mass in GeV/c² as appropriate).

## Workspace state and safe collaboration

The working tree has substantial pre-existing modifications, additions, and deletions across the Python package, docs, website, native desktop, CI, and generated outputs. These reflect prior project work and cleanup. They are **not** a clean baseline. Before editing, inspect `git status --short` and the relevant diffs. Do not reset, checkout, restore, clean, or overwrite unrelated changes. Make a focused change and report touched files. Do not modify the `validation-worktree/` checkout.

Do not reintroduce the removed React/Vite website or browser Workbench. Do not remove Python modules merely because the retired Python browser UI has been removed; the Qt desktop depends on Python worker code.

## Build and verification

Use the existing CMake configuration/presets rather than inventing a new build system. Relevant Qt tests are declared in `desktop/CMakeLists.txt`; some optional integration tests skip unless a real pinned PYTHIA/DELPHES runtime is configured. Run focused checks for changed behavior and report exactly which ones ran and which were skipped. A successful unit test is not a scientific validation claim.

The normal user launch path is:

```powershell
./tools/start_workbench.ps1
```

For the WSL-backed collision workflow, configure/use the installed WSL runtime as described in `docs/engineering/sim-runtime.md`, then launch through the script with the selected distro. Never silently switch a user's standard launcher or overwrite an executable while the app is open without checking the build result and preserving the current binary.

## Immediate improvement targets from the user

The user wants the native Qt app improved substantially, with particular focus on:

1. A convincing full collision event in the 3D Event Inspector: multiple particles with useful, clearly differentiated trajectories and linked object details. Retain the physics distinction between truth, DELPHES objects, and ideal display propagation.
2. Clearer typography, spacing, hierarchy, and readable long-form content in CMS Open Data and Learning / Documentation. Attached screenshots showed manifest details and lesson text displayed as plain unstructured prose.
3. A more useful Runs / Comparisons workspace, including interpretable histograms/uncertainties, meaningful run comparison, better empty/one-event states, and additional honest analysis/graph modes.
4. Fixing run-history text density: a screenshot showed IDs, status, and backend squeezed together in plain rows. The current implementation was updated to a structured table; check the code before assuming this is still outstanding.

When improving the UI, prefer coherent task flow and legible hierarchy over adding controls without a clear use. Preserve keyboard accessibility, units, axis labels, event-level uncertainty semantics, source identity, filters, and the ability to inspect numeric values. Keep charts sourced from saved artifact values.

## Suggested first actions for the receiving assistant

1. Read this handoff, then inspect `git status --short` and the current implementations in `desktop/src/MainWindow.cpp`, `ScientificPlotWidget.*`, `DetectorViewport3D.*`, `EventData.*`, the Python worker/simulation modules, and `desktop/tests/MainWindowTests.cpp`.
2. Verify the exact current UI and available data fields before proposing features; do not infer a feature from its name or a screenshot.
3. Choose one coherent, reviewable improvement slice, implement it in the native app, add/update focused tests, and capture/inspect a native UI view if the environment supports it.
4. Update the relevant engineering notes with implemented behavior and evidence, preserving explicit limitations.
5. Summarize the changes, build/test results, skips, evidence, and any next high-value work.
