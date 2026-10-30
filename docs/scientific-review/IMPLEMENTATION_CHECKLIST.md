# Scientific Review Implementation Checklist

This checklist turns the ten-document review into code, test, and communication
work. It is deliberately kept beside the review so the implementation can be
audited against its source recommendations. Statuses identify implementation, partial scope, or external evidence. `done` means the software recommendation is implemented; it does not mean physics validated.

## P0 — protect scientific claims

| Status | Review recommendation | Implementation target | Required evidence / user-facing update |
|---|---|---|---|
| done — corrected v2 report gate fails at Υ(2S) | Remove PDG-target-dependent resonance candidate ranking and mass-window selection. | `tools/build_cms_resonance_validation.py`; new selector in `src/heplab/physics/cms_resonance_validation.py`; frozen selection tests. | Candidate selector must not accept a target mass; selection hash and sample provenance recorded; old target-selected report remains preserved but is labeled exploratory and excluded from pass gates. |
| done — disjoint events in the same file, not independent dataset | Create a fresh event-disjoint holdout and keep candidate choice frozen before fitting. | Resonance builder CLI/split; `tests/test_cms_physics_validation.py`; versioned evidence under `src/heplab/data/reference/`. | Fit/selection split and source ranges/hashes recorded; held-out events never influence selection or training; report avoids calling same-file holdout independent data validation. |

## P1 — model scope, provenance, physics and verification

| Status | Review recommendation | Implementation target | Required evidence / user-facing update |
|---|---|---|---|
| done | Centralize sourced particle constants and conventions. | New `src/heplab/physics/constants.py`; update Workbench, engine, labs and display defaults. | PDG source/year and uncertainty recorded; tests cover all consumers and units; keep frozen legacy fixtures interpretable. |
| done — separate fixed-momentum experiment | Add a separate relativistic muon survival experiment. | New lifetime calculation/sampling module, engine/worker operation, UI inputs/result panel and template. | Analytic survival and seeded proper-time sample checks over the roadmap momentum/path grid; no daughter-decay claim. |
| done for current run/result contracts | Attach versioned model/domain/evidence metadata to runs and tracks. | Model registry and result envelope in `src/heplab`; artifact serialization/migration; desktop preflight and export. | Unknown model IDs fail closed; round-trip tests preserve model ID/version, units, domains, evidence state, limitations and source references. |
| done | Add a machine-readable verification registry and reproducible command. | Registry schema/data plus runner using `docs/scientific-review/verification/independent_checks.py`. | Each row stores command, source/data hashes, environment, threshold, observed result, scope and `not_established`; no stale result is labeled current. |
| done for declared numerical domain | Expand independent numerical checks for supported calculations. | Tests/tools for four-vectors, 18-case field momentum/η/charge grid and boundary stop, geometry intersections, slab energy bookkeeping, RNG replay/schedule invariance, table edges and weighted fit coverage. | Tolerances declared before evaluation; SciPy remains an optional verification dependency, not a runtime dependency. |
| blocked (external dependency) | Validate material-loss distributions beyond mean stopping power. | Compare a pinned Geant4 configuration or published measurement; keep analytic model explicitly bounded. | Geant4 runtime/reference sample and expert-approved distribution gates are required; do not fabricate tails or calibration. |
| blocked (external dependency) | Complete CMS field/material/conditions transport or detector calibration. | Separate CMSSW/Geant4 integration and matched conditions-aware data/MC analysis. | Requires resolved GlobalTag/IOV, equivalent MC, certification/corrections, covariance and a physics reviewer; current analytic path remains `tracker-field reference`. |
| done | Preserve separation among analytic, DELPHES, measured-data, predicted-crossing and digitized-channel objects. | Run schemas, result labels, event display legend, evidence pages and exports. | Each object layer names source/model/units; no displayed synthetic or predicted object is described as a measured hit. |
| done — wrapper-inclusive microbenchmark, not end-to-end | Benchmark Python/Rust only on fixed semantic fixtures and measured workloads. | Existing Python/Rust tests plus reproducible benchmark command/artifact. | Record host/compiler/Python/workload/uncertainty/parity; do not optimize or add kernels without a measured bottleneck. |

## P2 — user workflows, UI, web and shareable artifacts

