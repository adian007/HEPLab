# Desktop research workbench — Phase 0 baseline

Status: **Phase 0 complete; awaiting user confirmation before Phase 1.**
The application remains an educational, unvalidated workbench.

## Scope and preservation

Read the full [28 October audit](desktop-audit-2026-10-28.md) before making changes.
Inspected `git status` before repository changes and created branch
`codex/desktop-phase0-baseline` from
`eb91e368fc708ba3f9d3d018e3ea27b8987458a4`. Existing modified, deleted and
untracked files were retained. No production source, existing tests, generated
frontend, persisted user runs, runtime configuration or dependencies were edited.

This phase adds only this report, its
[compact evidence record](desktop-phase0-evidence-2026-10-28.json), and two
observational probes: `tools/desktop_phase0.py` and
`tools/desktop_phase0_browser.js`. The commit is titled
`Record desktop Phase 0 baseline for findings #1-#7`; it contains only those four
new files. There are no finding-fix commits in this phase. Test-first fixes belong
to subsequent, separately confirmed phases.

The initial checkout contains changes made after the audited UI snapshot.
Reproductions below concern that current dirty tree. They are not attributed to
the base commit alone. The probe recorded hashes of 79 dirty/untracked input files
before the worker/browser exercises. Final verification matched 78 of them;
`docs/engineering/desktop-shell.md` changed outside this phase's edits while the
probes were running. It was left untouched. All recorded application/test inputs
still match. This documentation drift limits the frozen-snapshot claim and is
recorded in the evidence JSON. No frontend build was necessary in Phase 0.

Raw evidence is retained in
`output/desktop-phase0-20261028-152134/`; no previous audit evidence was replaced.
The worker probes used distinct new source/packaged projects. The local browser
server used a third project on `127.0.0.1:8771`. Numerical and version fault
injections affected browser memory only, never persisted physical results.

## Baseline checks

| Check | Result | Scope |
| --- | --- | --- |
| `python -m pytest` | 172 passed, 1 skipped, 1 warning; 53.36 s | Entire Python suite; optional Rust-binding test skipped |
| Five audit test modules | 58 passed, 1 warning; 4.69 s | Exact original audit module set; log and JUnit retained |
| Source JSON-lines worker | Ideal and DY runs complete; invalid 1 GeV response rejected | Actual subprocess, isolated project |
| Packaged `heplab-worker.exe` | Same; saved run fully recovered after process restart | Existing Windows executable, not rebuilt |
| Response separation | Trajectories, material result and digits identical with/without response | Both workers, same seed/configuration |
| Browser reproduction | All seven probes completed; final attempt has zero automation errors | Edge/Playwright, shared source UI |
| Probe checks | Ruff check/format and JS syntax checks pass | New probe code; shared JS syntax also checked |

Audit modules: `test_desktop_worker.py`, `test_material_and_workbench.py`,
`test_physics_reference.py`, `test_cms_material_and_mass.py`,
`test_project_capabilities.py`.

Environment: Python 3.13; exact dependency versions are in the evidence record.
FastAPI 0.141.1 / Starlette 1.6.0 / httpx 0.28.1 emits:
`Using httpx with starlette.testclient is deprecated; install httpx2 instead.`
`httpx2` is absent. The warning is recorded and unsuppressed. Dependency/test-client
repair remains work for the next confirmed implementation phase; no shared Python
environment was changed to conceal the baseline.

Source and existing generated frontend hashes match:

| Asset | SHA-256 (both copies) |
| --- | --- |
| `workbench.js` | `f5d6868a657fcd597948ac5dfb3d4e8c9fab7ea9134ce83a0d94d039a4768cb5` |
| `index.html` | `7d24a68b040564e2a1d9ae94271b9bda48e3fc9367b4ed536df20c91d260c343` |
| `workbench.css` | `5e94d4ca107de88867345e92de7db07b183aa6a072b9285dd4dcc57f2cc8c5dc` |

