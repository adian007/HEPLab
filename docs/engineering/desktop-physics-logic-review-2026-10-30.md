# Desktop Workbench physics and logic review — 2026-10-30

## Focus

This review is specifically about the desktop HEPLab Workbench: the user-facing configuration and run lifecycle, worker-to-engine path, analytic bench calculations, collision workflow, persisted results, and event display. The public website is out of scope here.

## Research conclusion: what “real CMS-like physics” requires

The current desktop has two different simulation levels that should stay distinct:

- The Rust/Python bench is a deterministic educational model: vacuum propagation, ideal or fixed OAE field, one silicon slab and a parameterized response. It is useful for controlled demonstrations, but cannot be made into realistic CMS transport just by refining the helix renderer.
- The existing PYTHIA8→DELPHES mode is the appropriate fast-simulation route for analysis and event-level detector effects. Delphes describes itself as a fast multipurpose detector-response simulation with simplified tracking, calorimeters and muon system. It is not the same as detailed detector transport.
- The credible detailed CMS path is CMSSW configuration with the matching detector geometry, magnetic field and conditions, using Geant4 for particle transport, then the relevant digitization/reconstruction chain. CMS documentation says detector geometry and magnetic field are required simulation components; a Global Tag bundles condition payloads and their IOVs, and should be explicitly selected for the dataset/era. A single nominal 3.8 T value is not a substitute for run-era conditions.
- For material response, the PDG review describes the mean Bethe energy loss and the limits of interpreting that mean as the typical energy loss; Geant4 handles continuous energy loss plus explicit secondary production above thresholds, and uses multiple-scattering models with non-Gaussian hard-scatter tails. A single Gaussian Highland draw and fixed mean deposit cannot reproduce those details.

**Recommended product boundary:** keep the current bench as an explicitly educational mode; keep Delphes as fast simulation; add a separate CMSSW/Geant4-backed “CMS full simulation” mode only if the required runtime, geometry, conditions, digitization and validation can be packaged and reproduced. Do not silently upgrade claims based on screenshots or a field-map swap.

