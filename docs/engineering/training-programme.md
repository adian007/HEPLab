# HEPLab Education and Training Programme

This operator curriculum is driven by
[curriculum.json](../../src/heplab/training/curriculum.json). Module and step
ids are stable contracts for progress records. The desktop, handbook and
notebook gallery must map to these ids rather than teaching unverified GUI
buttons.

## Shared conventions

- **GeV**: HEPLab uses GeV for momentum and invariant mass. Momentum is shown
  as GeV/c, invariant mass as GeV/c².
- **Synthetic fixture**: generated Z→μμ teaching data is an educational
  simulation. It is not CMS Open Data or a detector calibration.
- **Data**: CERN/NanoAOD input is recorded data only when the record declares
  `is_data`, the reader mode and certification are compatible.
- **Runtime-gated**: PYTHIA8/DELPHES and native views are not complete until
  runtime discovery or the corresponding native backend is verified.
- **Completion**: passing a superficial click is insufficient. Evidence must
  be a real application state, public result, immutable artifact or replay
  report.

## Module 1 — Getting Started with HEPLab

**Scope:** 45 minutes. **Prerequisites:** Python 3.12, access to a local
terminal and optional Jupyter environment.

**Learning objectives**

- Verify a HEPLab installation and public API version.
- Identify implemented and unavailable Workbench areas.
- Open or create a project and understand local, relative project paths.
- Understand that the native Qt shell is not yet a substitute for the
  JSON-lines compatibility worker.

**Instructions**

1. Run `python --version`, then `python -m pip install -e ".[analysis,notebook]"`.
2. Run `heplab --version` and `python -c "import heplab; print(heplab.API_VERSION)"`.
3. Open the C++20/Qt 6 Workbench only where that build is installed.
4. In **Learning / Documentation**, confirm the eight-module catalogue and
   the Z-boson verified workflow.
5. Do not interpret unavailable navigation sections as broken controls; they
   are explicitly labelled until native capabilities are integrated.

**Practical exercise**

Create a setup note containing package version, API version, operating system,
Python executable and any unavailable optional extras.

**Common mistakes**

- Treating a package import as proof that NumPy, ROOT or imininuit is installed.
- Using a future API version or private module as public interface.
- Expecting the historical Tauri shell or native Event Inspector controls.

**Troubleshooting**

- Missing `heplab`: activate the environment used for installation.
- Missing analysis extras: install `heplab[analysis]`.
- Unavailable native build: use the Python/CLI/workbench compatibility path
  and record the native build gate.

**Measurable completion**

The student records the real `heplab --version` and API `1`, can identify the
current environment, and opens or opens a project through a supported local
interface.

## Module 2 — Running Your First Simulation

**Scope:** 60 minutes. **Prerequisites:** Module 1.

**Learning objectives**

- Select the supported Z-boson teaching workflow.
- Configure muon pT, relative isolation and opposite charge.
- Start, poll and cancel a desktop/worker job.
- Save and verify the `heplab-z-boson-result-v1` artifact.

**Instructions**

1. Use the bundled Z preset from
   `web/HEPLab.Web/wwwroot/examples/z-boson-preset.json`.
2. Preview it and confirm the synthetic scope and event 1.
3. Use 20 GeV/c minimum pT, 0.15 maximum relative isolation and
   opposite-charge pairing.
4. Submit the run through the Workbench or desktop IPC operation
   `jobs.submit`.
5. Poll `jobs.get`; only `completed` has a publishable result.
6. Download the JSON and HTML exports. Verify the JSON's checksum with
   `heplab.load`.

**Conceptual questions**

- Why is `opposite charge` a test for neutral-pair selection, not proof of Z
  identity?
- Why can the fit uncertainty be statistical but the Z mass reference be a
  published particle-property value?
- What changes in the fit if muon momentum resolution changes?

**Common mistakes**

- Presenting practice data as CMS data.
- Interpreting every Z-like pair as a truth Z boson.
- Calling `completed` proof of detector calibration.

**Measurable completion**

The replay has 4,000 practice events, 2,155 selected pairs with the default
cuts in the verified baseline, all Z lab checks pass, and checksum replay
succeeds. Values must be treated as environment-specific unless independently
reproduced.

## Module 3 — Understanding the Event Inspector

**Scope:** 45 minutes. **Prerequisites:** Module 2.

**Learning objectives**

- Distinguish event truth, generated particles and reconstructed muons.
- Inspect four-momenta and their units.
- Identify planned native visualization states without inventing controls.

**Verified operations**

The worker exposes `jobs.event(job_id, index)` for bounded event retrieval.
The web compatibility display is not a native Qt implementation. Native 2D/3D
camera and geometry-layer controls are not complete.

**Instructions**

1. Complete a Z-boson run.
2. Retrieve event 1 or a different bounded event index.
3. Inspect `EventInfo`, `Muon` records and generator labels.
4. Compute one invariant mass in Jupyter for independent confirmation.

**Conceptual questions**

- Which fields describe measured/reconstructed objects and which describe
  generated truth?