Packaged worker SHA-256:
`bc13f928db6b264af17ddfa5003452c7c09a78c45e438d8d47b0c08996c9f435`.
Matching frontend files do not establish which resources were embedded into an
installed native executable. Native installed-app acceptance remains uncertified.

## Findings rechecked

### 1 — Original unconditional Pass no longer reproduces; trust gaps remain

Both browser badge paths pass a `1e-15 GeV` residual and fail an injected `0.5 GeV`.
Skip the already-fixed unconditional-pass defect.

The analytic badge labels both NaN and missing residuals **Failed**, not Unknown.
The generator badge labels NaN Failed and throws `TypeError` on a missing residual.
The generator cases are injected UI tests, not live collision results.
Analytic results do not record applicable conservation tolerances.

The current UI hard-codes analytic `1e-9 GeV` and generator `1e-6 GeV` absolute
thresholds. In contrast, `sim/pipeline.py` checks generator components against
`max(0.002 GeV, 2e-5 * total incoming beam energy)` and records that expression as
a string. Its comment and `sim-runtime.md` cite native ROOT rounding as the reason.
At 13 TeV that backend threshold is 0.26 GeV. The UI/backend disagreement is
source-confirmed; this phase does not endorse either threshold or alter it.
Absolute/relative numerical values, scale definitions, derivation, result metadata,
and Unknown handling still need implementation and tests.

### 2 — Recovery and Load setup now work; version contracts remain incomplete

Browser history retained all four observed entries across refresh. Opening a
persisted entry loaded its result and parameters. A saved v1 setup restored a
modified momentum from 30 to 45 GeV. Invalid seed 0 was rejected with a readable
message. Both source and packaged worker restarts returned a saved run identical
to its originally committed result through `runs.get`.

Skip rebuilding those working recovery paths. Remaining gaps: an injected future
`heplab-workbench-result-v999` opens without refusal; a v999 setup is rejected with
the generic message `Choose a HEPLab setup JSON file`, which does not name the
version problem. Unknown setup parameter keys are silently accepted and discarded.
Supported legacy setup/result migrations and incompatible-version refusal need
explicit tests. Native Open dialogs were not exercised.

### 3 — Original recall mismatch and hidden warning no longer reproduce

After a 45 GeV run, a 20 GeV run and recall of the first run, both draft and result
show 45 GeV. Editing the draft back to 20 leaves the 45 GeV result with
`Parameters modified · showing previous result` visibly displayed at 1100×680.
The screenshot was visually inspected. Skip those original fixes.

The existing recall action automatically replaces the draft. There is no separate
“Use this run's settings” action. History labels include momentum, seed and backend
once metadata is loaded, but omit timestamp and visible ID; the full ID is a
tooltip. Newly discovered runs initially show only an ID prefix until opened.
The requested immutable-result/editable-draft interaction still needs a deliberate
implementation in Phase 2.

### 4 — Original invisible response no longer reproduces

The browser table shows 45.000 GeV truth pT beside sampled 45.418 and 45.957 GeV.
The inspector exposes accepted/lost state, efficiency, scale, resolution and scope.
The analysis workspace overlays truth and sampled response distributions. Both
worker probes confirm transport, material and digits remain unchanged by enabling
this independent branch. Skip rebuilding this output.

The numerical fit domain is not exposed in the inspected table/inspector; the
inspector gives the population scope instead. A dedicated regression proving the
response cannot be applied twice is still required. Existing
`test_workbench_samples.py` covers sampled observables and loss state but does not
provide that exact regression. No calibrated CMS response is established.

### 5 — Original “In range”/1 GeV rejection no longer reproduces; failure state remains

Selecting transverse-pair DY response at 1 GeV displays a local
`requires momentum ≥ 5 GeV/c` message and Invalid values in checks. Clicking Run
sends zero submissions. Skip rebuilding that client feedback.

