# Native simulator GUI design

## Review of the supplied notes

The notes combine standards, examples from working projects, and the author's
toolkit recommendations. They provide design input for HEPLab. Several source
labels in the notes lack links, so claims about prevalence, official adoption,
and the reasons behind migrations need separate evidence. Qt with
OpenGL is one supported desktop path in Geant4. Phoenix demonstrates an
independent web event-display path. These examples establish precedent for
multiple toolkits for particle physics. [Geant4 visualization drivers](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/Visualization/visdrivers.html) · [HEP Software Foundation visualization white paper](https://arxiv.org/abs/1811.10309) · [Phoenix source](https://github.com/HSF/phoenix)

ISO 9241-110 provides general interaction principles for evaluating the student
workflow. ISA-101 addresses industrial operator displays. The idea of a written
HMI philosophy transfers to HEPLab as an explicit hierarchy for run state,
results, and scientific scope. An educational simulator has a different
operating context from an industrial control room. [ISO 9241-110](https://www.iso.org/standard/75258.html) · [ISA-101 standards](https://www.isa.org/standards-and-publications/isa-standards/isa-101-standards)

## Interaction requirements

| Practice from the notes | HEPLab behavior | Acceptance |
| --- | --- | --- |
| Event-by-event navigation and linked projections | In an event-capable workspace, the event ID and selected object stay stable across the detector tree, XY/XZ views, 3D view, and table. Geometry toggles change visibility only. | Select an object from a table and identify the same object in both views. Step to the next event and clear stale selection. |
| Task-oriented display hierarchy | Put the source and scope beside the main result. Place controls near the affected view, with explicit units, cuts, and a visible path to provenance. | From an exported result, identify the event source, selection, units, fit uncertainty, and checkpoint count without opening the raw JSON. |
| Use display space for evidence | Use a chart and a table backed by the same saved bins. Provide keyboard navigation and use text alongside visual status. | Switch from cutflow to mass bins by keyboard and read the counts without using the chart. |
| Error tolerance | Keep the last successfully opened result visible if a new file is malformed. Explain the problem near the file-open action. | Open a valid export, then a malformed file, and check the active plot survives. |
| Prototype evaluation | Observe students using the complete predict, configure, run, inspect, and replay workflow. Evaluate the result display separately from simulation fidelity. | Record task completion, navigation errors, and whether students can explain what the synthetic peak measures. |

Docking and a contextual command console can help an expert workspace once those
tasks are established. A first-time learner needs a predictable layout with a visible
next action. Use further educator and student testing to decide when more controls
belong on the default surface.

## Workbench development

### Baseline usability audit

| Workspace | Observed friction | Workbench change |
| --- | --- | --- |
| Projects | Run IDs carried little context until a run was opened. | Show the selected run's backend, seed, budget and state beside history. |
| Simulation | The configuration had no comparison presets and raw JSON filled the results area. | Add physical presets and a readable committed result with optional technical details. |
| Event Inspector | Thin tracks competed with axes and detector outlines. The earlier three-panel layout squeezed each view. | Give 3D the main canvas with a short, linked XY/XZ strip. Offer single-view layouts and frame the selected track on demand. |
| Runs and Comparisons | Histogram bins could not be inspected or compared against an earlier result. | Expose bin bounds, counts and uncertainty on hover. Allow pinning a committed run beside the current one. |
| CMS Open Data | Long manifest details were difficult to scan. | Separate dataset metadata, certification, provenance, files and analysis scope. |
| Validation | Raw worker JSON hid the acceptance gate and its measured residuals. | Show the model, maximum and RMS residuals, threshold, and status before the raw record. |
| Learn HEPLab | Instructions assumed an outdated viewport layout and external completion requirements were hard to find. | Use the 3D workflow and show the required evidence alongside each exercise. |

The native Workbench builds from the root CMake project. It uses Qt Widgets for
navigation and controls, QPainter for the projections and histograms, and
QOpenGLWidget for the interactive 3D viewport. The simulation worker supplies
scientific results through its existing local protocol.

The shell uses the Fusion palette with light and dark options. The dark palette
uses charcoal panels, a cyan focus border, and light text. Standard controls
use 10-point typography and a 27-pixel minimum height. Expert density uses
9-point typography and a 21-pixel minimum height. The event
views retain a dark scientific canvas with blue and amber track colors and a
white selection highlight in either shell theme.

Ctrl+K opens the workspace chooser. Ctrl+Enter runs the configured experiment
when the worker is ready. Qt settings retain appearance, window geometry,
and inspector dock placement. The Event Inspector opens with 3D above the linked
XY and XZ projections. Use the layout selector for a single view, **Frame track**
to center the selected trajectory, and **Fit** to restore the overview. Event
navigation shows the sequence position and supports Alt+Left and Alt+Right.
The layer controls distinguish model surfaces, predicted crossings, and the
optional CMS iSpy reference overlays. The track details list predicted crossing
coordinates in metres.

In **Simulation**, choose **pp collision · PYTHIA8 / DELPHES** to generate
13 TeV Drell–Yan events using the pinned Linux or WSL runtime. The run captures
the dimuon momentum, pseudorapidity and isolation cuts. The 3D inspector renders
bounded ideal-solenoid paths for stable generated charged particles. It lists
neutral truth particles and reconstructed DELPHES objects without assigning them
measured tracks. The trajectory filter shows all paths, muons, or other charged
particles.

**Runs and Comparisons** plots invariant mass, muon transverse momentum,
muon pseudorapidity, missing transverse momentum, and jet multiplicity when the
committed artifact supplies those observables. Bar, step, unit-area normalized
shape, and cumulative histogram modes use the same bins and event-level
uncertainties. Low-statistics or single-bin states are explicitly badged as
descriptive views. Pinning a run shares the horizontal range and bin edges
between plots. Collision plots retain signed generator weights and group
uncertainties by event, without luminosity normalization.
The **Selection cutflow** tab shows event counts, weighted yields, uncertainties,
and the selection applied to each run, while the **Bin values** tab exposes
exact per-bin counts, uncertainties, normalized fractions, and cumulative sums.
Export supports both PNG images and provenance-annotated CSV bin tables.
Changing the displayed axis range or bin count does not change the artifact.
CMS catalog entries and Learning lessons render structured, theme-aware metadata
and status cards. Simulation shows a committed result summary, and Validation
compares tracker field residuals with the worker's acceptance threshold.
Both pages keep the source JSON in optional technical details. Lesson
progress records only evidence the desktop can verify.

In the **Event Inspector**, collision events show `event_info` provenance (source,
event weight, dimuon selection status, mass, MET, and DELPHES muon/jet counts),
human-readable PDG species labels, an explicit `Origin` column (`PYTHIA8 truth`
vs `DELPHES reco`), and visual differentiation between muon trajectories and
other charged particles with persistent `μ−`/`μ+` endpoint badges.

The transverse source is a single-event bench. The angular source supports
1–200 events through the same reference solver. The editor limits the budget
to the selected source and saves that choice with the project configuration.

The `heplab_live_workspaces` Qt test starts an isolated project and a real
worker, checks event navigation in a two-event angular sample, compares
committed runs at 45 and 30 GeV/c, and navigates all seven workspaces.
It checks the layout at 1024×720 and 1280×820 logical pixels. Setting
`HEPLAB_WORKSPACE_CAPTURES` to a writable directory records the seven visible
workspaces at the larger size.