Research sources: [Geant4 electromagnetic and tracking processes](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/TrackingAndPhysics/physicsProcess.html), [Geant4 mean energy loss](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/energy_loss/enloss.html), [Geant4 multiple scattering](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/elastic_scattering/msc.html), [CMS simulation geometry and magnetic field](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookChapter6), [CMS Open Data condition database guide](https://opendata.cern.ch/docs/cms-guide-for-condition-database), [PDG 2025 passage of particles through matter](https://pdg.lbl.gov/2025/reviews/rpp2025-rev-passage-particles-matter.pdf), and [Delphes project description](https://delphes.github.io/).

## Overall assessment

The desktop app has a solid educational workbench foundation, but it is not yet a validated detector simulator. Its strongest decisions are explicit model maturity labels, deterministic addressed random numbers, a Python reference path alongside Rust, immutable run artifacts, capability/preflight information, and clear distinction between predicted surface crossings and measured hits. The most important improvement is to keep the UI and scientific interpretation aligned with what each backend actually calculated, then expand physical fidelity only with independent reference closure.

## What the desktop app does

1. Tauri launches the packaged Python worker over bounded JSON-lines IPC. The Rust shell and Python worker validate the operation protocol.
2. The browser workbench submits a strict `RunConfig` to the durable local job queue.
3. In analytic mode, `bench()` creates a declared opposite-charge muon pair (one pair or a bounded angular sample), propagates the tracks through a vacuum field model, applies one illustrative silicon slab, and digitizes the slab deposit. A separate optional response branch samples reconstruction efficiency and pT response.
4. In collision mode, the app invokes PYTHIA8→DELPHES, analyzes reconstructed outputs, and builds a display from reconstructed muon kinematics.
5. The result and provenance are written as a versioned, immutable artifact. The event display draws track polylines and predicted detector-surface crossings over detector reference geometry.

Useful implementation entry points: [desktop worker](../../src/heplab/desktop/worker.py), [Workbench job/configuration logic](../../src/heplab/server/workbench.py), [physics engine](../../src/heplab/physics/engine.py), [reference calculations](../../src/heplab/physics/reference.py), [detector transport](../../src/heplab/physics/detector.py), [CMS field model](../../src/heplab/physics/cms_field.py), [material model](../../src/heplab/physics/material.py), [Rust response kernel](../../kernels/physics-core/src/response.rs), and [Workbench renderer](../../src/heplab/server/static/workbench.js).

## Findings

### High — Resonance selection can bias the validation comparison

The offline CMS resonance regression in `tools/build_cms_resonance_validation.py` selects an opposite-charge candidate by closeness to the reference PDG mass, then uses the chosen masses to report closure. This does not govern the analytic bench's generated pair, but it is relevant to the desktop's displayed reference-validation evidence: choosing with the target value can sculpt the distribution toward that same target and make the comparison look better than an independent test. The code/doc explicitly describes the closest-to-target policy.

**Fix:** use mass-independent muon quality/trigger/vertex selection, or fit all combinatorial candidates with a declared event-level model. Freeze the selection before unblinding the validation mass, then compare on an independent held-out sample. Until then, label this view as a frozen-sample regression, not independent detector calibration.

### Medium — Keep the reconstruction-response branch visibly separate from the drawn track

In `bench()`, `response_model="delphes_reference"` creates `reference_response` from the original truth state as a separate truth-to-object branch. It does not replace the track's displayed trajectory, material state, or digit; the renderer draws `track.points`, while sampled pT is shown in properties/tables and histograms. The code records this distinction in a scope string, but users can still read “Tracking response” as a reconstructed trajectory or detector hit model.

**Fix:** name it “reference response overlay” or “sampled reconstruction observable”; show a separate accepted/lost object state alongside truth in the inspector; mark that the event display remains the truth/bench path. Keep measured data, simulated hits, predicted crossings, and smeared objects as separate visual layers with distinct legends.

### Medium — Tree, table, inspector, and canvas selection lose synchronization

For recorded CMS events, `selectObject()` updates the inspector for jets/electrons/photons/MET and clears the particle table selection, but it does not clear the old muon button's selected/pressed state or highlight the chosen object in the viewport. Canvas hit-testing only considers `screenTracks`, which is populated from muon tracks, not the other display objects. This conflicts with the GUI design's shared selection model and can leave two parts of the interface describing different selected objects.

**Fix:** represent each selectable display object with one stable typed identity, then synchronize viewport highlight, table state, tree state, and inspector from a shared selection function. If an object is intentionally not canvas-pickable, still clear stale state and mark the table/inspector selection consistently.

### Medium — Event display for collision events is an IP-based extrapolation

`muon_display()` builds a new state at `(0,0,0)` from each muon's pT, eta and phi, then propagates it through the ideal uniform-solenoid guide model. For PYTHIA/DELPHES events this is an explanatory extrapolation from reconstructed kinematics; it is not the track fit's original vertex, DELPHES hit geometry, or a set of measured detector hits. The function and UI text already say “IP-assumed” and “predictions, not measured hits,” which is good disclosure.

**Fix:** retain those labels next to the canvas and in exports. Where the input contains a reconstructed vertex or hit-level coordinates, render those separately instead of silently substituting the interaction point. Add a “display model” panel showing source coordinates, field model, geometry hash, and crossing method for the selected event.

### Medium — Detector transport is scoped and internally coherent, but far from full detector response

The analytic path is vacuum propagation in an ideal solenoid (or a fixed nominal CMS tracker OAE field inside its validity region), a single silicon slab, deterministic mean loss, Gaussian Highland core, and threshold/noise/saturation digitization. Other displayed detector surfaces add no material. The CMS field is not resolved by data-taking run/IOV. This means the picture is useful for teaching curvature, intersections and a simple energy ledger, but it cannot reproduce realistic multiple scattering tails, straggling, secondaries, showers, detector inefficiency/occupancy, or calibrated hit patterns.

**Fix:** keep each unsupported effect stated at the point of use. Prioritize a conditions-aware field and geometry/material navigator, then validate path and momentum at boundaries, energy transfer, and response against an independent Geant4/CMSSW reference. Add stochastic loss, secondaries and detector response only with independent reference datasets and held-out closure. CMS detector structure and PDG stopping-power theory are useful references, not substitutes for end-to-end validation: [CMS detector overview](https://cms.cern/news/detector-overview), [PDG passage of particles through matter](https://pdg.lbl.gov/2024/reviews/rpp2024-rev-passage-particles-matter.pdf).

### Medium — Check replay's physical-time presentation against its animation clock

The replay clock advances by `4 m/s × selected speed` in `event-display-gl.js`, while the overlay reports `t ≈ s/c`. The animation is intentionally time-compressed, but that is not stated beside the replay control; the numeric flight-time caption can be mistaken for the animation's elapsed wall-clock time. Also, the simulation records crossing markers in physical path coordinate (`crossing.path_m`), while replay computes its track clock from straight chord lengths between sampled points in both the Canvas2D and GL renderers. Since a helix arc is longer than its chords, markers can appear slightly later than the track reaches the same surface. The code computes actual beta-dependent crossing times, so `s/c` is only a light-speed approximation.

**Fix:** use the trajectory's authoritative `path_m` coordinates for track interpolation and crossing markers, sharing one path coordinate through both renderers. Label replay “accelerated path replay”; call `s/c` a light-speed approximation or use each track's computed `time_ns`. Keep animation rate out of any physics quantity or artifact.

### Medium — Aimed live preview can pass a response sample outside its calibration domain

`RunConfig` checks the 5 GeV pT minimum for the angular response sample, but the live preview accepts aimed `eta` through ±2.4 and substitutes an aimed transverse pair. For a 5 GeV momentum at |η|=2.4, pT is only about 0.90 GeV, below the response calibration's 5 GeV lower bound. The lower-level calibration call then fails after preview starts rather than returning an input-specific preflight explanation.

**Fix:** when the preview requests the reference-response branch, validate `pT = |p|/cosh(η) ≥ 5 GeV` before computing, and explain the allowed η/momentum range in the controls. Keep the current calibration's documented pT-local limitations visible.

### Medium — Event export mixes run-level and current-event data without a distinct schema

`Jobs.event()` returns the run summary and aggregate analysis alongside the requested event's tracks. The UI replaces its displayed result with that response when navigating and exports the whole object as `...event-N.json`. The file therefore combines run-level analysis/artifact metadata with one event's track collection, and the export action does not identify this hybrid contract. The original complete run artifact remains immutable on disk, but the downloaded JSON is not clearly “run” or “event.”

**Fix:** offer separate “Export full run” and “Export current event” actions. Give each a versioned envelope with explicit `run_id`, `event_index`, `scope`, and schema, and ensure the full-run export always reads the immutable original artifact.

### Low — Duplicate worker operation mapping entry in the working changes

`src/heplab/desktop/worker.py` contains two identical `"jobs.list"` entries in its handler mapping. Python keeps the later one, so this is redundant rather than a runtime failure.

**Fix:** remove the duplicate and keep the mapping one-to-one with `operations.json`.

### Low — Canvas2D fallback capability note is inaccurate

`docs/engineering/gui-design.md` says the Canvas2D fallback draws only muons for recorded CMS events. The current fallback also draws detector outline layers and some reconstructed-object geometry; it is a lower-fidelity painter-style rendering without WebGL depth/transparency, rather than a muon-only view.

**Fix:** document the actual fallback feature set and show a small “reduced renderer” status when active. Keep both renderers' object identities, labels, and selection behavior consistent.

## Logic and calculation checks that look sound in this path

- Opposite-charge, back-to-back momenta are constructed as a declared test pair; it is explicitly not represented as a collision event.
- The positive lognormal response conversion is mathematically consistent: for coefficient of variation `r`, the log-width is `sqrt(ln(1+r²))`. The implementation writes this as `sqrt(2 ln(hypot(r,1)))`, which is equivalent because `hypot(r,1)=sqrt(1+r²)`. Calibration then uses `exp(log_bias + sigma²/2)` with a mean-normalized lognormal draw. Do not “simplify” this by deleting the factor of 2 without changing `hypot` to `1+r²`.
- The single-slab path applies a material state update and records an energy residual. It is a declared approximation; the ledger should not be mistaken for a full detector transport conservation audit because medium recoil and all other material are absent.
- In collision analysis the GUI describes highest scalar-pT pair selection before the mass cut, which avoids the target-mass candidate selection used by the separate reference-regression builder.
- The display explicitly presents surface intersections as predicted crossings rather than sensor hits. That naming should remain invariant through event tables and exports.
- The workbench's `RunConfig` constraints generally match UI gating, and live preview uses the same `bench()` calculation path as a saved analytic run.
- The sampled lognormal response formula is correct: `sqrt(2 ln(hypot(r,1))) = sqrt(ln(1+r²))`; with mean-normalized draws its coefficient of variation is `r`. The Python reference, Rust kernel, and calibration conversion are consistent here.

## Recommended desktop roadmap

1. Keep the current reference/educational boundary prominent in preflight, result header, table, and exported artifact.
2. Clarify truth, sampled response object, simulated hit, measured object, and predicted crossing as different entities; link selection across canvas, tables and inspector.
3. Fix the validation-selection leakage before treating the reference-validation panel as independent evidence.
4. Add deterministic distribution closure tests for the response parameters (mean, width/CV, efficiency, ordering and seed behavior), plus Python/Rust parity on identical addressed draws.
5. Use frozen independent Geant4/CMSSW reference fixtures to grow from ideal trajectories to field/material navigation and response.
6. Run representative desktop tasks on packaged builds, including keyboard-only, screen reader, narrow-window and renderer-fallback workflows. Treat this as separate from numerical correctness.

## Review limits

This was a source and documentation audit, not an independent physics validation or complete user study. The local ASP.NET site build performed in the broader project review is unrelated to desktop physics. No production deployment was performed, and no full test suite was run for this desktop-focused review.

## Work started after the research review

- Live aimed previews now reject reference-response requests outside the calibration's `|eta| < 2.4` and `pT >= 5 GeV` domain before entering the simulation path.
- Both event-display renderers now use the trajectory's physical `path_m` samples when available, so replayed tracks and crossing markers share a path coordinate. Geometry-only display paths retain the chord-length fallback.
- Selecting a reconstructed CMS object in the table now clears stale selected-muon state and marks the chosen row; selecting a muon clears object-row selection.
- Removed the duplicate `jobs.list` worker handler entry from the pending local diff.
- No physics model was promoted to validated or full-detector status. The CMSSW/Geant4 route above remains a distinct future backend requiring source-era conditions, reproducible packaging and reference validation.

These changes were not run through the test suite in this pass.