Run nevertheless remains **enabled** while the known constraint is violated.
Rules are duplicated in JS instead of published by the backend. In a separate
in-memory failed-submission injection, status becomes FAILED while the visible
result still says **Result up to date** and remains exportable. It does not say
“previous successful run.” This is a UI recovery probe, not evidence of an engine
failure. Both actual workers authoritatively reject the invalid configuration.

### 6 — Availability notice improved; actionable help and identity gaps reproduce

Both workers report Rust and PYTHIA8/DELPHES unavailable. Collision selection
disables Run and now displays a nearby notice. Skip adding a notice that already
exists.

The notice still says to set `HEPLAB_SIM_PREFIX`, has no help link, and supplies no
desktop installation flow. The simulation option lacks an unavailable label.
The document title changes to **Drell–Yan collisions** while the earlier analytic
result remains visible. Disabled Previous/Next buttons have empty tooltips for
the single-event fixture. These remaining cases reproduce in the browser.

### 7 — Result identity improved; full export provenance remains incomplete

The result export now has a run-ID filename, e.g.
`heplab-b907ef89ef8b4d3ee334f9b1-event-0.json`, and a v2 artifact object with run ID,
HEPLab version, creation timestamp and configuration hash. Skip rebuilding these
existing fields.

There is no complete app/worker/build/source-revision-and-dirty identity envelope.
Requested/effective configurations and validation scope are not collected into
the requested provenance contract. The direct worker transverse fixture still
records 100 requested events and 1 effective event. Geometry/reference hashes
exist in nested model data; this is partial provenance, not absence of all hashes.
Setups still download as **heplab-setup.json** and contain only v1 format and
parameters, without run/build/source identity. Versioned backward-compatible
envelope design requires user confirmation before changing a format other tools
may read.

## Existing analysis inventory

Inventory is based on implementation reads and the passing suite, not on roadmap
claims or a newly certified real-data workflow.

| Capability | Existing implementation | Practical limits / desktop exposure |
| --- | --- | --- |
| Dataset discovery and loading | `catalog.py`, `io/xrootd.py`, `readers/nanoaod.py`, CLI `_read_events` / `fetch` / `run` | Manifest-driven NanoAOD ROOT streaming; local JSON schema-v1 events; bounded samples and source ranges. Catalog listing exists in IPC, but no desktop dataset analysis flow. |
| Certification and caching | `io/certification.py`, `io/cache.py` | Lumi masks, source-range/cache identity, committed JSON or Parquet chunks. Remote checksums can be declared-only; not every fetched byte is independently checksum-verified. |
| DELPHES input | `readers/delphes.py` | ROOT truth/reconstructed objects, generator weights, absent measurements preserved. Data/MC isolation definitions differ and must not be silently treated as equivalent. |
| CMS AOD | `readers/aod.py` | Explicit `NotImplementedError`; unavailable. |
| Selections and cutflows | `analyses/dimuon/run.py`, dimuon YAML config | Muon pT/eta/isolation, opposite charge, mass window, trigger/certification gates; candidate policies and bounded output; integer and weighted cutflows. No desktop selection editor. |
| Weighted histograms | `physics/reference.py::WeightedHistogram`, dimuon processor | Signed weights, compensated sums, sumw2, flow bins, candidate/event variance accounting. Current desktop synthetic plots are raw unweighted counts, separate from this analysis processor. |
| Mass fits with uncertainty | `stats/fits.py`, CLI `fit` | CPU iminuit truncated Gaussian+uniform teaching model; errors, covariance, EDM and fit validity. Rejects nonunit weights, clustered candidates and GPU requests. No coverage or detector-model certification. |
| Systematics | Dimuon `_settings`, config `systematics: []` | Nonempty systematics explicitly raise an unsupported-model error. No implemented variation orchestration or systematic covariance. New supported models need approval and validation. |
| Data/MC comparison | `analyses/closure.py`, CLI `closure`, read-only API `/closure/{data}/{sim}` | Compatible normalized shapes, covariance and ratio variance; requires matching analysis/observable/semantic identity and known isolation. Rejects clustered candidates; no systematic covariance or absolute-luminosity comparison. Not exposed through desktop IPC. |
| Persistence/provenance | `io/artifacts.py`, `io/provenance.py`, CLI `run` / `fit` | Immutable atomic analysis publication, source/config/manifest/certification/range hashes; fit child references parent hash. Bench identity is partial; closure CLI currently writes a report directly. Reuse capabilities without assuming all outputs have identical provenance guarantees. |
| Other existing workflows | `lab/replay.py`, `lab/daq.py`, `lab/profile.py` | Hardware replay/efficiency path and IPC operations exist; distinct from the requested dataset-to-fit loop. |
| Parallel execution | `processors/base.py` | Processor protocol; no implemented coffea/Dask analysis executor in this module. |