| Status | Review recommendation | Implementation target | Required evidence / user-facing update |
|---|---|---|---|
| done — grouped v2 envelope with legacy migration | Split analytic, collision, display and analysis configuration while retaining explicit migration. | `RunConfig`, API/worker contracts, saved jobs/artifacts and frontend config serialization. | Invalid combinations rejected before queueing; legacy flat configurations migrate explicitly and round-trip tests cover both forms. |
| done | Version full-run and selected-event artifacts separately. | `src/heplab/export/web_page.py`, artifact schemas and UI export actions. | `RunArtifact` and parent-linked `EventView` include run/event identity, source/model IDs, digest, seed, RNG/software versions and privacy flags; raw events/local paths excluded by default. |
| done for builds without optional samples; bundled-sample evidence depends on available fixtures | Smoke-test the frozen desktop worker's model and data capabilities. | `desktop/build_worker.py`, packaged worker protocol and `tests/test_desktop_worker.py`. | Empty CMS library is valid when no verified ROOT sample files are included; when bundled, both registered sample IDs must appear. This checkout has the certification mask but no Run2016G/DY ROOT sample pair. |
| done for current component metadata | Add a persistent preflight summary and explicit scientific legend/status. | Workbench markup/JS/CSS and saved result envelope. | Model/version, assumptions, ranges, omitted effects and validation status visible before Run and in the result; unknown status never becomes pass. |
| done | Use one typed selection state across tree/table/canvas/inspector. | `src/heplab/server/static/workbench.js`, display renderer and tests. | Event changes and unsupported canvas object selection clear stale highlights; non-trajectory rows state “not shown as a trajectory.” |
| done — linked XY/XZ default pair with switchable single views and 3D | Add synchronized XY and longitudinal views, shared path cursor, and switchable 3D. | Workbench paired SVG projections, shared typed selection, playback state, keyboard controls and table. | Pointer/keyboard selection and path cursor update both panels; axes and metre units remain visible; unsupported objects remain absent from trajectory paths. |
| done — beginner path with collapsible advanced models and corrective mode-aware errors | Simplify setup order and expose advanced response/field choices with explanations. | Workbench source/run controls stay visible; response, field, slab and electronics settings are behind a keyboard-operable explanation; invalid values receive an inline error before Run. |
| done for available datasets and models | Add saved-run comparison and statistical plot presets. | Result store/API, comparison UI, JSON export, event-clustered histograms, η-binned efficiency, matched relative-pT residual and survival renderers. | Comparison records any stored artifact digests, seeds and model/config differences; plots state sample, units, binning, denominators, clustered statistical intervals/errors and omitted systematics. Missing source digests remain null and are never synthesized. |
| implemented in source; packaged human accessibility validation unresolved | Complete keyboard, zoom/text-scale, reduced-motion, screen-reader and fallback-renderer behavior. | Workbench markup/JS/CSS and packaged UI checks. | No canvas-only action; reduced renderer is announced; task workflow documented. Human usability evidence requires packaged Windows builds, assistive technology and willing participants. |
| done for bounded starter workflows | Add reproducible experiment templates/cards. | Versioned template fixtures, UI starter cards, tutorial docs and exports. | Curvature, muon lifetime, PDG silicon mean-loss and field-comparison templates reproduce cited expected values within stated tolerances. |
| done | Repair web source-edit links and constrain Markdown/MDX rendering. | `web/HEPLab.Web/Pages/Docs.cshtml`, `Docs.cshtml.cs`, `SiteContentService.cs`, tests. | Every edit link resolves to an actual source; raw/unsupported MDX cannot inject executable HTML; TOC IDs match rendered heading IDs. |
| done for canonical guide and generated examples | Put evidence-scope explanations on technical/model/example pages. | `web/HEPLab.Web/Content/Docs/**`, reusable Razor component/partial. | Pages distinguish software parity, named-reference agreement, calibration and physics validation, linking exact evidence. |
| done — grouped config and synthetic result included | Add a guided first experiment and downloadable versioned Workbench config/artifact. | ASP.NET educational page/assets; Python config/artifact serialization. | Clearly static tutorial, synthetic labels and expected result/limits; no implication of remote simulation. |
| done for source and contract; deployment host remains a product decision | Establish one canonical web source and route/content contract checks. | `web/README.md`, `/site` ownership/build docs, CI/content tests. | Canonical source/build/deploy target declared; all nav/routes/anchors/examples/source links tested. Existing user migration edits must be preserved. |
| done — synthetic, named table, and recorded data with failed gate | Curate examples for analytic, reference-table and recorded-data analysis tiers. | Website gallery and checked-in fixtures. | Each example has visible source kind, provenance, validation status and limitations; recorded-data evidence is only included if a suitable clean artifact exists. |
| done for current chart families | Improve educational plots with statistical definitions and observed/expected context. | Analytic and collision captions expose source population, selection, units, bins, denominators, event-clustered/statistical errors and omitted systematics; CMS data charts add selected/total events, source, normalized-bin covariance, and correction/systematic omissions. | This is plot-definition coverage, not evidence for omitted effects or detector agreement. |

## P2/P3 — staged scientific extensions and release communication