- Why does a detector surface intersection differ from a generated trajectory?
- Why must event provenance remain linked to the parent run artifact?

**Measurable completion**

The student explains truth versus reconstruction, reports units correctly, and
links at least one event view to the parent artifact. Native controls are
considered complete only after implementation and screenshot evidence.

## Module 4 — Working with Simulation Results

**Scope:** 45 minutes. **Prerequisites:** Module 3.

**Learning objectives**

- Interpret cutflow stages and efficiency.
- Read histogram entries, edges, counts and units.
- Compare immutable run records and export offline HTML/JSON.

**Instructions**

1. Open the Z result and inspect `cutflow`, `histogram`, `fit` and
   `progress`.
2. Report raw entry counts and stage efficiencies, not only a peak.
3. Export the JSON and HTML result.
4. Reload JSON with `heplab.load` and verify checksum fields.

**Exercise**

Change isolation to 0.10 and rerun from the same seed. The baseline record
from the verified Z workflow should lose pairs rather than increase unless
the implementation or configuration differs; stop and investigate mismatches.

**Measurable completion**

The student names the selected count, can reproduce its cutflow, and produces
a checksum-verifiable export.

## Module 5 — HEPLab with Python and Jupyter

**Scope:** 75 minutes. **Prerequisites:** Module 4.

**Learning objectives**

- Install and use `heplab.run`, `heplab.read`, `heplab.load`, `heplab.fit_peak`
  and `heplab.export_html`.
- Reproduce the Z result with public APIs.
- Use NumPy/awkward/uproot/Matplotlib only as optional analysis dependencies.

**Instructions**

1. Run `notebooks/gallery/01_environment_verification.ipynb`.
2. Run `02_first_event_inspection.ipynb`.
3. Run `03_dimuon_spectrum.ipynb`.
4. Run `04_fit_and_reproducible_report.ipynb`.
5. Optionally open the existing guided Z notebook.

**Measurable completion**

Cutflow and histogram replay exactly or within documented floating-point
rules, the public artifact reload passes digest verification, and fit output
is labelled as statistical and synthetic.

## Module 6 — Using CERN Open Data

**Scope:** 90 minutes. **Prerequisites:** Module 5.

**Learning objectives**

- Discover a manifest through the catalog.
- Distinguish `.json` teaching events from `.root` NanoAOD.
- Apply recorded-data certification and keep simulation flags separate.

**Instructions**

1. Use `heplab catalog list` or `datasets.list`.
2. Inspect only a manifest whose local fixture, checksum and certification are
   available.
3. Use `heplab.read(path, simulation=False, format="nanoaod")` for recorded
   data and `simulation=True` for declared simulation.
4. Do not silently relabel a NanoAOD file; the reader refuses a simulation
   file read as data.

**Limitations**

Broad held-out CMS validation is not complete. A 100-event smoke or fixture
does not certify a full physics measurement.

**Measurable completion**

The student reports source, manifest, certification and simulation/data mode,
and can execute a checked-in reproduction for any supplied held-out fixture.

## Module 7 — Advanced HEPLab Workflows

**Scope:** 120 minutes. **Prerequisites:** Module 6.

**Learning objectives**

- Discover external PYTHIA8/DELPHES capability, never assume availability.
- Compare only runs with identical registered process and seeds.
- Explain statistical uncertainty, detector approximations and limitations.

**Instructions**

1. Call `engine.capabilities` and `simulation` from the Workbench session.
2. If the simulation runtime is unavailable, stop and report the missing
   pinned runtime. Do not substitute a synthetic Z run.
3. If available, use only the registered Drell–Yan mumu process and pinned
   CMS card.
4. Compare invariant-mass bins and event weights in public artifacts.

**Measurable completion**

The student produces no backend claim without a capability record and
documents versions, seed, event count, cross-section convention and
approximation limitations.

## Module 8 — Independent HEPLab Project

**Scope:** 180 minutes. **Prerequisites:** Module 7.

**Student workflow**

1. Choose the Z-boson synthetic lab unless the required recorded-data fixture
   and certification are available.
2. Declare hypothesis, configuration, scope and expected observables.
3. Execute via Workbench, CLI or public API.
4. Inspect at least one event and the cutflow/histogram.
5. Export the result and replay it in Jupyter.
6. Produce a one-to-three page report.

**Report checklist**

- HEPLab and API versions.
- Exact environment and dependencies.
- Experiment, seed and event count.
- Input digest or manifest/certification.
- Selection and binning.
- Statistical versus detector-systematic uncertainty.
- Limitations and whether the result is synthetic, fast simulation or data.
- Exact replay command.

**Measurable completion**

A fresh environment can replay the artifact, the report names the same
provenance, and no unsupported detector, CMS or measurement claim appears.

## Screenshot and accessibility status

Screenshots are not marked complete for a GUI until captured from a build that
contains the corresponding native control. The Qt shell test currently verifies
the native title and navigation shell only; it does not certify a simulation,
event viewer or screenshot. Future screenshot assets must include build SHA,
captured state, resolution and accessibility text.