Reusable core work is substantial. Phase 4 should expose these implementations,
with explicit unsupported states and new systematics work, after an approved
design note. The synthetic desktop “Run analysis” view is not the requested
real-dataset research loop.

## Evidence boundaries and next decisions

**Known:** the Python suite passes; recorded browser behaviors reproduce; both
actual worker processes preserve and reopen new isolated results; source and
generated frontend bytes match; missing engines are reported honestly. The final
probe completed without automation errors. These are numerical/software checks,
not experimental validation.

**Inferred:** shared UI logic likely has the same behavior in the current desktop
frontend. Matching generated files support this inference but do not certify an
installed build or WebView2 interaction.

**Still unvalidated:** native dialogs and complete tour; genuine long-job native
Stop; worker-crash UI/restart; install/upgrade/uninstall and clean profile; memory
over long sessions; native minimum window; live collision navigation; real-data
loop on a user-approved dataset; clean tagged reproducible release.

The first browser attempt hit Playwright `route.fulfill: Route is already handled`.
It is an automation failure, not an app bug. The corrected probe uses temporary
browser-memory API substitutions, restores them and completes all seven cases.
The final reusable probe was checked again with explicit output-path configuration;
all seven cases completed with zero automation errors. Both successful evidence
sets are retained, in `browser-attempt2/` and `browser-final/` respectively.

Before Phase 1, confirm proceeding with the **remaining** finding 1/2 gaps and the
dependency warning. Tolerance policy needs an explicit decision before changing
physics-meaningful gates: analytic roundoff should have a documented numerical
error budget; generator acceptance must account for stored ROOT precision and
must use the same recorded criterion in worker and UI. This phase neither selects
new tolerances nor changes existing ones.

Later decisions remain deferred to their phase gates: export compatibility
contract; Phase 4 design and real dataset; redistribution/license/size/platform
choices for PYTHIA8/DELPHES/Rust; clean tagged release. Nothing has been bundled,
published, installed, upgraded or uninstalled here.

## Reproducing the observations

Choose a fresh evidence directory for every run. From the repository root:

```powershell
python tools/desktop_phase0.py capture --output output/desktop-phase0-new
python tools/desktop_phase0.py worker --output output/desktop-phase0-new
python tools/desktop_phase0.py worker --output output/desktop-phase0-new --binary desktop/src-tauri/target/x86_64-pc-windows-msvc/release/heplab-worker.exe
python tools/desktop_phase0.py serve --output output/desktop-phase0-new --port 8771
```

Keep that isolated server running and use another terminal:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=heplab-phase0 open 'http://127.0.0.1:8771/?phase0-output=D:/HEPLab/output/desktop-phase0-new/browser' --browser msedge --headed
npx --yes --package @playwright/cli playwright-cli -s=heplab-phase0 snapshot
npx --yes --package @playwright/cli playwright-cli -s=heplab-phase0 run-code --filename tools/desktop_phase0_browser.js
python tools/desktop_phase0.py verify-inputs --output output/desktop-phase0-new
```

The browser script requires the isolated port and an explicit fresh output path.
The capture and worker commands refuse existing destinations. The browser probe
records observations; it deliberately does not encode defects as desired behavior.
The new scripts are baseline tools, not the Phase 3 native acceptance harness.