| Status | Review recommendation | Implementation target | Required evidence / user-facing update |
|---|---|---|---|
| done — one-muon altitude/path survival only; no atmosphere/shower | Add a fixed-momentum educational atmospheric survival mode after the lifetime core. | Separate one-muon path/altitude calculation and UI template; no shower generator. | Compare to analytic survival; source atmosphere/path assumptions; label as a survival demonstration, not a cosmic-ray shower simulation. |
| done for bounded software models | Add curvature/sagitta comparison experiments across charge, momentum and field. | Versioned sweep spans four momenta, four uniform fields and both charge signs; an independent circle formula checks all 32 ideal cases and eight bounded OAE comparisons report diagnostic endpoint differences. | OAE differences have no field-measurement threshold; no run-era field or detector validation claim. |
| blocked (external dependency) | Add measured tail/straggling comparison and a pixel response prototype. | Only after pinned Geant4/CMSSW or public response fixtures exist. | Requires material-specific distributions, sensor thickness/pitch/noise/Lorentz drift/charge sharing and independent detector-response evidence. |
| blocked (external dependency) | Expose detailed CMS transport. | Optional separate CMSSW/Geant4 workflow. | Requires a clean supported installation, pinned geometry/field/GlobalTag/IOV/digitization, conditions access and independent boundary/material/response validation. |
| blocked (external dependency) | Expand matched CMS data/MC and systematic uncertainty analysis. | CMS analysis workflow and reports. | Requires matched certified data/MC, trigger/correction payloads, covariance model and untouched final sample. Existing measured data are not enough. |
| done — scientific and academic docs updated | Update professor demonstration, academic claims, roadmap, citations and user docs to match implemented status. | `08_ACADEMIC_PRESENTATION.md`, README, engineering/web docs and result UI. | Keep project classification educational; state exact verified scope and all unresolved external dependencies. |

## Worktree protection and final audit

- Preserve all pre-existing modified, deleted and untracked user files. Edit only the
  minimum required hunks in files already dirty.
- Do not overwrite old resonance artifacts. Retain them with an explicit
  target-dependent exploratory label and point production/UI evidence to v2 with its explicit failed status. A failed result
  remains visible as a failure and is never promoted to independent validation.
- Verify Python tests, Rust tests, desktop/web builds and the website content contract
  using repository workflows. Record each command and result here.
- Recheck all local Markdown/source links and inspect the final changed-file list so
  unrelated user work is not included.

## Final verification record — 30 October 2026

| Command / check | Result and scope |
|---|---|
| `uv run --project . pytest -q` | Full Python suite passed after implementation, including the worker packaging regression; repository-declared skips remain. One third-party Starlette deprecation warning is emitted by `fastapi.testclient`. |
| `uv run --project . python tools/run_verification_registry.py` | Passed equation, integration, curvature, table-domain, slab-ledger, lifetime and RNG checks. These verify named software submodels, not experimental detector agreement. |
| `uv run --project . python tools/build_site_examples.py` and `python tools/check_site_contract.py` | Generated the curvature sweep and three provenance-bearing examples; site contract passed with 19 navigation entries and 18 source pages. |
| `dotnet build web/HEPLab.Web/HEPLab.Web.csproj --configuration Release` | Passed with 0 warnings and 0 errors. ASP.NET is the canonical current website source. |
| Production web asset regression | Fixed the built-DLL asset manifest loading that caused empty CSS/JS responses despite HTTP 200. `python tools/check_site_runtime.py` passed for both Release build and publish output: four pages, seven assets checked against source with identity/gzip requests and correct MIME types, plus search JSON. Both commands now run in CI. Public deployment remains unverified. |
| Professional ASP.NET interface upgrade | Bootstrap 5.3.8 and local IBM Plex assets; reusable C# icons and Razor navigation/lab/gallery/preview components; redesigned shared interface and fixture-backed interactive 3D home view. Runtime coverage includes all 19 pages, local links/anchors, unique IDs/headings, fingerprinted assets, vendor hashes, field/curvature convention checks, and exact fixture provenance. Local browser checks cover desktop/mobile rendering, search, themes, offcanvas focus/dismissal, lab loading, gallery filters, and 3D camera controls. This is interface/software evidence, not an experimental or WCAG certification. |
| Frozen worker and Tauri release build | Isolated Windows PyInstaller worker build and IPC smoke passed; the Tauri `--no-bundle` release build passed with the fresh worker. No certified CMS ROOT sample pair was present, so its packaged library was correctly empty. The optional samples are required and checked when supplied. |
| Rust core | `cargo test --manifest-path kernels/physics-core/Cargo.toml --locked`: 17 passed. `cargo fmt --manifest-path kernels/Cargo.toml --all -- --check` passed. Tauri Clippy passed in the isolated stage with warnings denied. |
| Changed-scope Ruff | Lint passed and 22 implementation/test files passed `ruff format --check`. |
| Full repository Ruff | Reports six existing findings outside the changed implementation scope: one long line in `desktop/core/tests/fake_worker.py`, three in `src/heplab/cli.py`, and two in `tools/verify_wheel.py`. |
| JavaScript and Python compilation | `node --check` passed for `workbench.js` and `data-workspace.js`; Python `compileall` passed for `src/heplab`, `tools`, `tests` and `desktop`. |
| Scientific-review links | All 84 local links across 11 Markdown files resolve. |
| `tools/check_handbook.py` | Fails because eight engineering notes in the current docs tree lack the handbook-required Mermaid diagram. The malformed absolute source links in the desktop physics review were repaired to repository-relative links. |
| `mkdocs build --strict` | Fails with 70 warnings because the handbook `docs_dir`/nav excludes source files and review pages that its local links reference, and includes stale artifact links. The canonical ASP.NET site build and its dedicated contract check pass. |
| `git diff --check` | Passed; Git reports line-ending normalization notices only. |
