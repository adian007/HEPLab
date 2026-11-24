# HEPLab native desktop development log

## 2026-11-23 — Repository rebuild baseline

- Audited the actual repository and confirmed that `desktop/` is deleted.
- Distinguished existing Python/Rust/CMS/simulation capabilities from
  historical Tauri claims.
- Added C++20/Qt 6 CMake infrastructure and a minimal native shell.
- Added accepted ADR-0012 and ADR-0013.
- Native compile remains blocked locally: Qt 6 is installed in Conda, but no
  C++ compiler/Ninja is available on `PATH`.
- Handbook check passed: 48 pages, 49 Mermaid blocks, 90 requirements and
  5 schemas/4 examples.
- A targeted existing-backend test run cannot collect `test_desktop_worker.py`
  because it imports the deliberately deleted `desktop.build_worker` module.

## 2026-11-23 — Windows C++ toolchain and native vertical slice

- Installed Visual Studio Build Tools 2022 component 17.14.45 with
  `Microsoft.VisualStudio.Workload.VCTools`, MSVC 14.44.35207 x64, and Windows
  11 SDK 10.0.26100.0.
- Installed Ninja 1.13.2 and Qt 6.8.3 `win64_msvc2022_64` under `D:\Qt`.
- Confirmed Qt uses `win32-msvc` and the toolchain is x64/MSVC-compatible.
- Corrected CMake test registration (`enable_testing` before `add_subdirectory`)
  and Qt runtime `PATH` registration for CTest.
- Debug build and tests pass.
- Release build and tests pass.
- Launched both Debug and Release executables; each remained responsive, had
  the title `HEPLab Workbench`, and was stopped after process verification.
- Migrated `tests/test_desktop_worker.py` to remove deleted Tauri/PyInstaller
  dependencies. The reusable worker contract suite passes 20 tests.
- Added native `WorkerClient` JSON-lines IPC and the first analytic simulation
  vertical slice: experiment selection, seed/budget/kinematic controls, submit,
  poll, event retrieval, cancellation, and JSON result export.
- Native Qt tests pass for invalid worker configuration, completed analytic
  execution with an artifact, and cancellation without an artifact.
- 3D rendering, CMS dataset UI, plotting, and packaging are not claimed complete.
- Representative native Simulation screenshot generated at
  `output/native-rebuild/native-shell-simulation.png`.
- Persistent project lifecycle implemented and tested: create, rename, open,
  save configuration, reopen configuration, run-history listing and worker
  project-root switching.
- Debug and Release split CTest cases pass for native shell, navigation,
  project persistence, worker success and cancellation.

## 2026-11-23 — Scientific Event Inspector and plotting

- Independently inspected the actual analytic artifact fields: metre Cartesian
  trajectories, trajectory crossings, object IDs, PDG/charge, truth momentum,
  digitization and geometry surfaces.
- Added native XY and XZ `QWidget` projections with fitted scene bounds,
  unit labels, track and crossing rendering, mouse line/picking and synchronized
  particle selection.
- Added Qt OpenGL 3D viewport ADR-0014. The view supports orbit, zoom,
  middle/right-button pan, camera reset, geometry wires, trajectories,
  crossing points and Shift+click selection.
- Added explicit context-failure text; XY/XZ remain available if OpenGL shaders
  or hardware initialization fail.
- Added artifact-only invariant-mass and muon-pT plots. Bin error bars are
  explicitly Poisson `sqrt(N)`; no fitted model or covariance is invented.
- Native 2D, 3D and plot tests pass in both Debug and Release slices.
- Added native CMS Open Data catalog discovery through `datasets.list`; it
  shows manifest-backed entries and limits, but download, caching and
  recorded-data analysis remain unimplemented.
